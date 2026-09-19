import csv, math
from datetime import datetime, timedelta
from collections import defaultdict
K = 30.0 * 1_073_000_000.0
def ts(s):
    s = s.replace("+00", "+00:00") if s.endswith("+00") else s
    return datetime.fromisoformat(s)
tape = defaultdict(list)
with open("bet_trades.csv", newline="") as f:
    for r in csv.DictReader(f):
        p = float(r["price"]); sol = int(r["sol_lamports"]) / 1e9
        if p <= 0: continue
        vmid = math.sqrt(K * p)
        vb = vmid + sol / 2 if r["side"] == "sell" else vmid - sol / 2
        va = vmid - sol / 2 if r["side"] == "sell" else vmid + sol / 2
        tape[r["mint"]].append(dict(bt=ts(r["block_time"]), side=r["side"], sol=sol, real_before=vb - 30, p_after=va * va / K, trader=r["trader"]))
created = {r["mint"]: ts(r["created_at"]) for r in csv.DictReader(open("bets.csv", newline=""))}
def p_at(T, i, t):
    p = T[i]["p_after"]
    for r in T[i + 1:]:
        if r["bt"] <= t: p = r["p_after"]
        else: break
    return p
print("sells in the first 10 min of life, real_sol >= 3 SOL; outcome = price at +60 s vs price at +2 s (our fill)")
print("band | n | median chg%% | mean | P(down) | P(< -10%%) | P(> +10%%) | median chg at +15s")
bands = [(0.02, 0.05), (0.05, 0.08), (0.08, 0.12), (0.12, 0.20), (0.20, 1.0)]
rows = defaultdict(list)
for m, T in tape.items():
    c = created.get(m)
    for i, r in enumerate(T):
        if r["side"] != "sell" or r["real_before"] < 3: continue
        if c and (r["bt"] - c).total_seconds() > 600: continue
        share = r["sol"] / r["real_before"]
        for lo, hi in bands:
            if lo <= share < hi:
                pf = p_at(T, i, r["bt"] + timedelta(seconds=2))
                p60 = p_at(T, i, r["bt"] + timedelta(seconds=60))
                p15 = p_at(T, i, r["bt"] + timedelta(seconds=15))
                rows[(lo, hi)].append((p60 / pf - 1, p15 / pf - 1))
for b in bands:
    v = sorted(x[0] for x in rows[b]); v15 = sorted(x[1] for x in rows[b]); n = len(v)
    if not n: continue
    print("%2.0f-%3.0f%% | %d | %+.1f | %+.1f | %.0f%% | %.0f%% | %.0f%% | %+.1f" % (b[0] * 100, b[1] * 100, n, 100 * v[n // 2], 100 * sum(v) / n, 100 * sum(1 for x in v if x < 0) / n, 100 * sum(1 for x in v if x < -0.1) / n, 100 * sum(1 for x in v if x > 0.1) / n, 100 * v15[n // 2]))
