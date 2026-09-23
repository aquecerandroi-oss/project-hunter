"""Teste A — o percentil separa onde o absoluto falhou?"""
from __future__ import annotations
import numpy as np
from stats69 import (ABS_OF, PCT_VARS, RNG, bh, block_bootstrap, blocks, by,
                     diff_means, load, perm_p)

rows = load()
print(f"n = {len(rows)} moedas (uma aposta por mint, flow_v2, medidas, idade <= 300 s)")
ret_all = np.array([r["ret"] for r in rows])
print(f"ret medio {ret_all.mean():+.4f}  mediana {np.median(ret_all):+.4f}  "
      f"positivas {100*(ret_all>0).mean():.1f}%")
blk_all = blocks(rows)
day_all = np.array([r["t"].date().isoformat() for r in rows])
print(f"blocos de 60 min: {len(np.unique(blk_all))}; dias: {len(np.unique(day_all))}")

res = []
for key, label in PCT_VARS:
    sel = [r for r in rows if r[key] != ""]
    idx = np.array([i for i, r in enumerate(rows) if r[key] != ""])
    # amostra identica para as duas versoes (Astra): o percentil ja foi anulado em load()
    # quando o absoluto do sujeito falta, logo `sel` e a amostra comum.
    ret = ret_all[idx]; blk = blk_all[idx]; day = day_all[idx]
    p = np.array([float(r[key]) for r in sel])
    hi = p >= np.median(p)
    if hi.all():
        hi = p > np.median(p)
    d = diff_means(ret, hi)
    lo, up, ple0, ptwo = block_bootstrap(ret, hi, blk)
    pp = perm_p(ret, hi, day)
    # versao ABSOLUTA da mesma variavel, mesma amostra, corte na mediana da amostra
    acol = ABS_OF[key]
    av = np.array([float(r[acol]) for r in sel])
    ok = np.ones(len(av), dtype=bool)
    med = np.median(av[ok])
    ahi = av > med if (av[ok] >= med).all() else av >= med
    if ahi[ok].all() or (~ahi[ok]).all():
        da, patwo = float("nan"), float("nan")
    else:
        da = diff_means(ret[ok], ahi[ok])
        _, _, _, patwo = block_bootstrap(ret[ok], ahi[ok], blk[ok])
    # tercis (planalto vs pico, descritivo)
    q1, q3 = np.percentile(p, [33.333, 66.667])
    lo3, hi3 = p <= q1, p >= q3
    d3 = float(ret[hi3].mean() - ret[lo3].mean()) if hi3.any() and lo3.any() else float("nan")
    res.append(dict(key=key, label=label, n=len(sel), n_hi=int(hi.sum()), d=d, lo=lo, up=up,
                    d3=d3, cut=float(np.median(p)),
                    ple0=ple0, ptwo=ptwo, pperm=pp, d_abs=da, p_abs=patwo))

# controles aleatorios (nao entram na familia)
ctrl = []
for key in ("p_rnd1", "p_rnd2"):
    p = np.array([float(r[key]) for r in rows]); hi = p >= np.median(p)
    d = diff_means(ret_all, hi)
    lo, up, _, ptwo = block_bootstrap(ret_all, hi, blk_all)
    ctrl.append((key, d, lo, up, ptwo))

print("\n== TESTE A: percentil na coorte (alto >= P50) vs absoluto (mediana da amostra) ==")
print(f"{'variavel':26} {'n':>4} {'corte':>6} {'D_pct':>8} {'IC95 pct':>20} {'p_boot':>7} "
      f"{'p_perm':>7} {'D_t3':>8} {'D_abs':>8} {'p_abs':>7}")
for r in res:
    print(f"{r['label']:26} {r['n']:4d} {r['cut']:6.3f} {r['d']:+8.4f} "
          f"[{r['lo']:+7.4f},{r['up']:+7.4f}] {r['ptwo']:7.3f} {r['pperm']:7.3f} "
          f"{r['d3']:+8.4f} {r['d_abs']:+8.4f} {r['p_abs']:7.3f}")
print("\ncontroles aleatorios (estaveis por mint, mesma maquina):")
for k, d, lo, up, ptwo in ctrl:
    print(f"  {k}: D={d:+.4f} IC95 [{lo:+.4f},{up:+.4f}] p={ptwo:.3f}")

ps = [r["ptwo"] for r in res]
print(f"\nBH 10% sobre a familia de 17 (13 percentis + 4 estados; estados no run_b):")
print("  (a decisao BH/BY final e tomada em run_family.py com os 17 p juntos)")
np.save("a_p.npy", np.array(ps))
import json
json.dump(res, open("a_res.json", "w"), default=float, indent=1)
