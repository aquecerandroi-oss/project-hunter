import csv, json, sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
VSOL0 = 30_000_000_000
FEE = Decimal("0.0125")
BRT = timezone(timedelta(hours=-3))

def ts(s):
    s = s.replace("+00", "+00:00") if s.endswith("+00") else s
    return datetime.fromisoformat(s)

def brt(d):
    return d.astimezone(BRT).strftime("%H:%M:%S.%f")[:-3]

trades = {}
with open("trades.csv", newline="") as f:
    for r in csv.DictReader(f):
        r["bt"] = ts(r["block_time"]); r["rcv"] = ts(r["received_at"])
        r["slot"] = int(r["slot"]); r["ei"] = int(r["event_index"])
        r["sol"] = int(r["sol_lamports"]); r["tok"] = int(Decimal(r["token_amount"]) * 10**6)
        trades.setdefault(r["mint"], []).append(r)
for m in trades:
    trades[m].sort(key=lambda r: (r["slot"], r["signature"], r["ei"]))

def proceeds(vsol, vtok, amount):
    return vsol - (vsol * vtok) // (vtok + amount)

def net(vsol, vtok, amount):
    p = proceeds(vsol, vtok, amount)
    return int(Decimal(p) * (1 - FEE))

positions = json.load(open("positions.json"))
out = []
summary = []
for P in positions:
    T = trades[P["mint"]]
    entry_bt = ts(P["entry_bt"]); exit_bt = ts(P["exit_bt"])
    # early wallets: first 10 distinct buyers from birth
    early = []
    for r in T:
        if r["side"] == "buy" and r["trader"] not in early:
            early.append(r["trader"])
        if len(early) >= 10: break
    early_set = set(early)
    # first buys count by trader (for info)
    # anchor: our entry fill
    idx = next((i for i, r in enumerate(T) if r["slot"] == P["entry_slot"] and r["trader"] == OUR and r["side"] == "buy"), None)
    if idx is None:
        print("NO TAPE ANCHOR for", P["tag"], "last tape trade", T[-1]["bt"]); P.update(_rows=[], _early=early, _peak=(0, entry_bt), _trail=None, _target=None, _big=[], _val=None, _post_max=None, _mark0=0, _exit_state=None); out.append(P); continue
    vsol, vtok = P["vsol_after"], P["vtok_after"]
    tokens = P["tokens"]; spent = P["spent"]
    mark0 = net(vsol, vtok, tokens)
    peak = mark0; peak_at = entry_bt
    rows = []
    trailing_cross = None
    target_cross = None
    exit_state = None
    big_sells = []
    hold_vsol, hold_vtok = None, None
    post_max = None
    rows.append(dict(t=entry_bt, who="US", side="buy", sol=P["exit_sol"] if False else None, share=None, mark=mark0, note="entry fill"))
    for r in T[idx + 1:]:
        real_before = vsol - VSOL0
        if r["trader"] == OUR and r["slot"] == P["exit_slot"] and r["side"] == "sell":
            # our actual exit: record state, then do NOT apply (hold path) -> apply separately
            exit_state = (vsol, vtok, real_before)
            rows.append(dict(t=r["bt"], who="US", side="sell", sol=r["sol"], share=r["sol"] / real_before, mark=net(vsol, vtok, tokens), note="our exit fill (reconstructed mark just before)"))
            continue
        if r["side"] == "buy":
            vsol += r["sol"]; vtok -= r["tok"]
        else:
            vsol -= r["sol"]; vtok += r["tok"]
        m = net(vsol, vtok, tokens)
        share = r["sol"] / real_before if r["side"] == "sell" else r["sol"] / real_before
        flag = ""
        if r["side"] == "sell":
            if r["trader"] == P["creator"]: flag += "CREATOR "
            elif r["trader"] in early_set: flag += "EARLY%d " % (early.index(r["trader"]) + 1)
            if r["sol"] / real_before >= 0.05: flag += "BIG "
        if exit_state is None:
            if m > peak: peak = m; peak_at = r["bt"]
            if trailing_cross is None and m <= peak * 0.9:
                trailing_cross = (r["bt"], m, r)
            if target_cross is None and m >= spent * 1.15:
                target_cross = (r["bt"], m, r)
            if r["side"] == "sell" and (r["sol"] / real_before >= 0.05 or r["trader"] in early_set or r["trader"] == P["creator"]):
                big_sells.append(dict(t=r["bt"], rcv=r["rcv"], trader=r["trader"], sol=r["sol"], tok=r["tok"], share=r["sol"] / real_before, mark_after=m, flag=flag, real_before=real_before))
        else:
            if post_max is None or m > post_max[1]:
                post_max = (r["bt"], m)
        rows.append(dict(t=r["bt"], who=r["trader"][:6], side=r["side"], sol=r["sol"], share=share, mark=m, note=flag.strip(), tok=r["tok"]))
    # validate reconstruction at exit
    if exit_state:
        v_after = exit_state[0] - P["exit_sol"]; tk_after = exit_state[1] + tokens
        val = (v_after - P["exit_vsol_after"]) / 1e9
    else:
        val = None
    P["_rows"] = rows; P["_early"] = early; P["_peak"] = (peak, peak_at); P["_trail"] = trailing_cross; P["_target"] = target_cross
    P["_big"] = big_sells; P["_val"] = val; P["_post_max"] = post_max; P["_mark0"] = mark0; P["_exit_state"] = exit_state
    out.append(P)

def fmt_sol(l): return "%.4f" % (l / 1e9)

for P in out:
    print("=" * 100)
    print(P["tag"], "entry", brt(ts(P["entry_bt"])), "exit", brt(ts(P["exit_bt"])), P["reason"], "spent", fmt_sol(P["spent"]), "net", fmt_sol(P["exit_net"]), "pnl %.2f%%" % ((P["exit_net"] / P["spent"] - 1) * 100))
    print("mark0", fmt_sol(P["_mark0"]), "peak(reconstr)", fmt_sol(P["_peak"][0]), "at", brt(P["_peak"][1]), "hw(db)", P["hw"], "recon-exit-vsol-diff SOL", P["_val"])
    print("early10:", [e[:6] + ("*C" if e == P["creator"] else "") for e in P["_early"]])
    print("trailing cross (tape):", (brt(P["_trail"][0]), fmt_sol(P["_trail"][1]), P["_trail"][2]["trader"][:6], P["_trail"][2]["side"], fmt_sol(P["_trail"][2]["sol"])) if P["_trail"] else None, "| trigger(db)", brt(ts(P["trigger_at"])))
    print("target cross (tape):", (brt(P["_target"][0]), fmt_sol(P["_target"][1])) if P["_target"] else None)
    print("post-exit max hold-mark:", (brt(P["_post_max"][0]), fmt_sol(P["_post_max"][1])) if P["_post_max"] else None)
    print("flagged sells before exit:")
    for b in P["_big"]:
        print("   ", brt(b["t"]), "rcv", brt(b["rcv"]), b["trader"][:6], "sol", fmt_sol(b["sol"]), "share %.1f%%" % (b["share"] * 100), "real_before", fmt_sol(b["real_before"]), "mark_after", fmt_sol(b["mark_after"]), b["flag"])
    print("timeline (trades after entry to exit+60s):")
    for r in P["_rows"]:
        if r["t"] <= ts(P["exit_bt"]) + timedelta(seconds=60):
            print("   ", brt(r["t"]), r["who"], r["side"], fmt_sol(r["sol"]) if r["sol"] else "-", ("%.1f%%" % (r["share"] * 100)) if r["share"] is not None else "-", "mark", fmt_sol(r["mark"]), r["note"])
json.dump([{k: (v if not k.startswith("_") else None) for k, v in P.items()} for P in out], open("pos_out.json", "w"), default=str)
