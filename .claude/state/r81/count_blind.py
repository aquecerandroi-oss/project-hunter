# R81 — contagem cega (sem desfechos): população, cobertura, distribuição das variáveis.
# cd .claude/state/r81 && PYTHONIOENCODING=utf-8 uv run --project C:/dev/project-hunter python count_blind.py
from collections import Counter

import numpy as np

from r81 import covered, first_per_mint, load_first, load_pop, load_trades, resolved, structure, ts

pop = load_pop()
first = load_first()
trades = load_trades()
fp = first_per_mint(pop)
P0 = [r for r in fp if resolved(r)]
print(f"apostas {len(pop)}; mints {len(fp)}; 1.ª por mint resolvidas {len(P0)}")
print("por lane", Counter(r["lane"] for r in P0), "série", Counter(r["series"] for r in P0))

rows = []
why = Counter()
for r in P0:
    T = ts(r["decided_at"])
    fb, fs = first.get(r["mint"], (None, None))
    if not covered(fb, T):
        why["fita arquivada começa depois de T−300 s (ou sem troca)"] += 1
        continue
    tt = trades.get((r["mint"], T), [])
    s = structure(tt, T, fs)
    if s is None:
        why["janela de 5 min vazia"] += 1
        continue
    sk = structure(tt, T, fs, received_before_decision=True)
    rows.append((r, s, sk))
print("excluídas:", dict(why))
print(f"P (1.ª por mint, resolvida, 5 min de fita): {len(rows)}  — limite do bloco 150")
print("por lane", Counter(r["lane"] for r, _, _ in rows), "série", Counter(r["series"] for r, _, _ in rows))
print("rule sets", Counter(r["rs"] for r, _, _ in rows).most_common())
print("por dia", sorted(Counter(r["decided_at"][:10] for r, _, _ in rows).items()))
age = np.array([(ts(r["decided_at"]) - ts(r["tok_created_at"])).total_seconds() / 60 for r, _, _ in rows if r["tok_created_at"]])
age_all = np.array([(ts(r["decided_at"]) - ts(r["tok_created_at"])).total_seconds() / 60 for r in P0 if r["tok_created_at"]])
print("idade na decisão (min), P0 quantis 10/25/50/75/90:", np.round(np.quantile(age_all, [.1, .25, .5, .75, .9]), 1))
print("idade na decisão (min), P  quantis 10/25/50/75/90:", np.round(np.quantile(age, [.1, .25, .5, .75, .9]), 1))
d = np.array([s.dist for _, s, _ in rows])
print("dist quantis 0/10/25/33/50/67/75/90/100:", np.round(np.quantile(d, [0, .1, .25, 1 / 3, .5, 2 / 3, .75, .9, 1]), 4))
print("zeros (última = mínimo):", int((d == 0).sum()))
print("n na janela quantis 10/50/90:", np.quantile([s.n_window for _, s, _ in rows], [.1, .5, .9]))
print("fundos_mais_altos:", Counter(s.higher_lows for _, s, _ in rows))
print("rompimento:", Counter(s.breakout for _, s, _ in rows))
k = [x for _, _, x in rows]
print(f"sensibilidade received_at < T: com valor {sum(x is not None for x in k)} de {len(rows)}")
same = sum(1 for _, s, x in rows if x is not None and x.dist == s.dist)
print(f"   mesma distância que o oráculo: {same}")
lag = np.array([(s.last_recv - ts(r["decided_at"])).total_seconds() for r, s, _ in rows])
print("maior received_at das trocas usadas − T (s), quantis 10/50/90:", np.round(np.quantile(lag, [.1, .5, .9]), 1),
      "; fração com alguma troca recebida depois de T:", round(float((lag >= 0).mean()), 3))
pd_ = [r for r, _, _ in rows if r["p_dist"]]
print(f"produção (meme_features_1m, end_time ≤ T e computed_at ≤ T): linha {sum(bool(r['f_end']) for r, _, _ in rows)}, "
      f"distance_to_support_pct {len(pd_)}; line_reason", Counter(r["p_reason"] for r, _, _ in rows if r["f_end"]))
