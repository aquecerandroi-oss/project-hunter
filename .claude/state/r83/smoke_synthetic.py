"""R83 — fumaça: desfechos SINTÉTICOS com efeito conhecido (+3·d_high + 0,2 + ruído) para provar o encanamento.
Não lê desfecho real. Escreve cache/out_synth.csv; depois: R83_OUT=out_synth.csv python run.py."""
import csv

import numpy as np
from h023 import CACHE, read_csv

rng = np.random.default_rng(7)
rows = read_csv(CACHE / "feat.csv")
with (CACHE / "out_synth.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["signal_id", "r_multiple", "r_ex_funding", "result", "exit_ts"])
    for r in rows:
        hi, c = r["hi24"], r["close_last"]
        d = (float(c) - float(hi)) / float(hi) if hi and c else 0.0
        y = 3 * d + 0.2 + rng.normal(0, 0.5)
        w.writerow([r["signal_id"], "" if r["has_r"] == "f" else f"{y:.6f}", f"{y:.6f}", "synthetic", ""])
