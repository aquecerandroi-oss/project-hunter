import csv, json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
VSOL0 = 30_000_000_000
FEE = Decimal("0.0125")
BRT = timezone(timedelta(hours=-3))
def ts(s):
    s = s.replace("+00", "+00:00") if s.endswith("+00") else s
    return datetime.fromisoformat(s)
def brt(d): return d.astimezone(BRT).strftime("%H:%M:%S")
trades = {}
with open("trades.csv", newline="") as f:
    for r in csv.DictReader(f):
        r["bt"] = ts(r["block_time"]); r["slot"] = int(r["slot"]); r["ei"] = int(r["event_index"])
        r["sol"] = int(r["sol_lamports"]); r["tok"] = int(Decimal(r["token_amount"]) * 10**6)
        trades.setdefault(r["mint"], []).append(r)
for m in trades: trades[m].sort(key=lambda r: (r["slot"], r["signature"], r["ei"]))
def net(vsol, vtok, amount):
    p = vsol - (vsol * vtok) // (vtok + amount)
    return int(Decimal(p) * (1 - FEE))

positions = json.load(open("positions.json"))
paths = {}
for P in positions:
    T = trades[P["mint"]]
    early = []
    for r in T:
        if r["side"] == "buy" and r["trader"] not in early: early.append(r["trader"])
        if len(early) >= 10: break
    idx = next((i for i, r in enumerate(T) if r["slot"] == P["entry_slot"] and r["trader"] == OUR and r["side"] == "buy"), None)
    if idx is None: paths[P["tag"]] = None; continue
    vsol, vtok = P["vsol_after"], P["vtok_after"]; tokens = P["tokens"]
    entry_bt = ts(P["entry_bt"]); exit_bt = ts(P["exit_bt"])
    path = []  # (bt, vsol, vtok, mark, trade or None)
    path.append((entry_bt, vsol, vtok, net(vsol, vtok, tokens), None, 0.0, ""))
    for r in T[idx + 1:]:
        if r["trader"] == OUR: continue  # hold path: skip our own sell
        real_before = vsol - VSOL0
        if r["side"] == "buy": vsol += r["sol"]; vtok -= r["tok"]
        else: vsol -= r["sol"]; vtok += r["tok"]
        share = r["sol"] / real_before
        flag = ""
        if r["side"] == "sell":
            if r["trader"] == P["creator"]: flag = "creator"
            elif r["trader"] in early: flag = "early%d" % (early.index(r["trader"]) + 1)
        path.append((r["bt"], vsol, vtok, net(vsol, vtok, tokens), r, share, flag))
    paths[P["tag"]] = path

def fill_after(path, t, tokens):
    """net proceeds after all trades with bt <= t (our sell lands at t)."""
    last = path[0]
    for p in path:
        if p[0] <= t: last = p
        else: break
    return net(last[1], last[2], tokens), last[0]

def simulate(P, rule, L):
    path = paths[P["tag"]]
    if path is None: return None
    exit_bt = ts(P["exit_bt"]); tokens = P["tokens"]
    window = []
    for p in path[1:]:
        bt, vsol, vtok, mark, r, share, flag = p
        if bt >= exit_bt: break  # position already closed by the real rule (same second counts as closed)
        if r["side"] != "sell": continue
        window = [w for w in window if (bt - w[0]).total_seconds() <= 3] + [(bt, share)]
        fired = False
        if rule["kind"] == "single" and share >= rule["x"]: fired = True
        if rule["kind"] == "roll3" and sum(w[1] for w in window) >= rule["x"]: fired = True
        if rule["kind"] == "early" and flag and r["tok"] >= rule["y"] * 10**6 * 10**6: fired = True
        if rule["kind"] == "single_or_early" and (share >= rule["x"] or (flag and r["tok"] >= rule["y"] * 10**6 * 10**6)): fired = True
        if fired:
            land = bt + timedelta(seconds=L)
            if land >= exit_bt: return None  # would land after/at the real exit -> no change
            fill, at = fill_after(path, land, tokens)
            return dict(trigger=bt, trigger_mark=mark, share=share, flag=flag, trader=r["trader"][:6], sol=r["sol"], tok=r["tok"], land=land, fill=fill)
    return None

rules = []
for x in (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15):
    rules.append(dict(kind="single", x=x, name="single>=%d%%" % round(x * 100)))
for x in (0.08, 0.10, 0.12, 0.15, 0.20):
    rules.append(dict(kind="roll3", x=x, name="sum3s>=%d%%" % round(x * 100)))
for y in (1, 5, 10, 20, 30):
    rules.append(dict(kind="early", y=y, name="early>=%dM" % y))
for x in (0.08, 0.10, 0.12, 0.15):
    for y in (10, 20, 30):
        rules.append(dict(kind="single_or_early", x=x, y=y, name="single>=%d%%|early>=%dM" % (round(x * 100), y)))

import sys
L = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
print("latency L =", L, "s (block of the sell -> our landing)")
actual_total = sum(P["exit_net"] - P["spent"] for P in positions)
print("ACTUAL total pnl SOL %.4f" % (actual_total / 1e9))
hdr = ["rule", "total", "delta"] + [P["tag"] for P in positions]
print("|".join(hdr))
detail = {}
for rule in rules:
    tot = 0; cells = []
    for P in positions:
        s = simulate(P, rule, L)
        if s is None:
            pnl = P["exit_net"] - P["spent"]; cells.append("%+.1f%%" % (pnl / P["spent"] * 100))
        else:
            pnl = s["fill"] - P["spent"]; cells.append("%+.1f%%*" % (pnl / P["spent"] * 100))
            detail.setdefault(rule["name"], {})[P["tag"]] = s
        tot += pnl
    print("|".join([rule["name"], "%.4f" % (tot / 1e9), "%+.4f" % ((tot - actual_total) / 1e9)] + cells))
print()
for name in ("single>=5%", "single>=8%", "single>=10%", "single>=12%", "sum3s>=12%", "early>=10M", "early>=20M", "single>=10%|early>=20M", "single>=12%|early>=20M"):
    print("--", name)
    for tag, s in detail.get(name, {}).items():
        P = next(p for p in positions if p["tag"] == tag)
        print("   %-10s trig %s %s %s sol %.3f (%.1f%%) tok %.1fM mark_after_sell %.4f -> land %s fill %.4f (pnl %+.1f%% vs real %+.1f%%)" % (
            tag, brt(s["trigger"]), s["trader"], s["flag"], s["sol"] / 1e9, s["share"] * 100, s["tok"] / 1e12, s["trigger_mark"] / 1e9, brt(s["land"]), s["fill"] / 1e9, (s["fill"] / P["spent"] - 1) * 100, (P["exit_net"] / P["spent"] - 1) * 100))
