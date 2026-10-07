"""h036 — calibração fina de P_REF (REFUTA indevido com θ = +0,10), mesma semente e caminhos de run_design2."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import run_design2 as rd
res, ext, _ = rd.pool()
rng = np.random.default_rng(rd.SEED)
sims = {s: rd.paths(res, ext, s, rng) for s in ("S1", "S2", "S3", "S4", "S5")}
for pr in (0.995, 0.9975, 0.999):
    b = {s: rd.run(*sims[s], 0.10, alpha_final=0.024, p_ref=pr)["REFUTA"] for s in sims}
    print(f"P_REF {pr}: P(REFUTA | θ=+0,10) " + " · ".join(f"{s} {v:.4f}" for s, v in b.items()))
