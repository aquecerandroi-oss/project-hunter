# R80 — contagem cega (sem desfechos): cobertura, reuso, formato dos links.
from collections import Counter
import numpy as np
from r80 import TokenIndex, first_per_mint, load_pop, load_tokens, resolved, ts

toks = load_tokens()
print("tokens", len(toks), "com twitter", sum(1 for t in toks if t["twitter"]))
idx = TokenIndex(toks)
kinds = Counter(t.kind for t in idx.tok.values() if t.key)
print("tipos de link (universo)", kinds.most_common())
top = Counter(t.key for t in idx.tok.values() if t.key).most_common(15)
print("chaves mais repetidas (universo inteiro, 11/09+):", top)
pop = load_pop()
print("linhas", len(pop), Counter((r["lane"], r["status"], r["oq"]) for r in pop).most_common(12))
P = first_per_mint(pop)
print("mints (1.a por mint)", len(P), "resolvidas", sum(resolved(r) for r in P))
by_day = {}
for r in P:
    if not resolved(r):
        continue
    T = ts(r["decided_at"]); d = str(T.date())
    own = idx.has_twitter(r["mint"]) is not None
    cov = idx.coverage(T)
    reu = idx.reuse(r["mint"], T)
    reu_k = idx.reuse(r["mint"], T, known_only=True)
    s = by_day.setdefault(d, {"n": 0, "own": 0, "cov": [], "legivel": 0, "reuse1": 0, "reuse1_k": 0, "semsoc": 0})
    s["n"] += 1; s["own"] += own; s["cov"].append(cov or 0)
    leg = own and cov is not None and cov >= 0.60
    s["legivel"] += leg
    if leg:
        s["reuse1"] += (reu or 0) >= 1; s["reuse1_k"] += (reu_k or 0) >= 1; s["semsoc"] += idx.has_twitter(r["mint"]) is False
tot = Counter()
print("dia | n | própria legível | cobertura 24h (mediana, mín) | legível (própria e cob>=0,60) | reuso>=1 | reuso>=1 (só o que a base sabia) | sem_social")
for d in sorted(by_day):
    s = by_day[d]
    print(d, s["n"], s["own"], f"{np.median(s['cov']):.3f} {min(s['cov']):.3f}", s["legivel"], s["reuse1"], s["reuse1_k"], s["semsoc"])
    for k in ("n", "own", "legivel", "reuse1", "reuse1_k", "semsoc"):
        tot[k] += s[k]
print("TOTAL", dict(tot))
