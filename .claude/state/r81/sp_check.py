# postos médios (empates) para o Spearman da variante E — cego
from collections import Counter
import numpy as np
exec(open("blind_e.py", encoding="utf-8").read().split("def sp(")[0])
def avg_rank(a):
    a = np.asarray(a); order = np.argsort(a, kind="mergesort"); r = np.empty(len(a)); r[order] = np.arange(len(a), dtype=float)
    for v in np.unique(a):
        m = a == v
        if m.sum() > 1: r[m] = r[m].mean()
    return r
print("Spearman (postos médios) dist × preço:", round(float(np.corrcoef(avg_rank(d), avg_rank(p))[0, 1]), 3))
print("por dia UTC, primeiras decisões resolvidas:", sorted(Counter(r["decided_at"][:10] for r in P0).items()))
