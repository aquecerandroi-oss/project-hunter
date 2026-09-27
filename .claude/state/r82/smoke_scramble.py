# R82 — cópia com PnL aleatório só para testar que h017_run.py roda (nenhum desfecho real é lido).
import csv
import random
import sys

random.seed(1)
src, dst = sys.argv[1], sys.argv[2]
with open(src, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
for r in rows:
    for k in ("arm_pnl", "ctl_pnl", "op_pnl"):
        if r[k]:
            r[k] = f"{random.uniform(-0.03, 0.02):.6f}"
with open(dst, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("ok", len(rows))
