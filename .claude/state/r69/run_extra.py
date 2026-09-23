"""Complementos pedidos pela Astra na revisao do veredito:
(a) teste B ponderado por ENTRADA, nao por balde;
(b) indice composto dos 4 colineares, reproduzivel;
(c) concordancia percentil<->absoluto depois da correcao dos ausentes."""
from __future__ import annotations
import csv, json
from datetime import datetime, timedelta
import numpy as np
from scipy.stats import spearmanr
from stats69 import ABS_OF, PCT_VARS, block_bootstrap, blocks, diff_means, load

rows = load()
ret = np.array([r["ret"] for r in rows]); blk = blocks(rows)

print("== (c) concordancia percentil x absoluto (amostra corrigida) ==")
rhos = []
for k, lab in PCT_VARS:
    pv = [(float(r[k]), float(r[ABS_OF[k]])) for r in rows if r[k] != ""]
    rho = spearmanr([x for x, _ in pv], [y for _, y in pv]).statistic
    rhos.append(rho)
    print(f"  {lab:26} n={len(pv):4d} rho={rho:+.3f}")
print(f"  faixa {min(rhos):+.2f} a {max(rhos):+.2f}, mediana {np.median(rhos):+.2f}")

print("\n== (b) indice composto (media dos percentis de progresso, mcap, fluxo, volume) ==")
keys = ["p_prog", "p_mcap", "p_flow", "p_vol"]
ok = np.array([all(r[k] != "" for k in keys) for r in rows])
comp = np.array([np.mean([float(r[k]) for k in keys]) if o else np.nan for r, o in zip(rows, ok)])
i = np.isfinite(comp)
for q in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
    c = np.quantile(comp[i], q); hi = comp[i] >= c
    print(f"  corte q={q:.1f} (valor {c:.3f}): D={diff_means(ret[i], hi):+.4f}")
hi = comp[i] >= np.median(comp[i])
lo, up, _, p2 = block_bootstrap(ret[i], hi, blk[i])
print(f"  corte mediana: D={diff_means(ret[i], hi):+.4f} IC95 [{lo:+.4f},{up:+.4f}] p={p2:.3f} (n={i.sum()})")
fit = np.array([r["t"] < datetime.fromisoformat("2026-09-20T00:00:00+00:00") for r in rows])[i]
hif = comp[i] >= np.median(comp[i][fit])
print(f"  split: D ajuste {diff_means(ret[i][fit], hif[fit]):+.4f} | "
      f"D teste {diff_means(ret[i][~fit], hif[~fit]):+.4f} (n teste {(~fit).sum()})")

print("\n== (a) teste B ponderado por ENTRADA ==")
state = {datetime.fromisoformat(r["t0"]): r for r in csv.DictReader(open("state.csv", encoding="utf-8"))}
buck: dict[datetime, list[float]] = {}
for r in rows:
    t = r["t"]; t0 = t.replace(minute=(t.minute // 5) * 5, second=0, microsecond=0)
    buck.setdefault(t0, []).append(r["ret"])
for key in ("births_min", "frac_pos_flow", "med_prog_60_300", "grads_h", "live_n"):
    vals, rr, nn = [], [], []
    for t0, rs in sorted(buck.items()):
        s = state.get(t0)
        if s is None or s[key] == "":
            continue
        vals.append(float(s[key])); rr.append(rs); nn.append(len(rs))
    v = np.array(vals); cut = np.median(v); hi = v >= cut
    flat_hi = [x for j, rs in enumerate(rr) if hi[j] for x in rs]
    flat_lo = [x for j, rs in enumerate(rr) if not hi[j] for x in rs]
    print(f"  {key:18} corte {cut:8.3f} | quente {np.mean(flat_hi):+.6f} (n={len(flat_hi)}) | "
          f"frio {np.mean(flat_lo):+.6f} (n={len(flat_lo)}) | D={np.mean(flat_hi)-np.mean(flat_lo):+.6f}")
