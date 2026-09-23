"""Familia congelada de 17 hipoteses: BH 10% + BY (referencia conservadora),
planalto-vs-pico e split temporal 12-19/09 (ajuste) / 20-23/09 (teste)."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
import numpy as np
from stats69 import ABS_OF, PCT_VARS, bh, block_bootstrap, blocks, by, diff_means, load

a = json.load(open("a_res.json")); b = json.load(open("b_res.json"))
fam = [(r["label"], r["ptwo"]) for r in a] + [(r["label"], r["p"]) for r in b[:4]]
ps = [p for _, p in fam]
kb, kby = bh(ps, 0.10), by(ps, 0.10)
print(f"== FAMILIA CONGELADA: {len(fam)} hipoteses, FDR 10% ==")
order = np.argsort(ps)
for rank, i in enumerate(order, 1):
    print(f"{rank:3d}. {fam[i][0]:34} p={ps[i]:.3f}  limiar BH={rank/len(ps)*0.10:.4f}  "
          f"BH={'SOBREVIVE' if kb[i] else 'nao'}  BY={'SOBREVIVE' if kby[i] else 'nao'}")
print(f"\nmenor p = {min(ps):.3f}; limiar BH do primeiro posto (o mais restritivo) = {0.10/len(ps):.4f}")
print(f"sobrevivem BH: {sum(kb)}   sobrevivem BY: {sum(kby)}")

rows = load()
ret = np.array([r["ret"] for r in rows]); blk = blocks(rows)
fit = np.array([r["t"] < datetime.fromisoformat("2026-09-20T00:00:00+00:00") for r in rows])
print(f"\n== SPLIT TEMPORAL: ajuste n={fit.sum()} (12-19/09), teste n={(~fit).sum()} (20-23/09) ==")
print(f"{'variavel':26} {'melhor corte no ajuste':>22} {'D ajuste':>9} {'D teste':>9} {'IC95 teste':>20}")
GRID = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
for key, label in PCT_VARS:
    sel = [i for i, r in enumerate(rows) if r[key] != ""]
    idx = np.array(sel); p = np.array([float(rows[i][key]) for i in sel])
    f = fit[idx]; rr = ret[idx]; bb = blk[idx]
    best, bestd = None, -9
    for q in GRID:
        c = np.quantile(p[f], q)
        hi = p >= c
        if hi[f].all() or (~hi[f]).all():
            continue
        d = diff_means(rr[f], hi[f])
        if abs(d) > abs(bestd) or best is None:
            best, bestd = c, d
    hi = p >= best
    if hi[~f].all() or (~hi[~f]).all():
        print(f"{label:26} {best:22.3f} {bestd:+9.4f}   (teste degenerado)"); continue
    dt = diff_means(rr[~f], hi[~f])
    lo, up, _, _ = block_bootstrap(rr[~f], hi[~f], bb[~f])
    print(f"{label:26} {best:22.3f} {bestd:+9.4f} {dt:+9.4f} [{lo:+7.4f},{up:+7.4f}]")

print("\n== PLANALTO vs PICO (D por corte, so descritivo) ==")
print(f"{'variavel':26} " + " ".join(f"{q:>7.2f}" for q in GRID))
for key, label in PCT_VARS:
    sel = [i for i, r in enumerate(rows) if r[key] != ""]
    idx = np.array(sel); p = np.array([float(rows[i][key]) for i in sel]); rr = ret[idx]
    line = []
    for q in GRID:
        c = np.quantile(p, q); hi = p >= c
        line.append("   n/a" if hi.all() or (~hi).all() else f"{diff_means(rr, hi):+7.3f}")
    print(f"{label:26} " + " ".join(line))
