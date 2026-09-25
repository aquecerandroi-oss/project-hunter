# Contagem cega ao desfecho: quantas decisões resolvidas com fita completa.
from collections import Counter

import numpy as np

from h019 import accel, complete, first_per_mint, load

rows = load()
print("apostas:", len(rows), Counter((r["lane"], r["rs"]) for r in rows))
print("com fita:", sum(r["has_tape"] for r in rows), "| tape_reason:", Counter(r["tape_reason"] for r in rows if r["has_tape"]))
print("janelas 10s/60s ausentes (com fita):", sum(1 for r in rows if r["has_tape"] and not r["tape_reason"] and accel(r["winj"]) is None))
fp = first_per_mint([r for r in rows if r["has_tape"]])
print("mints (1.ª decisão com fita):", len(fp), Counter(r["rs"] + "/" + r["lane"] for r in fp))
ok = [r for r in fp if complete(r)]
res = [r for r in ok if r["resolved"]]
print("fita completa:", len(ok), "| resolvidas:", len(res), "| não resolvidas:", Counter((r["status"], r["oq"]) for r in ok if not r["resolved"]))
print("gaps>0 entre as resolvidas:", sum(int(r["gaps"] or 0) > 0 for r in res))
x = np.array([accel(r["winj"]) for r in res]); xn = np.array([accel(r["winj"], "buys") for r in res])
print("acc SOL quantis 0/10/25/33/50/67/75/90/100:", np.round(np.quantile(x, [0, .1, .25, 1/3, .5, 2/3, .75, .9, 1]), 3), "zeros", int((x == 0).sum()))
print("acc n   quantis:", np.round(np.quantile(xn, [0, .1, .25, 1/3, .5, 2/3, .75, .9, 1]), 3), "zeros", int((xn == 0).sum()))
print("por dia:", Counter(r["features_end_time"][:10] for r in res), "por lane:", Counter(r["lane"] for r in res))
