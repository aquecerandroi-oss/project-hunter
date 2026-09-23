"""Teste B — o estado da coorte prediz o desfecho medio das entradas do balde?"""
from __future__ import annotations
import csv, json
from datetime import datetime, timedelta
import numpy as np
from stats69 import REPS, RNG, block_bootstrap, diff_means, load

BUCKET = timedelta(minutes=5)
STATE_VARS = [("births_min", "nascimentos/min"), ("frac_pos_flow", "fracao com fluxo positivo"),
              ("med_prog_60_300", "progresso mediano 60-300 s"), ("grads_h", "graduacoes/h")]

state = {}
for r in csv.DictReader(open("state.csv", encoding="utf-8")):
    state[datetime.fromisoformat(r["t0"])] = r

rows = load()
buckets: dict[datetime, list[float]] = {}
for r in rows:
    t = r["t"]
    t0 = t.replace(minute=(t.minute // 5) * 5, second=0, microsecond=0)
    buckets.setdefault(t0, []).append(r["ret"])

recs = []
for t0, rets in sorted(buckets.items()):
    s = state.get(t0)
    if s is None:
        continue
    recs.append(dict(t0=t0, n=len(rets), ret=float(np.mean(rets)), **{k: s[k] for k in
                ("live_n", "frac_pos_flow", "med_prog_60_300", "births_min", "grads_h", "med_buys")}))
print(f"baldes de 5 min com >= 1 entrada: {len(recs)} (de {len(buckets)} baldes com entrada); "
      f"entradas cobertas {sum(r['n'] for r in recs)} de {len(rows)}")
n_per = np.array([r["n"] for r in recs])
print(f"entradas por balde: media {n_per.mean():.2f}, max {n_per.max()}")
ret_b = np.array([r["ret"] for r in recs])
print(f"ret medio por balde (peso igual) {ret_b.mean():+.4f}; ponderado por entradas "
      f"{np.average(ret_b, weights=n_per):+.4f}")

t0min = min(r["t0"] for r in recs)
blk = np.array([int((r["t0"] - t0min) / timedelta(minutes=60)) for r in recs])
print(f"blocos de 60 min: {len(np.unique(blk))}")

out = []
for key, label in STATE_VARS + [("live_n", "tamanho da coorte (controle)"),
                                ("med_buys", "compras medianas da coorte (controle)")]:
    v = np.array([float(r[key]) if r[key] != "" else np.nan for r in recs])
    ok = ~np.isnan(v)
    if ok.sum() < 30:
        print(f"{label}: amostra insuficiente ({ok.sum()})"); continue
    cut = np.median(v[ok])
    hi = v >= cut
    d = diff_means(ret_b[ok], hi[ok])
    lo, up, _, ptwo = block_bootstrap(ret_b[ok], hi[ok], blk[ok])
    # quanto removeria e qual o retorno do braco quente
    hot = ret_b[ok][hi[ok]]; cold = ret_b[ok][~hi[ok]]
    nhot = n_per[ok][hi[ok]].sum(); ncold = n_per[ok][~hi[ok]].sum()
    out.append(dict(key=key, label=label, n=int(ok.sum()), cut=float(cut), d=float(d),
                    lo=lo, up=up, p=ptwo, ret_hot=float(hot.mean()), ret_cold=float(cold.mean()),
                    n_hot=int(nhot), n_cold=int(ncold)))

print(f"\n{'estado da coorte':34} {'nb':>4} {'corte':>8} {'ret_quente':>11} {'ret_frio':>9} "
      f"{'D':>8} {'IC95':>20} {'p':>6} {'entradas cortadas':>18}")
for r in out:
    print(f"{r['label']:34} {r['n']:4d} {r['cut']:8.3f} {r['ret_hot']:+11.4f} "
          f"{r['ret_cold']:+9.4f} {r['d']:+8.4f} [{r['lo']:+7.4f},{r['up']:+7.4f}] {r['p']:6.3f} "
          f"{r['n_cold']:6d}/{r['n_hot']+r['n_cold']:<6d}")
json.dump(out, open("b_res.json", "w"), default=float, indent=1)
