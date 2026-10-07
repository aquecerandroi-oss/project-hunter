"""R90 — fumaça SINTÉTICA (rotulada): covariáveis e x reais das unidades da momentum, desfecho INVENTADO.
Efeito injetado de +0,25 R por desvio de x deve sair CONFIRMA-compatível; dois nulos devem sair NÃO CONFIRMA/REFUTA.
Nenhum desfecho real é lido.

cd .claude/state/r90 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python smoke90.py
"""

from __future__ import annotations

import numpy as np
from analysis90 import analyze, label, scales
from freeze90 import build, complete
from data90 import units


def main() -> None:
    rows = [dict(r, r=0.0) for r in build(15) if complete(r) and r["strategy"] == "momentum"]
    us = units(rows)
    sc = scales(us)
    zx = (np.array([u["x"] for u in us]) - sc["x"][0]) / sc["x"][1]
    for name, beta, seed in (("SINTÉTICO efeito +0,25", 0.25, 1), ("SINTÉTICO nulo A", 0.0, 2), ("SINTÉTICO nulo B", 0.0, 3)):
        rng = np.random.default_rng(seed)
        y = 0.3 + beta * zx + rng.normal(scale=1.2, size=len(us))
        fake = [dict(u, r=float(v)) for u, v in zip(us, y, strict=True)]
        res = analyze(fake, reps=1000, robust=False)
        lab = label(res, min(1.0, 2 * res["p_raw"]))
        print(f"{name}: β_x {res['beta']:+.4f} IC dia [{res['lo']:+.4f}, {res['hi']:+.4f}] IC mercado "
              f"[{res['lo_m']:+.4f}, {res['hi_m']:+.4f}] → {lab.label}")  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
