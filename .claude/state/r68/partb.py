"""R68 parte B — walk-forward fora de amostra, limiares fixos (primário).

Protocolo: `.claude/state/r68/preregistro.md` + EMENDA 1.
Bootstrap de blocos temporais conjuntos (3 dias), p-valor centrado sob o nulo,
Holm (confirmação) e BH (reportado), baseline "sempre long" na mesma população.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np

from load68 import HORIZONS, bars_for, load_csv_gz
from signals68 import PREDICTORS, compute

SEED = 68
N_BOOT = 5000
BLOCK_DAYS = 3
MIN_TRADES = 30
MRE = 0.0010  # ganho mínimo economicamente relevante: +0,10 % líquido por operação
COST_PROXY = float(Decimal("0.0014"))
COST_DESK = float(Decimal("0.0014") + Decimal("0.0002") / Decimal("0.05"))
NAN = float("nan")


def panel(raw: dict, h: int, delay: int = 0) -> dict:
    """Empilha todos os mercados num painel de pontos de decisão do horizonte `h`.

    `delay = 1` é a sensibilidade da E1.6c: decide no fecho de `b`, entra no fecho
    de `b+1` e sai em `b+1+h`.
    """
    bars = bars_for(raw, h)
    sol = bars.get("SOLUSDT")
    sol_ret: dict[int, float] = {}
    if sol is not None and len(sol) > 1:
        cont = sol.bucket_start[1:] == sol.bucket_start[:-1] + h
        sol_ret = dict(
            zip(
                sol.bucket_start[:-1][cont].tolist(),
                (sol.close[1:][cont] / sol.close[:-1][cont] - 1.0).tolist(),
            )
        )
    keys = ("day", "mkt", "ret", "ret_sol", "eligible", *PREDICTORS)
    cols: dict[str, list] = {k: [] for k in keys}
    for si, (sym, b) in enumerate(sorted(bars.items())):
        n = len(b)
        need = delay + 1
        if n <= need + 2:
            continue
        sig = compute(b)
        i = np.arange(n - need)
        ok = b.bucket_start[i + need] == b.bucket_start[i] + need * h
        i = i[ok]
        if i.size == 0:
            continue
        r = b.close[i + need] / b.close[i + delay] - 1.0
        rs = np.array([sol_ret.get(int(x), NAN) for x in b.bucket_start[i + delay]])
        cols["day"].append(b.bucket_start[i] // 1440)
        cols["mkt"].append(np.full(i.size, si))
        cols["ret"].append(r)
        cols["ret_sol"].append((1.0 + r) / (1.0 + rs) - 1.0)
        cols["eligible"].append(sig["eligible"][i])
        for p in PREDICTORS:
            cols[p].append(sig[p][i])
    out: dict = {k: np.concatenate(v) for k, v in cols.items() if v}
    out["symbols"] = np.array(sorted(bars.keys()))
    return out


def _blocks(day: np.ndarray) -> np.ndarray:
    return (day - int(day.min())) // BLOCK_DAYS


def _per_block(block, ret, mask, nb):
    s = np.bincount(block[mask], weights=ret[mask], minlength=nb)
    c = np.bincount(block[mask], minlength=nb).astype(np.float64)
    return s, c


def _stat(s, c, cost):
    tot = c.sum()
    return float(s.sum() / tot - cost) if tot > 0 else NAN


def evaluate(
    pan: dict, mask: np.ndarray, cost: float, ret_key: str = "ret",
    base_mask: np.ndarray | None = None,
) -> dict:
    """Retorno líquido médio por operação, IC e p por bootstrap de blocos conjuntos.

    `base_mask` restringe o baseline "sempre long" à mesma população do sinal
    (E1.9a). O adaptativo tem de o passar: o sinal só existe nas janelas de teste,
    e comparar com um sempre-long do painel inteiro compara regimes diferentes.
    """
    ret = pan[ret_key]
    good = np.isfinite(ret)
    block = _blocks(pan["day"])
    nb = int(block.max()) + 1
    base = pan["eligible"] & good
    if base_mask is not None:
        base = base & base_mask
    sig = mask & base
    ns = int(sig.sum())
    if ns < MIN_TRADES:
        return {"n": ns, "status": "sem_potencia"}
    ss, sc = _per_block(block, ret, sig, nb)
    bs, bc = _per_block(block, ret, base, nb)
    theta = _stat(ss, sc, cost)
    theta_long = _stat(bs, bc, cost)
    rng = np.random.default_rng(SEED)
    draw = rng.integers(0, nb, size=(N_BOOT, nb))
    ts = ss[draw].sum(1) / np.maximum(sc[draw].sum(1), 1e-12) - cost
    tl = bs[draw].sum(1) / np.maximum(bc[draw].sum(1), 1e-12) - cost
    lo, hi = np.percentile(ts, [2.5, 97.5])
    dlo, dhi = np.percentile(ts - tl, [2.5, 97.5])
    return {
        "n": ns,
        "status": "ok",
        "taxa_entrada": float(ns / max(int(base.sum()), 1)),
        "mean_net": theta,
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "p_boot": float(np.mean(np.abs(ts - theta) >= abs(theta))),
        "sempre_long": theta_long,
        "delta": theta - theta_long,
        "delta_lo": float(dlo),
        "delta_hi": float(dhi),
        "blocos": nb,
        "blocos_com_entrada": int((sc > 0).sum()),
    }


def _adjust(pv: list[float]) -> tuple[list[float], list[float]]:
    m = len(pv)
    order = list(np.argsort(pv))
    holm = [0.0] * m
    run = 0.0
    for k, idx in enumerate(order):
        run = max(run, min(1.0, (m - k) * pv[idx]))
        holm[idx] = run
    bh = [0.0] * m
    run = 1.0
    for k in range(m - 1, -1, -1):
        idx = order[k]
        run = min(run, min(1.0, m / (k + 1) * pv[idx]))
        bh[idx] = run
    return holm, bh


def main() -> None:
    raw = load_csv_gz(Path(sys.argv[1]))
    label = sys.argv[2] if len(sys.argv) > 2 else "U2"
    cells: list[dict] = []
    for h in HORIZONS:
        pan = panel(raw, h)
        pan_d1 = panel(raw, h, delay=1)
        for p in PREDICTORS:
            cells.append(
                {
                    "universo": label,
                    "h": h,
                    "preditor": p,
                    "proxy_014": evaluate(pan, pan[p], COST_PROXY),
                    "mesa_054": evaluate(pan, pan[p], COST_DESK),
                    "sol_014": evaluate(pan, pan[p], COST_PROXY, ret_key="ret_sol"),
                    "atraso1_014": evaluate(pan_d1, pan_d1[p], COST_PROXY),
                }
            )
        print(f"h={h}: painel {pan['ret'].size} pontos, {int(pan['eligible'].sum())} elegiveis", flush=True)

    ok = [c for c in cells if c["proxy_014"]["status"] == "ok"]
    holm, bh = _adjust([c["proxy_014"]["p_boot"] for c in ok])
    for c, ho, b in zip(ok, holm, bh):
        pr = c["proxy_014"]
        c["holm"] = ho
        c["bh"] = b
        c["confirma"] = bool(pr["mean_net"] > 0 and pr["ci_lo"] > 0 and ho < 0.05 and pr["delta_lo"] > 0)
        c["evidencia_contra_MRE"] = bool(pr["ci_hi"] < MRE)
    Path(f"partb_{label}.json").write_text(json.dumps(cells, indent=1), encoding="utf-8")

    print()
    print(
        f"{'h':>4} {'preditor':<14} {'n':>8} {'entr%':>6} {'liq@0.14%':>12} "
        f"{'IC95 (bp)':>19} {'p':>6} {'Holm':>6} {'long':>9} {'delta':>9} "
        f"{'@0.54%':>10} {'em SOL':>9} {'atraso1':>9}"
    )
    for c in cells:
        pr, ms, so, at = c["proxy_014"], c["mesa_054"], c["sol_014"], c["atraso1_014"]
        if pr["status"] != "ok":
            print(f"{c['h']:>4} {c['preditor']:<14} {pr['n']:>8}   sem potencia (< 30 operacoes)")
            continue
        g = lambda d: d["mean_net"] * 1e4 if d["status"] == "ok" else NAN  # noqa: E731
        print(
            f"{c['h']:>4} {c['preditor']:<14} {pr['n']:>8} {pr['taxa_entrada'] * 100:>5.1f}% "
            f"{pr['mean_net'] * 1e4:>+10.2f}bp [{pr['ci_lo'] * 1e4:>+8.2f},{pr['ci_hi'] * 1e4:>+8.2f}] "
            f"{pr['p_boot']:>6.3f} {c['holm']:>6.3f} {pr['sempre_long'] * 1e4:>+8.2f} "
            f"{pr['delta'] * 1e4:>+8.2f} {g(ms):>+9.2f} {g(so):>+8.2f} {g(at):>+8.2f}"
        )
    conf = [c for c in cells if c.get("confirma")]
    print(f"\nCONFIRMAM (regra congelada, Holm < 0,05): {len(conf)} -> {[(c['h'], c['preditor']) for c in conf]}")
    contra = sum(1 for c in cells if c.get("evidencia_contra_MRE"))
    print(f"EVIDENCIA CONTRA vantagem util (IC sup < +{MRE * 1e4:.0f} bp): {contra}/{len(cells)}")


if __name__ == "__main__":
    main()
