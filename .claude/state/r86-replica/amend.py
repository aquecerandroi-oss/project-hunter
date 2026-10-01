"""r86-replica — cláusulas da emenda de 2026-10-01 03:02Z (falha fechada, bootstrap de mercado, diagnósticos)."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from feat import ols_beta, robust_z
from replica import CUTS, MRE, REPS, SEED, enrich, holm, load, units


def X_of(us, first):
    cols = [np.ones(len(us)), first] + [robust_z(np.array([u[k] for u in us])) for k in ("dlow", "atr", "r4")]
    return np.column_stack(cols)


def full_rank(X):
    return np.linalg.matrix_rank(X) == X.shape[1] and np.all(np.isfinite(X))


def boot_fc(X, y, clusters, coef=1):
    labs = sorted(set(clusters))
    idx = defaultdict(list)
    for i, c in enumerate(clusters):
        idx[c].append(i)
    groups = [np.array(idx[c]) for c in labs]
    rng = np.random.default_rng(SEED)
    out, dropped = [], 0
    for _ in range(REPS):
        ii = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        if not full_rank(X[ii]):
            dropped += 1
            continue
        out.append(ols_beta(X[ii], y[ii])[coef])
    return np.array(out), dropped


def main():
    sig, days, win = load()
    allu = units(enrich(sig, days, win))
    res = {}
    for st in ("momentum", "volume_anomaly"):
        us = [u for u in allu if u["strategy"] == st]
        y = np.array([u["y"] for u in us])
        rz = np.array([u["razao"] for u in us])
        o = {"n": len(us), "days": len({u["day"] for u in us}), "npos": int((rz > 0).sum()), "nneg": int((rz <= 0).sum())}
        o["limit"] = o["n"] < 150 or o["days"] < 15 or min(o["npos"], o["nneg"]) < 30
        mads = {k: float(np.median(np.abs(np.array([u[k] for u in us]) - np.median([u[k] for u in us]))))
                for k in ("razao", "dlow", "atr", "r4")}
        print(f"\n## {st}: n {o['n']} dias {o['days']} >0 {o['npos']} ≤0 {o['nneg']} limite {o['limit']} MAD {mads}")
        if o["limit"]:
            res[st] = (o, 1.0)
            continue
        X = X_of(us, robust_z(rz))
        print(f"posto completo {full_rank(X)}; número de condição {np.linalg.cond(X):.3f}")
        if not (full_rank(X) and np.all(np.isfinite(y)) and min(mads.values()) > 0):
            print("falha fechada: instrumento inválido na amostra inteira")
            res[st] = (dict(o, inst=True, cid=(np.nan, np.nan), cim=(np.nan, np.nan)), 1.0)
            continue
        b = ols_beta(X, y)[1]
        bd, dd = boot_fc(X, y, [u["day"] for u in us])
        bm, dm = boot_fc(X, y, [u["market_id"] for u in us])
        pd_ = float(np.mean(bd - b >= b))
        pm = float(np.mean(bm - b >= b))
        cid = np.percentile(bd, [2.5, 97.5])
        cim = np.percentile(bm, [2.5, 97.5])
        print(f"β_razao {b:+.4f} | dia IC [{cid[0]:+.4f}; {cid[1]:+.4f}] p {pd_:.4f} descartadas {dd} | "
              f"mercado ({len({u['market_id'] for u in us})}) IC [{cim[0]:+.4f}; {cim[1]:+.4f}] p {pm:.4f} descartadas {dm}")
        # nível do grupo favorável com IC do mesmo bootstrap de dia
        days_ = [u["day"] for u in us]
        labs = sorted(set(days_))
        rng = np.random.default_rng(SEED)
        grp = defaultdict(list)
        for i, d in enumerate(days_):
            grp[d].append(i)
        lv = []
        for _ in range(REPS):
            ii = np.concatenate([np.array(grp[labs[j]]) for j in rng.integers(0, len(labs), len(labs))])
            sel = ii[rz[ii] > 0]
            if sel.size:
                lv.append(y[sel].mean())
        print(f"nível razão>0: média {y[rz > 0].mean():+.4f} IC dia [{np.percentile(lv, 2.5):+.4f}; {np.percentile(lv, 97.5):+.4f}]")
        lomo = [ols_beta(X[[i for i, u in enumerate(us) if u["market_id"] != m]],
                         y[[i for i, u in enumerate(us) if u["market_id"] != m]])[1] for m in {u["market_id"] for u in us}]
        lodo = [ols_beta(X[[i for i, d in enumerate(days_) if d != dd_]], y[[i for i, d in enumerate(days_) if d != dd_]])[1]
                for dd_ in labs]
        print(f"β sem cada mercado [{min(lomo):+.4f}; {max(lomo):+.4f}] · sem cada dia [{min(lodo):+.4f}; {max(lodo):+.4f}]")
        top_m = max(defaultdict(int, {m: sum(1 for u in us if u["market_id"] == m) for m in {u['market_id'] for u in us}}).values())
        top_d = max(len(v) for v in grp.values())
        print(f"concentração: maior mercado {top_m}/{o['n']} ({top_m / o['n']:.1%}), maior dia {top_d}/{o['n']} ({top_d / o['n']:.1%})")
        Xr = np.column_stack([X[:, 0], X[:, 2:]])
        resid = X[:, 1] - Xr @ ols_beta(Xr, X[:, 1])
        print(f"dispersão residual de z_razao depois dos controles: dp {resid.std():.4f} (dp bruto {X[:, 1].std():.4f})")
        plat, parts = [], []
        for c in CUTS:
            ind = (rz > c).astype(float)
            parts.append(tuple(ind))
            Xc = X_of(us, ind)
            plat.append(ols_beta(Xc, y)[1] if full_rank(Xc) and 0 < ind.sum() < len(ind) else math.nan)
        print("patamar:", " ".join(f"{c:+.3f}:{v:+.4f}" for c, v in zip(CUTS, plat)))
        k1 = set(labs[: math.ceil(len(labs) / 2)])
        hv = []
        for part in (True, False):
            sub = [i for i, d in enumerate(days_) if (d in k1) == part]
            hv.append(ols_beta(X[sub], y[sub])[1] if full_rank(X[sub]) else math.nan)
        print(f"metades: {hv[0]:+.4f} / {hv[1]:+.4f}")
        inst = dd > REPS / 100 or dm > REPS / 100 or any(math.isnan(v) for v in plat + hv)
        # patamar: >= 4 cortes consecutivos com β > 0 E partições distintas entre si
        pl_ok = any(all(v > 0 for v in plat[i:i + 4]) and len(set(parts[i:i + 4])) == 4 for i in range(len(CUTS) - 3))
        o.update(b=b, cid=cid, cim=cim, plat=plat, hv=hv, inst=inst, lvl=y[rz > 0].mean(), pl_ok=pl_ok)
        res[st] = (o, max(pd_, pm))
    ps = [p for _o, p in res.values()]
    labels = {}
    for (st, (o, _p)), ph in zip(res.items(), holm(ps)):
        if o["limit"]:
            lab = "LIMITE DE DADO"
        elif o["inst"]:
            lab = "LIMITE (instrumento)"
        elif o["cid"][1] < MRE and o["cim"][1] < MRE:
            lab = "REFUTA"
        elif (o["b"] >= MRE and o["cid"][0] > 0 and o["cim"][0] > 0 and ph < 0.05 and o["lvl"] > 0
              and all(v > 0 for v in o["hv"]) and o["pl_ok"]):
            lab = "CONFIRMA"
        else:
            lab = "NÃO CONFIRMA"
        labels[st] = lab
        print(f"{st}: p Holm (maior dos dois) {ph:.4f} → {lab}")
    vals = list(labels.values())
    glob = ("CONFIRMA" if "CONFIRMA" in vals else "REFUTA" if all(v == "REFUTA" for v in vals)
            else "LIMITE DE DADO" if all(v.startswith("LIMITE") for v in vals) else "NÃO CONFIRMA")
    print(f"\nH-027 pela emenda (regra global 4): {glob}")
    orig = [v for v in vals if not v.startswith("LIMITE")]
    print("H-027 pelo texto original do bloco (REFUTA se todas as fora do limite refutarem):",
          "REFUTA" if orig and all(v == "REFUTA" for v in orig) else "outro")


if __name__ == "__main__":
    main()
