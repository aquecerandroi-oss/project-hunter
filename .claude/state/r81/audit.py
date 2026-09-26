# R81 — auditoria CEGA do instrumento (sem desfechos): criação, continuidade, ordem, preço, disponibilidade em T.
import csv
from collections import Counter
from datetime import timedelta
import numpy as np
from r81 import first_per_mint, load_first, load_pop, load_trades, resolved, structure, ts

first = load_first(); trades = load_trades(); pop = load_pop()
A = list(csv.DictReader(open("cache/audit.csv", encoding="utf-8")))
print(f"# A. fita da decisão × arquivo (pista de eventos, 1.ª proposta por mint com fita): {len(A)}")
tw = np.array([int(r["trades_in_window"]) for r in A]); ar = np.array([int(r["arch_60"]) for r in A]); ak = np.array([int(r["arch_60_known"]) for r in A])
ratio = ar / np.maximum(tw, 1)
print(f"   trocas no minuto julgado: fita ao vivo mediana {np.median(tw):.0f}; arquivo (block_time) mediana {np.median(ar):.0f};"
      f" arquivo/fita quantis 10/25/50/75/90 {np.round(np.quantile(ratio, [.1, .25, .5, .75, .9]), 2)}")
print(f"   arquivo com ≥ 90 % das trocas do minuto: {(ratio >= 0.9).mean():.1%}; < 50 %: {(ratio < 0.5).mean():.1%}")
print(f"   arquivo recebido até o as_of (o que a base tinha): mediana {np.median(ak):.0f}; zero em {(ak == 0).mean():.1%} das decisões")
cs = [(r["mint"], r["tape_cslot"]) for r in A if r["tape_cslot"]]
m = Counter("igual" if first.get(mi, (None, None))[1] == int(s) else ("sem arquivo" if first.get(mi, (None, None))[1] is None else "diferente") for mi, s in cs)
print(f"   slot de criação da fita (inferido ao vivo) × slot da 1.ª troca arquivada: {dict(m)} (fita com slot: {len(cs)} de {len(A)})")
sn = np.array([int(r["snaps_5m_known"]) for r in A]); s1 = np.array([int(r["snaps_1m_known"]) for r in A])
print(f"   fotos da curva recebidas antes de T: últimos 5 min mediana {np.median(sn):.0f} (p10 {np.quantile(sn, .1):.0f}); último minuto mediana {np.median(s1):.0f};"
      f" < 5 fotos em 5 min: {(sn < 5).mean():.1%}")

print("\n# B. último slot ambíguo (P0 1.ª por mint resolvida, trocas block_time < T)")
P0 = [r for r in first_per_mint(pop) if resolved(r)]
amb = tot = 0; gaps = []
for r in P0:
    T = ts(r["decided_at"]); tt = [t for t in trades.get((r["mint"], T), []) if T - timedelta(seconds=300) <= t.block_time < T]
    if not tt:
        continue
    tot += 1
    last_slot = max(t.slot for t in tt)
    ps = {t.price for t in tt if t.slot == last_slot}
    if len(ps) > 1:
        amb += 1
        gaps.append(float(max(ps) / min(ps) - 1))
print(f"   decisões com troca na janela {tot}; último slot com > 1 preço distinto: {amb} ({amb / tot:.1%}); amplitude mediana {np.median(gaps):.3f}" if gaps else "")
