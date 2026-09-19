"""Population study on the paper-bet entries of the last 24 h: Everton rule vs Everton rule + 'first big sell' exit."""
import csv, math, sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
K = 30.0 * 1_073_000_000.0  # SOL * tokens (constant product of a fresh pump.fun curve)
FEE2 = 0.9875 ** 2
def ts(s):
    s = s.replace("+00", "+00:00") if s.endswith("+00") else s
    return datetime.fromisoformat(s)
tape = defaultdict(list)
with open("bet_trades.csv", newline="") as f:
    for r in csv.DictReader(f):
        p = float(r["price"]); sol = int(r["sol_lamports"]) / 1e9
        if p <= 0: continue
        vmid = math.sqrt(K * p)
        vbefore = vmid + sol / 2 if r["side"] == "sell" else vmid - sol / 2
        vafter = vmid - sol / 2 if r["side"] == "sell" else vmid + sol / 2
        tape[r["mint"]].append(dict(bt=ts(r["block_time"]), trader=r["trader"], side=r["side"], sol=sol, tok=float(r["token_amount"]), p=p, real_before=vbefore - 30, p_after=vafter * vafter / K))
bets = list(csv.DictReader(open("bets.csv", newline="")))
L = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
HOLD = 300
TRAIL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10

def price_at(T, i0, t):
    """price after the last trade with bt <= t, starting from index i0 (or entry price)."""
    p = None
    for r in T[i0:]:
        if r["bt"] <= t: p = r["p_after"]
        else: break
    return p

def run(bet, rule):
    T = tape[bet["mint"]]; entry = ts(bet["entry_at"])
    early = []
    for r in T:
        if r["side"] == "buy" and r["trader"] not in early: early.append(r["trader"])
        if len(early) >= 10: break
    i0 = next((i for i, r in enumerate(T) if r["bt"] >= entry), None)
    if i0 is None: return None
    if (T[i0]["bt"] - entry).total_seconds() > 5: return None  # no tape at entry
    p0 = T[i0]["p_after"]  # our fill ~ the first trade at/after entry
    peak = p0; window = []
    for r in T[i0 + 1:]:
        dt = (r["bt"] - entry).total_seconds()
        if dt > HOLD:
            pe = price_at(T, i0, entry + timedelta(seconds=HOLD + L)) or r["p"]
            return dict(reason="time", ratio=pe / p0 * FEE2, t=HOLD)
        p = r["p_after"]
        peak = max(peak, p)
        fired = None
        if p / p0 * FEE2 >= 1.15: fired = "target"
        elif TRAIL and p <= (1 - TRAIL) * peak: fired = "trailing"
        if rule and r["side"] == "sell":
            share = r["sol"] / r["real_before"] if r["real_before"] > 0.3 else 0
            window = [w for w in window if (r["bt"] - w[0]).total_seconds() <= rule.get("w", 3)] + [(r["bt"], share, r["trader"])]
            if rule["kind"] == "single" and share >= rule["x"]: fired = "bigsell"
            if rule["kind"] == "roll3" and sum(w[1] for w in window) >= rule["x"]: fired = "bigsell"
            if rule["kind"] == "cascade":
                sellers = {}
                for w in window: sellers[w[2]] = 1
                if len(sellers) >= rule["n"] and sum(w[1] for w in window) >= rule["x"]: fired = "cascade"
            if rule["kind"] == "early" and (r["trader"] in early or r["trader"] == bet["creator"]) and r["tok"] >= rule["y"] * 1e6: fired = "earlysell"
        if fired:
            pf = price_at(T, i0, r["bt"] + timedelta(seconds=L)) or p
            return dict(reason=fired, ratio=pf / p0 * FEE2, t=dt)
    last = T[-1]
    return dict(reason="censored", ratio=last["p_after"] / p0 * FEE2, t=(last["bt"] - entry).total_seconds())

rules = [None] + [dict(kind="single", x=x, name="single>=%d%%" % round(x * 100)) for x in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20)] \
      + [dict(kind="roll3", x=x, name="sum3s>=%d%%" % round(x * 100)) for x in (0.10, 0.15, 0.20)] \
      + [dict(kind="early", y=y, name="early>=%dM" % y) for y in (5, 10, 20)]       + [dict(kind="cascade", n=n, x=x, w=2, name="casc%d/2s>=%d%%" % (n, round(x * 100))) for n in (4, 6, 8) for x in (0.05, 0.10, 0.15)]
print("L=%s s; bets (unique mint+minute) = %d" % (L, len(bets)))
print("rule | n | mean pnl%% | median pnl%% | win%% | p10 | p90 | exits: target/trailing/time/bigsell/early/censored")
for rule in rules:
    res = [run(b, rule) for b in bets]
    res = [r for r in res if r]
    pn = sorted((r["ratio"] - 1) * 100 for r in res)
    n = len(pn)
    if n == 0: continue
    cnt = defaultdict(int)
    for r in res: cnt[r["reason"]] += 1
    print("%-14s| %d | %+.2f | %+.2f | %.0f%% | %+.1f | %+.1f | %s" % (rule["name"] if rule else "everton-only", n, sum(pn) / n, pn[n // 2], 100 * sum(1 for x in pn if x > 0) / n, pn[int(n * 0.1)], pn[int(n * 0.9)],
        " ".join("%s=%d" % kv for kv in sorted(cnt.items()))))
