"""R91 (H-034) — secundárias pré-registradas (não decidem): comprou_no_topo, perda ≥ 50 %, só operator/5,
uma por mint, por pista, P com nulo junto do false, saídas, posições reais. Saída: sec.txt."""

from __future__ import annotations

import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run91 import build, f, rd, r_of  # noqa: E402
from stats91 import Units, adjusted, bootstrap, supported_strata  # noqa: E402
from freeze91 import WINDOWS, regime, ts  # noqa: E402

REPS, SEED = 10_000, 20261007


def ratio_ci(flag: np.ndarray, x: np.ndarray, mint: np.ndarray) -> tuple[float, float, float, float, float]:
    """taxas (true, false), razão false÷true e IC 95 % por bootstrap de mint (agrupado, descritivo)."""
    rt, rf = flag[x].mean(), flag[~x].mean()
    uniq, inv = np.unique(mint.astype(str), return_inverse=True)
    rng = np.random.default_rng(SEED)
    out = []
    for _ in range(REPS):
        c = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))[inv].astype(float)
        a, b = (c * flag * x).sum() / max((c * x).sum(), 1e-12), (c * flag * ~x).sum() / max((c * ~x).sum(), 1e-12)
        if a > 0:
            out.append(b / a)
    lo, hi = np.percentile(out, [2.5, 97.5])
    return float(rt), float(rf), float(rf / rt) if rt > 0 else math.nan, float(lo), float(hi)


def line(tag: str, u: Units) -> str:
    b = bootstrap(u, by="mint", reps=REPS, seed=SEED)
    ok = np.isfinite(u.y)
    return (f"  {tag}: n {int((u.x & ok).sum())}/{int((~u.x & ok).sum())} · D_adj {f(b.d)} IC mint [{f(b.lo)}; {f(b.hi)}]"
            f" · nível true {f(adjusted(u)[1])}")


def main() -> None:
    elig, out, units = rd("eligible.csv"), {o["bet_id"]: o for o in rd("outcomes.csv")}, rd("units.csv")
    log = ["R91 — secundárias da H-034 (descritivas)"]
    for var in ("H", "P"):
        rows = [r for r in elig if r["var"] == var]
        meas = [r for r in rows if out[r["bet_id"]]["status"] == "closed" and out[r["bet_id"]]["outcome_quality"] == "measured"]
        x = np.array([r["x"] == "true" for r in meas])
        mint = np.array([r["mint"] for r in meas], object)
        o = [out[r["bet_id"]] for r in meas]
        rv = np.array([r_of(z) for z in o])
        topo = np.array([Decimal(z["pnl_sol"]) < 0 and z["high_water_x"] != "" and Decimal(z["high_water_x"]) <= 1 for z in o])
        big = rv <= -0.5
        log.append(f"\n== {var}")
        for name, fl in (("comprou_no_topo", topo), ("perda ≥ 50 %", big)):
            rt, rf, ra, lo, hi = ratio_ci(fl, x, mint)
            log.append(f"  {name}: true {rt:.1%} · false {rf:.1%} · false÷true {ra:.2f}× IC mint [{lo:.2f}; {hi:.2f}]")
        for arm, m in (("true", x), ("false", ~x)):
            ex = Counter(z["exit_reason"] for z, k in zip(o, m) if k)
            log.append(f"  saídas {arm}: {dict(ex.most_common())}")
        up = build(rows, out, "prim")
        if var == "H":
            log.append(line("só operator/5", up.take(up.conj.astype(str) == "operator/5")))
        first: dict[str, int] = {}
        for i, r in enumerate(rows):
            j = first.get(r["mint"])
            if j is None or r["proposed_at"] < rows[j]["proposed_at"]:
                first[r["mint"]] = i
        one = np.zeros(len(rows), bool)
        one[list(first.values())] = True
        log.append(line("uma unidade por mint (a mais antiga)", up.take(one)))
        for lane in ("meme_event_gate_v1", "meme_features_15s_v1"):
            log.append(line(f"pista {lane}", up.take(np.array([r["series"] == lane for r in rows]))))
    # P com nulo junto do false (estratos com suporte recalculados nessa definição)
    keep = []
    for r in units:
        at = ts(r["proposed_at"])
        if r["snap_mayhem"] == "true" or r["tok_mayhem"] == "true":
            continue
        if r["rs"] == "operator/5" and any(a <= at <= b for a, b in WINDOWS):
            continue
        keep.append({**r, "x": "true" if r["progress_rising"] == "true" else "false",
                     "stratum": f"{r['rs']}|{regime(r['rs'], at)}", "day": at.date().isoformat()})
    u0 = Units(np.zeros(len(keep)), np.array([r["x"] == "true" for r in keep]), np.array([r["stratum"] for r in keep], object),
               np.array([r["mint"] for r in keep], object), np.array([r["day"] for r in keep], object),
               np.array([r["rs"] for r in keep], object))
    sup = supported_strata(u0, min_per_arm=5)
    pn = [r for r in keep if r["stratum"] in sup and r["bet_id"] in out]
    log.append(f"\n== P com nulo junto do false: estratos {sorted(sup)}, {len(pn)} unidades com desfecho lido"
               f" (das {sum(r['stratum'] in sup for r in keep)} elegíveis nessa definição)")
    log.append(line("P nulo=false", build(pn, out, "prim")))
    # posições reais da operator/5
    real = [r for r in rd("real.csv") if r["status"] == "closed" and r["pnl_sol"] and r["holders_rising"] in ("true", "false")]
    y = np.array([float(Decimal(r["pnl_sol"]) / (Decimal(r["sol_spent_lamports"]) / Decimal(10**9))) for r in real])
    ur = Units(y, np.array([r["holders_rising"] == "true" for r in real]), np.array(["op5"] * len(real), object),
               np.array([r["mint"] for r in real], object), np.array([r["proposed_at"][:10] for r in real], object),
               np.array(["op5"] * len(real), object))
    b = bootstrap(ur, by="mint", reps=REPS, seed=SEED)
    log.append(f"\n== posições reais operator/5 (H): {len(real)} fechadas · true {int(ur.x.sum())} média {f(float(y[ur.x].mean()))}"
               f" · false {int((~ur.x).sum())} média {f(float(y[~ur.x].mean()))} · D {f(b.d)} IC mint [{f(b.lo)}; {f(b.hi)}]")
    print("\n".join(log))


if __name__ == "__main__":
    main()
