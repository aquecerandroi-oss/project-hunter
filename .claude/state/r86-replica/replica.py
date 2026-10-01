"""r86-replica — análise independente da H-027 (pré-registro em Fila de Hipoteses.md § H-027).

Entradas (extraídas por q_sig.sql, q_daily_chunk.sql, q_win_tpl.sql): cache/sig.csv, cache/daily.csv, cache/win.csv.
Saídas: out/units_<variante>.csv e o relatório no stdout.
"""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np

from feat import DayAgg, ols_beta, razao_mm20d, robust_z, window_cov

HERE = Path(__file__).parent
SEED, REPS, MRE = 20261001, 10_000, 0.05
CUTS = (-0.05, -0.025, 0.0, 0.025, 0.05)
R83_READ = datetime.fromisoformat("2026-09-28T01:58:45+00:00")


def ts(s: str) -> datetime | None:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s.replace(" ", "T"))


def dec(s: str) -> Decimal | None:
    return Decimal(s) if s else None


def load():
    sig = list(csv.DictReader(open(HERE / "cache/sig.csv", encoding="utf-8")))
    days: dict[str, dict[date, DayAgg]] = defaultdict(dict)
    for r in csv.reader(open(HERE / "cache/daily.csv", encoding="utf-8")):
        mid, d, nf, _na, nfd, c, mrf, _mra = r
        days[mid][date.fromisoformat(d)] = DayAgg(int(nf), int(nfd), dec(c), ts(mrf))
    win = {}
    for r in csv.reader(open(HERE / "cache/win.csv", encoding="utf-8")):
        sid, n, nd, fo, lo_, lo, mr, c1, c241 = r
        win[sid] = {"n": int(n), "n_distinct": int(nd), "first_open": ts(fo), "last_open": ts(lo_),
                    "lo": dec(lo), "max_recv": ts(mr), "c_m1": dec(c1), "c_m241": dec(c241)}
    return sig, days, win


def enrich(sig, days, win, use_guard=True):
    rows = []
    for s in sig:
        obs, em = ts(s["obs"]), ts(s["emitted_at"])
        assert obs is not None and em is not None
        rz, why_rz = razao_mm20d(days.get(s["market_id"], {}), obs, em, use_guard=use_guard)
        dlow, r4, why_w = window_cov(win[s["signal_id"]], obs, em, use_guard=use_guard)
        atr = float(s["atr_pct"]) if s["atr_pct"] else None
        rn = float(s["r_multiple"]) if s["r_multiple"] else None
        rex = float(s["r_ex_funding"]) if s["r_ex_funding"] else None
        rows.append(dict(s, obs_t=obs, em_t=em, razao=rz, why_rz=why_rz, dlow=dlow, r4=r4, why_w=why_w,
                         atr=atr, rn=rn, rex=rex))
    return rows


def waterfall(rows):
    c: Counter = Counter()
    for r in rows:
        if r["rn"] is None:
            c["1_sem_R_net:" + (r["r_net_reason"] or "?").split(":")[0]] += 1
        elif r["why_rz"]:
            c["2_razao:" + r["why_rz"]] += 1
        elif r["why_w"] in ("janela_24h_incompleta", "guarda_24h"):
            c["3_" + r["why_w"]] += 1
        elif r["why_w"] == "sem_return_4h":
            c["4_sem_return_4h"] += 1
        elif r["atr"] is None:
            c["5_sem_atr"] += 1
        else:
            c["ok"] += 1
    return dict(sorted(c.items()))


def complete(r, outcome="rn"):
    return (r[outcome] is not None and r["razao"] is not None and r["dlow"] is not None
            and r["r4"] is not None and r["atr"] is not None)


def units(rows, outcome="rn"):
    g = defaultdict(list)
    for r in rows:
        if complete(r, outcome):
            g[(r["strategy"], r["market_id"], r["obs_t"])].append(r)
    out = []
    for (st, mid, obs), rs in g.items():
        out.append({"strategy": st, "market_id": mid, "symbol": rs[0]["symbol"], "obs": obs, "day": obs.date(),
                    "n_sig": len(rs), "versions": "|".join(sorted(x["version"] for x in rs)),
                    "y": float(np.mean([x[outcome] for x in rs])), "atr": float(np.mean([x["atr"] for x in rs])),
                    "razao": rs[0]["razao"], "dlow": rs[0]["dlow"], "r4": rs[0]["r4"]})
        assert all(x["razao"] == rs[0]["razao"] and x["dlow"] == rs[0]["dlow"] for x in rs)
    out.sort(key=lambda u: (u["obs"], u["market_id"]))
    return out


def design(us, key_var):
    z = [robust_z(np.array([u[k] for u in us])) for k in ("dlow", "atr", "r4")]
    first = key_var(us)
    return np.column_stack([np.ones(len(us)), first, *z])


def boot(X, y, clusters, coef=1, reps=REPS, seed=SEED):
    labs = sorted(set(clusters))
    idx = defaultdict(list)
    for i, c in enumerate(clusters):
        idx[c].append(i)
    groups = [np.array(idx[c]) for c in labs]
    rng = np.random.default_rng(seed)
    bs = np.empty(reps)
    for b in range(reps):
        pick = rng.integers(0, len(groups), len(groups))
        ii = np.concatenate([groups[j] for j in pick])
        bs[b] = ols_beta(X[ii], y[ii])[coef]
    return bs


def analyse(us, label, market_boot=False):
    out = {"label": label, "n": len(us)}
    if not us:
        return out
    y = np.array([u["y"] for u in us])
    rz = np.array([u["razao"] for u in us])
    days_ = [u["day"] for u in us]
    out["days"] = len(set(days_))
    out["n_pos"], out["n_neg"] = int((rz > 0).sum()), int((rz <= 0).sum())
    out["mean_pos"] = float(y[rz > 0].mean()) if out["n_pos"] else math.nan
    out["mean_neg"] = float(y[rz <= 0].mean()) if out["n_neg"] else math.nan
    out["limit"] = out["n"] < 150 or out["days"] < 15 or min(out["n_pos"], out["n_neg"]) < 30
    if out["n"] < 10 or min(out["n_pos"], out["n_neg"]) < 2:
        return out
    X = design(us, lambda v: robust_z(np.array([u["razao"] for u in v])))
    b = ols_beta(X, y)
    out["beta"] = b.tolist()
    bs = boot(X, y, days_)
    out["ci"] = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
    out["p_one"] = float(np.mean(bs - b[1] >= b[1]))
    if market_boot:
        bm = boot(X, y, [u["market_id"] for u in us])
        out["ci_market"] = (float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5)))
    Xs = design(us, lambda v: np.array([1.0 if u["razao"] > 0 else 0.0 for u in v]))
    bsec = ols_beta(Xs, y)
    bss = boot(Xs, y, days_)
    out["sec_beta"], out["sec_ci"] = float(bsec[1]), (float(np.percentile(bss, 2.5)), float(np.percentile(bss, 97.5)))
    plat, prev = [], None
    for c in CUTS:
        grp = tuple(u["razao"] > c for u in us)
        Xc = design(us, lambda v, c=c: np.array([1.0 if u["razao"] > c else 0.0 for u in v]))
        bc = float(ols_beta(Xc, y)[1]) if 0 < sum(grp) < len(grp) else math.nan
        plat.append((c, bc, sum(grp), grp != prev))
        prev = grp
    out["plateau"] = plat
    run = best = 0
    for _c, bc, _n, distinct in plat:
        run = (run + 1 if (distinct or run == 0) else run) if bc > 0 else 0
        best = max(best, run)
    out["plateau_ok"] = best >= 4
    dates = sorted(set(days_))
    k1 = set(dates[: math.ceil(len(dates) / 2)])
    halves = []
    for part in (True, False):
        sub = [i for i, d in enumerate(days_) if (d in k1) == part]
        halves.append(float(ols_beta(X[sub], y[sub])[1]))
    out["halves"] = halves
    return out


def fmt(o):
    s = [f"### {o['label']}: unidades {o['n']}"]
    if o["n"] == 0:
        return "\n".join(s)
    s.append(f"dias UTC {o['days']} · razão>0 {o['n_pos']} (média R {o['mean_pos']:+.4f}) · ≤0 {o['n_neg']} "
             f"(média R {o['mean_neg']:+.4f}) · limite de dado: {o['limit']}")
    if "beta" in o:
        b = o["beta"]
        s.append(f"β [1, z_razao, z_dlow, z_atr, z_r4] = {', '.join(f'{x:+.4f}' for x in b)}")
        s.append(f"β_razao {b[1]:+.4f} IC95 dia [{o['ci'][0]:+.4f}; {o['ci'][1]:+.4f}] p_unilateral {o['p_one']:.4f}")
        if "ci_market" in o:
            s.append(f"  IC95 por mercado [{o['ci_market'][0]:+.4f}; {o['ci_market'][1]:+.4f}]")
        s.append(f"secundária β 1[razão>0] {o['sec_beta']:+.4f} IC95 [{o['sec_ci'][0]:+.4f}; {o['sec_ci'][1]:+.4f}]")
        s.append("patamar: " + " · ".join(f"c={c:+.3f} β={bc:+.4f} n>{n}{'' if d else ' (=partição anterior)'}"
                                          for c, bc, n, d in o["plateau"]) + f" → ok={o['plateau_ok']}")
        s.append(f"metades: {o['halves'][0]:+.4f} / {o['halves'][1]:+.4f}")
    return "\n".join(s)


def verdict(o, p_holm):
    if o["limit"]:
        return "LIMITE DE DADO"
    if o["ci"][1] < MRE:
        return "REFUTA"
    ok = (o["beta"][1] >= MRE and o["ci"][0] > 0 and p_holm < 0.05 and o["mean_pos"] > 0
          and o["plateau_ok"] and all(h > 0 for h in o["halves"]))
    return "CONFIRMA" if ok else "NÃO CONFIRMA"


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def dump(us, name):
    (HERE / "out").mkdir(exist_ok=True)
    with open(HERE / f"out/units_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(us[0].keys()))
        w.writeheader()
        w.writerows(us)


def main(argv):
    sig, days, win = load()
    rows = enrich(sig, days, win)
    print(f"sinais terminais long perp prospectivos: {len(rows)}", Counter(r['strategy'] for r in rows))
    for st in ("momentum", "volume_anomaly", "mean_reversion"):
        print(f"\n## cascata (nível de sinal) {st}:", waterfall([r for r in rows if r["strategy"] == st]))
    allu = units(rows)
    dump(allu, "primary")
    res = {}
    for st in ("momentum", "volume_anomaly"):
        res[st] = analyse([u for u in allu if u["strategy"] == st], st, market_boot=True)
    ps = [res[st].get("p_one", 1.0) if not res[st]["limit"] else 1.0 for st in res]
    for st, ph in zip(res, holm(ps)):
        print("\n" + fmt(res[st]))
        print(f"p Holm {ph:.4f} → VEREDITO {st}: {verdict(res[st], ph)}")
    mr = [u for u in allu if u["strategy"] == "mean_reversion"]
    print("\n" + fmt(analyse(mr, "mean_reversion v14 (descritivo)")))
    print("\n## distribuição de razao_mm20d por estratégia (unidades completas)")
    for st in ("momentum", "volume_anomaly", "mean_reversion"):
        v = np.array([u["razao"] for u in allu if u["strategy"] == st])
        if v.size:
            q = np.percentile(v, [0, 5, 25, 50, 75, 95, 100])
            print(st, v.size, " ".join(f"{x:+.4f}" for x in q), f"média {v.mean():+.4f}")
    avail = Counter()
    seen = set()
    for r in rows:
        if r["razao"] is not None and r["dlow"] is not None and r["r4"] is not None and r["atr"] is not None:
            k = (r["strategy"], r["market_id"], r["obs_t"])
            if k not in seen:
                seen.add(k)
                avail[(r["strategy"], r["razao"] > 0)] += 1
    print("\n## disponibilidade sem olhar R_net (unidades com as 4 variáveis):", dict(avail))
    print("sinais com as 4 variáveis (sem exigir R):",
          Counter(r["strategy"] for r in rows if r["razao"] is not None and r["dlow"] is not None
                  and r["r4"] is not None and r["atr"] is not None))
    mom_markets = {u["market_id"] for u in allu if u["strategy"] == "momentum"}
    print("mercados momentum com unidade completa:", len(mom_markets))
    print("\n## descritivos")
    print(fmt(analyse([u for u in units(enrich(sig, days, win, use_guard=False)) if u["strategy"] == "momentum"],
                      "momentum SEM guardas")))
    print(fmt(analyse([u for u in units(rows, "rex") if u["strategy"] == "momentum"], "momentum r_ex_funding")))
    print(fmt(analyse(units([r for r in rows if r["strategy"] == "momentum" and r["version"] == "v3"]),
                      "momentum só v3")))
    print(fmt(analyse(units([r for r in rows if r["strategy"] == "momentum" and r["em_t"] > R83_READ]),
                      "momentum pós-R83")))


if __name__ == "__main__":
    main(sys.argv)
