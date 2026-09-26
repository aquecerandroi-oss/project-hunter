# R81 — contagem cega da variante adaptada E (janela [T−300, T) truncada no nascimento), sem desfechos.
from collections import Counter
from datetime import timedelta
import numpy as np
from r81 import first_per_mint, load_first, load_pop, load_trades, resolved, structure, ts
pop = load_pop(); first = load_first(); trades = load_trades()
P0 = [r for r in first_per_mint(pop) if resolved(r)]
TOL = timedelta(seconds=5)
rows, why = [], Counter()
for r in P0:
    T = ts(r["decided_at"]); c = ts(r["tok_created_at"]); fb, fs = first.get(r["mint"], (None, None))
    if fb is None:
        why["sem troca arquivada"] += 1; continue
    if fb > max(T - timedelta(seconds=300), c + TOL):
        why["arquivo começa depois do nascimento (+5 s) e depois de T−300"] += 1; continue
    s = structure(trades.get((r["mint"], T), []), T, fs if fb <= c + TOL else None)
    if s is None:
        why["janela vazia"] += 1; continue
    rows.append((r, s, (T - c).total_seconds()))
print("P_E:", len(rows), "excluídas", dict(why))
print("lanes", Counter(r["lane"] for r, _, _ in rows), "séries", Counter(r["series"] for r, _, _ in rows))
d = np.array([s.dist for _, s, _ in rows]); age = np.array([a for _, _, a in rows]); p = np.array([float(s.price_t) for _, s, _ in rows])
m = np.array([float(s.min5) for _, s, _ in rows])
print("dist quantis 0/10/25/33/50/67/75/90/100:", np.round(np.quantile(d, [0, .1, .25, 1/3, .5, 2/3, .75, .9, 1]), 3))
print("min5 (SOL/token) quantis 1/10/50/90/99:", np.quantile(m, [.01, .1, .5, .9, .99]))
def sp(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b)); return float(np.corrcoef(ra, rb)[0, 1])
print(f"Spearman dist × preço na decisão {sp(d, p):.3f}; dist × idade {sp(d, age):.3f}; preço × idade {sp(p, age):.3f}")
print("fundos_mais_altos", Counter(s.higher_lows for _, s, _ in rows), "(None = coin < 180 s ou minuto vazio)")
print("rompimento", Counter(s.breakout for _, s, _ in rows))
pr = [(float(r["p_dist"]), s.dist) for r, s, _ in rows if r["p_dist"]]
print("produção distance_to_support_pct presente:", len(pr), "; line_reason:", Counter(r["p_reason"] or "ok" for r, _, _ in rows if r["f_end"]), "sem linha 1m:", sum(not r["f_end"] for r, _, _ in rows))
if pr:
    a, b = np.array(pr).T; print(f"Spearman produção × bloco: {sp(a, b):.3f}")
