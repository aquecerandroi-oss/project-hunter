"""R83 — a reconstrução (velas) contra a produção (feature_snapshots no minuto obs). Sem desfecho."""
from __future__ import annotations

import numpy as np
from blind import spearman
from h023 import CACHE, load_features, read_csv, ts

pop, _ = load_features()
by = {r["signal_id"]: r for r in pop}
snap = read_csv(CACHE / "snap.csv")
print("snapshots no minuto obs:", len(snap))
for key, sk in (("d_high", "s_dh"), ("d_low", "s_dl"), ("ret15", "s_r15"), ("ret240", "s_r4h")):
    pairs = [(by[s["signal_id"]][key], float(s[sk])) for s in snap
             if s["signal_id"] in by and by[s["signal_id"]][key] is not None and s[sk]]
    a, b = (np.array(x) for x in zip(*pairs, strict=True))
    diff = np.abs(a - b)
    print(f"{key}: n {len(pairs)} | idênticos (|Δ|<1e-12) {np.mean(diff < 1e-12):.4f} | "
          f"|Δ| p99 {np.percentile(diff, 99):.2e} máx {diff.max():.2e} | ρ {spearman(list(a), list(b)):.5f}")
    same_candle = [(by[s["signal_id"]][key], float(s[sk])) for s in snap if s["signal_id"] in by
                   and by[s["signal_id"]][key] is not None and s[sk] and ts(s["snap_candle_ts"]) == by[s["signal_id"]]["obs"]]
    a2, b2 = (np.array(x) for x in zip(*same_candle, strict=True))
    print(f"   só snapshots cuja última vela fecha em obs: n {len(same_candle)} idênticos {np.mean(np.abs(a2-b2) < 1e-12):.4f}")
# redundância com os valores de produção (momentum_15m e atr_14_pct ancorado), subconjunto
for fam in ("continuacao", "reversao"):
    for sk in ("s_mom15", "s_r4h", "s_r15", "s_atr"):
        pairs = [(by[s["signal_id"]]["d_high"], float(s[sk])) for s in snap if s["signal_id"] in by
                 and by[s["signal_id"]]["family"] == fam and by[s["signal_id"]]["d_high"] is not None and s[sk]]
        if len(pairs) > 30:
            a, b = zip(*pairs, strict=True)
            print(f"{fam} ρ(d_high, {sk} produção) = {spearman(list(a), list(b)):+.3f} (n {len(pairs)})")
# envelope return_15m (momentum) contra a reconstrução
pairs = [(r["ret15"], r["env_ret15"]) for r in pop if r["env_ret15"] is not None and r["ret15"] is not None]
d = np.abs(np.array([p[0] - p[1] for p in pairs]))
print(f"return_15m do envelope × reconstruído: n {len(pairs)} idênticos(<1e-12) {np.mean(d < 1e-12):.4f} máx {d.max():.2e}")
