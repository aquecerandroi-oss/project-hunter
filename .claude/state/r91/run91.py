"""R91 (H-034) — corre o pré-registro + emenda 1 sobre a lista congelada e os desfechos lidos uma vez.

Entrada: cache/eligible.csv (congelada), cache/days.txt, cache/units.csv, cache/outcomes.csv, cache/real.csv.
Saída: h034.txt (stdout).
"""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats91 import (  # noqa: E402
    Scenario, Units, adjusted, bootstrap, family_verdict, halves_mask, holm, leave_one_out,
    measure_verdict, supported_strata,
)

REPS, SEED, MRE, ATA = 10_000, 20261007, 0.05, 0.0186


def rd(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(open(HERE / "cache" / name, encoding="utf-8")))


def r_of(o: dict[str, str]) -> float | None:
    if not o["pnl_sol"] or not o["sol_spent"] or Decimal(o["sol_spent"]) == 0:
        return None
    return float(Decimal(o["pnl_sol"]) / Decimal(o["sol_spent"]))


def build(rows: list[dict[str, str]], out: dict[str, dict[str, str]], scen: str) -> Units:
    y = []
    for r in rows:
        o = out[r["bet_id"]]
        v = r_of(o)
        if o["status"] == "closed" and o["outcome_quality"] == "measured" and v is not None:
            y.append(v)
        elif scen == "S1" and o["status"] == "closed" and o["outcome_quality"] == "indeterminate":
            y.append(-1.0)
        else:
            y.append(math.nan)
    return Units(
        y=np.array(y), x=np.array([r["x"] == "true" for r in rows]), s=np.array([r["stratum"] for r in rows], object),
        mint=np.array([r["mint"] for r in rows], object), day=np.array([r["day"] for r in rows], object),
        conj=np.array([r["rs"] for r in rows], object),
    )


def f(v: float, k: int = 4) -> str:
    return "nan" if not math.isfinite(v) else f"{v:+.{k}f}"


def scenario(u: Units, days: list[str], tag: str, log: list[str]) -> tuple[Scenario, float]:
    bm = bootstrap(u, by="mint", reps=REPS, seed=SEED)
    bd = bootstrap(u, by="day", reps=REPS, seed=SEED)
    _, lvl = adjusted(u)
    m1, m2 = halves_mask(u.day, days)
    hv = (adjusted(u.take(m1))[0], adjusted(u.take(m2))[0])
    loo = leave_one_out(u)
    log.append(f"  [{tag}] n={int(np.isfinite(u.y).sum())} D_adj {f(bm.d)} · IC mint [{f(bm.lo)}; {f(bm.hi)}] "
               f"(básico [{f(bm.basic_lo)}; {f(bm.basic_hi)}], inválidas {bm.invalid:.2%}, p {bm.p:.4f}) · "
               f"IC dia [{f(bd.lo)}; {f(bd.hi)}] (básico [{f(bd.basic_lo)}; {f(bd.basic_hi)}], inválidas {bd.invalid:.2%}, "
               f"p {bd.p:.4f})")
    log.append(f"  [{tag}] nível ajustado do braço true {f(lvl)} (com ATA {f(lvl - ATA)}) · metades {f(hv[0])} / {f(hv[1])} · "
               f"deixa-um-fora {{{', '.join(f'{k}: {f(v)}' for k, v in loo.items())}}}")
    sc = Scenario(bm.d, bm.lo, bm.hi, bd.lo, bd.hi, bm.invalid, bd.invalid, lvl, hv, tuple(loo.values()))
    return sc, max(bm.p, bd.p)


def arms(u: Units) -> str:
    ok = np.isfinite(u.y)
    parts = []
    for name, m in (("true", u.x & ok), ("false", ~u.x & ok)):
        parts.append(f"{name}: {int(m.sum())} un/{len(set(u.mint[m]))} mints/{len(set(u.day[m]))} dias, "
                     f"média {f(float(u.y[m].mean()) if m.any() else math.nan)}, mediana "
                     f"{f(float(np.median(u.y[m])) if m.any() else math.nan)}")
    return " · ".join(parts)


def main() -> None:
    elig, days = rd("eligible.csv"), (HERE / "cache" / "days.txt").read_text().split()
    out = {o["bet_id"]: o for o in rd("outcomes.csv")}
    units = rd("units.csv")
    log = [f"R91 — H-034 · desfechos lidos em {next(iter(out.values()))['read_at']} · {len(out)} apostas"]
    agree = [(r["holders_rising"] == r["f15_holders_rising"], r["progress_rising"] == r["f15_progress_rising"])
             for r in units if r["f15_row"] == "t"]
    conc = {"H": sum(a for a, _ in agree) / len(agree), "P": sum(b for _, b in agree) / len(agree)}
    log.append(f"I1 concordância bloco flow × meme_features_15s: {len(agree)} unidades, H {conc['H']:.2%}, P {conc['P']:.2%}")
    res: dict[str, dict[str, object]] = {}
    for var in ("H", "P"):
        rows = [r for r in elig if r["var"] == var]
        log.append(f"\n== {var} ({'holders_rising' if var == 'H' else 'progress_rising'}) — {len(rows)} unidades na lista")
        stat = Counter((r["x"], out[r["bet_id"]]["status"], out[r["bet_id"]]["outcome_quality"]) for r in rows)
        log.append(f"  status × qualidade por braço: {dict(sorted(stat.items()))}")
        instr = []
        if conc[var] < 0.99:
            instr.append("concordância < 99 %")
        for arm in ("true", "false"):
            a = [out[r["bet_id"]] for r in rows if r["x"] == arm]
            meas = [o for o in a if o["status"] == "closed" and o["outcome_quality"] == "measured"]
            cap = sum(o["cap_applied"] == "true" for o in meas)
            miss = sum(not (o["status"] == "closed" and o["outcome_quality"] == "measured") for o in a)
            log.append(f"  braço {arm}: teto aplicado {cap}/{len(meas)} · ausentes (indeterminate/abertas) {miss}/{len(a)}")
            if meas and cap / len(meas) > 0.02:
                instr.append(f"teto em > 2 % ({arm})")
            if a and miss / len(a) > 0.20:
                instr.append(f"ausentes > 20 % ({arm})")
        up = build(rows, out, "prim")
        us = build(rows, out, "S1")
        ok = np.isfinite(up.y)
        limit = None
        nt, nf = int((up.x & ok).sum()), int((~up.x & ok).sum())
        dt, df_ = len(set(up.day[up.x & ok])), len(set(up.day[~up.x & ok]))
        mt, mf = len(set(up.mint[up.x & ok])), len(set(up.mint[~up.x & ok]))
        if nt + nf < 100 or min(nt, nf) < 30 or min(dt, df_) < 8 or min(mt, mf) < 8:
            limit = f"n {nt + nf}, braços {nt}/{nf}, dias {dt}/{df_}, mints {mt}/{mf}"
        log.append(f"  primário: {arms(up)}")
        log.append(f"  instrumento: {instr or 'passa'} · limite de dado: {limit or 'passa'}")
        sp, pp = scenario(up, days, "primário", log)
        ss, ps = scenario(us, days, "S1", log)
        res[var] = {"instr": instr or None, "limit": limit, "sp": sp, "ss": ss, "pp": pp, "ps": ps}
    hp = holm({k: (1.0 if v["instr"] or v["limit"] else v["pp"]) for k, v in res.items()})
    hs = holm({k: (1.0 if v["instr"] or v["limit"] else v["ps"]) for k, v in res.items()})
    verdicts = {}
    for var, v in res.items():
        verdicts[var] = measure_verdict(instrument="; ".join(v["instr"]) if v["instr"] else None, limit=v["limit"],
                                        prim=v["sp"], s1=v["ss"], p_holm=max(hp[var], hs[var]), mre=MRE)
        log.append(f"\n{var}: p bruto prim {v['pp']:.4f} / S1 {v['ps']:.4f} · Holm prim {hp[var]:.4f} / S1 {hs[var]:.4f} "
                   f"→ {verdicts[var]}")
    log.append(f"H-034 (família): {family_verdict(verdicts)}")
    print("\n".join(log))


if __name__ == "__main__":
    main()
