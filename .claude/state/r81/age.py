from collections import Counter
import numpy as np
from r81 import first_per_mint, load_pop, load_first, resolved, ts
pop = load_pop(); first = load_first()
P0 = [r for r in first_per_mint(pop) if resolved(r)]
age = np.array([(ts(r["decided_at"]) - ts(r["tok_created_at"])).total_seconds() for r in P0 if r["tok_created_at"]])
print("n com created_at", age.size, "de", len(P0))
for c in (120, 180, 240, 270, 300, 360, 600):
    print(f"idade >= {c} s: {(age >= c).sum()}")
print("máx idade (s)", age.max().round(1), "quantis 95/99", np.quantile(age, [.95, .99]).round(1))
gap = np.array([(first[r["mint"]][0] - ts(r["tok_created_at"])).total_seconds() for r in P0 if r["tok_created_at"] and first.get(r["mint"], (None,))[0]])
print("1.ª troca arquivada − created_at (s) quantis 10/50/90/99:", np.quantile(gap, [.1, .5, .9, .99]).round(1))
allb = [r for r in pop]
agea = np.array([(ts(r["decided_at"]) - ts(r["tok_created_at"])).total_seconds() for r in allb if r["tok_created_at"]])
print("todas as apostas (não só 1.ª):", agea.size, "idade >= 300 s:", (agea >= 300).sum())
print("por rule set, idade máx (s):", {k: round(max((ts(r["decided_at"]) - ts(r["tok_created_at"])).total_seconds() for r in allb if r["rs"] == k and r["tok_created_at"]), 1) for k in sorted({r["rs"] for r in allb})})
