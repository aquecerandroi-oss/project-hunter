"""r86-replica — sensibilidades refeitas com as definições do primário, para isolar a causa de cada divergência."""

from __future__ import annotations

import numpy as np

import replica as R
from feat import ols_beta, razao_mm20d, robust_z


def summ(name, us, reps):
    R.REPS = reps
    o = R.analyse(us, name)
    X = R.design(us, lambda v: robust_z(np.array([u["razao"] for u in v])))
    y = np.array([u["y"] for u in us])
    bm = R.boot(X, y, [u["market_id"] for u in us], reps=reps)
    bd = R.boot(X, y, [u["day"] for u in us], reps=reps)
    o["ci"] = (float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5)))
    print(f"- {name} (reps {reps}): n {o['n']} dias {o['days']} | β {o['beta'][1]:+.4f} IC dia [{o['ci'][0]:+.4f}, {o['ci'][1]:+.4f}]"
          f" IC mercado [{np.percentile(bm, 2.5):+.4f}, {np.percentile(bm, 97.5):+.4f}] | nível >0 {o['mean_pos']:+.4f} ≤0 {o['mean_neg']:+.4f}")
    return o


def main():
    sig, days, win = R.load()
    rows = R.enrich(sig, days, win)
    mom = [r for r in rows if r["strategy"] == "momentum"]
    for reps in (10_000, 2000):
        summ("só v3", R.units([r for r in mom if r["version"] == "v3"]), reps)
    # r_ex nas MESMAS linhas da primária (R_net não nulo)
    same = [dict(r, rex=r["rex"]) for r in mom if r["rn"] is not None]
    summ("r_ex_funding mesmas linhas", R.units(same, "rex"), 2000)
    summ("pré-R83", R.units([r for r in mom if r["em_t"] <= R.R83_READ]), 2000)
    # sem a guarda de chegada dos 20 dias, MANTENDO a guarda de 24 h
    ng = []
    for r in mom:
        if r["why_w"] == "guarda_24h":
            continue
        rz, _ = razao_mm20d(days.get(r["market_id"], {}), r["obs_t"], r["em_t"], use_guard=False)
        ng.append(dict(r, razao=rz))
    summ("sem guarda de chegada (mantém 24 h)", R.units(ng), 2000)
    # covariáveis com IC por dia e p da secundária (10 000)
    R.REPS = 10_000
    us = [u for u in R.units(rows) if u["strategy"] == "momentum"]
    y = np.array([u["y"] for u in us])
    X = R.design(us, lambda v: robust_z(np.array([u["razao"] for u in v])))
    b = ols_beta(X, y)
    for j, nm in ((2, "d_low"), (3, "atr"), (4, "r4")):
        bs = R.boot(X, y, [u["day"] for u in us], coef=j)
        print(f"covariável {nm} {b[j]:+.4f} [{np.percentile(bs, 2.5):+.4f}, {np.percentile(bs, 97.5):+.4f}]")
    Xs = R.design(us, lambda v: np.array([1.0 if u["razao"] > 0 else 0.0 for u in v]))
    bsec = ols_beta(Xs, y)[1]
    bss = R.boot(Xs, y, [u["day"] for u in us])
    print(f"secundária {bsec:+.4f} p unilateral centrado {np.mean(bss - bsec >= bsec):.4f}")


if __name__ == "__main__":
    main()
