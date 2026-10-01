"""R86 — fumaça SINTÉTICA (desfecho inventado, rotulado): o encanamento confirma um efeito injetado e não um nulo.

Usa as covariáveis REAIS das unidades elegíveis (cegas) e troca R_net por um desfecho sintético de efeito conhecido.
cd .claude/state/r86 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python smoke86.py
"""

from __future__ import annotations

import csv

import numpy as np
from analysis86 import analyze, label, render, scales
from data86 import CACHE, feature_rows, guard_window, load_daily, units


def main() -> None:
    rows, _ = feature_rows(load_daily())
    kept, _ = guard_window(rows)
    with (CACHE / "eligible.csv").open(encoding="utf-8") as fh:
        elig = {r["signal_id"] for r in csv.DictReader(fh)}
    mom = [dict(r, r=0.0) for r in kept if r["signal_id"] in elig and r["strategy"] == "momentum"]
    us = units(mom)
    sc = scales(us)
    rng = np.random.default_rng(7)
    print("# FUMAÇA SINTÉTICA — desfechos inventados, nada aqui é resultado")
    for name, beta, b0 in (("SINTÉTICO efeito +0,25 R/desvio, nível +0,10", 0.25, 0.10),
                           ("SINTÉTICO nulo (β = 0, nível −0,20)", 0.0, -0.20),
                           ("SINTÉTICO nulo 2 (β = 0, nível +0,10)", 0.0, 0.10)):
        syn = []
        for u in us:
            z = (u["razao"] - sc["razao"][0]) / sc["razao"][1]
            syn.append(dict(u, r=float(b0 + beta * z + rng.normal(scale=1.2))))
        res = analyze(syn, reps=2000)
        lab = label(res, min(1.0, 2 * res["p_raw"]))
        print("\n".join(render(name, res, lab, min(1.0, 2 * res["p_raw"]))))


if __name__ == "__main__":
    main()
