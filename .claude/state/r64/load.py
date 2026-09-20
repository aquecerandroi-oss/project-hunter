"""R64 — load the 24 real positions of 2026-09-19, the tape and the 15 s photos; rebuild the hold-path.

Method = R62 (`.claude/state/r62/analyze.py`, `sim.py`): from the entry fill reserves (exact), every tape trade
adds/removes sol/tokens on the virtual reserves; mark = net proceeds of selling all our tokens x (1 - 1.25 %).
Our own trades after the entry are skipped (hold path). When the tape has no anchor (4 mints), the 15 s photos
(`meme_curve_snapshots`) give the reserves directly.
"""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
VSOL0 = 30_000_000_000
FEE = Decimal("0.0125")
BRT = timezone(timedelta(hours=-3))
HOLD = 300


def ts(s):
    s = s.strip()
    if s.endswith("+00"):
        s = s + ":00"
    return datetime.fromisoformat(s.replace(" ", "T"))


def brt(d, fmt="%H:%M:%S"):
    return d.astimezone(BRT).strftime(fmt)


def net(vsol, vtok, amount):
    p = vsol - (vsol * vtok) // (vtok + amount)
    return int(Decimal(p) * (1 - FEE))


def load_positions():
    rows = list(csv.DictReader(open(HERE / "pos24.csv", newline="", encoding="utf-8")))
    seen = {}
    out = []
    for r in rows:
        sym = r["symbol"].strip()
        seen[sym] = seen.get(sym, 0) + 1
        P = dict(
            tag=sym + ("#%d" % seen[sym] if seen[sym] > 1 or sym in ("Cupsey", "NARKY", "KODA", "Musepaid") else ""),
            mint=r["mint"], set="%s/%s" % (r["rule_set"], "5" if r["rule_set_id"].endswith("11") else "6"),
            entry_at=ts(r["entry_at"]), exit_at=ts(r["exit_at"]), reason=r["exit_reason"], decided_at=ts(r["decided_at"]),
            spent=int(r["sol_spent_lamports"]), received=int(r["sol_received_lamports"]), pnl_sol=Decimal(r["pnl_sol"]),
            entry_slot=int(r["entry_slot"]), entry_bt=ts(r["entry_bt"]), tokens=int(Decimal(r["tokens_entry"])),
            vsol_after=int(Decimal(r["vsol_after"])), vtok_after=int(Decimal(r["vtok_after"])),
            exit_slot=int(r["exit_slot"]), exit_bt=ts(r["exit_bt"]), exit_net=int(Decimal(r["exit_net"])),
            exit_vsol_after=int(Decimal(r["exit_vsol_after"])), exit_vtok_after=int(Decimal(r["exit_vtok_after"])),
            creator=r["creator"], hw=Decimal(r["high_water_sol"]),
        )
        out.append(P)
    # tags: number the repeated symbols #1/#2
    counts = {}
    for P in out:
        counts[P["mint"]] = counts.get(P["mint"], 0) + 1
    idx = {}
    for P in out:
        base = P["tag"].split("#")[0]
        if counts[P["mint"]] > 1:
            idx[P["mint"]] = idx.get(P["mint"], 0) + 1
            P["tag"] = "%s#%d" % (base, idx[P["mint"]])
        else:
            P["tag"] = base
    return out


def load_tape():
    trades = {}
    with open(HERE / "trades.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["bt"] = ts(r["block_time"]); r["slot"] = int(r["slot"]); r["ei"] = int(r["event_index"])
            r["sol"] = int(r["sol_lamports"]); r["tok"] = int(Decimal(r["token_amount"]) * 10**6)
            trades.setdefault(r["mint"], []).append(r)
    for m in trades:
        trades[m].sort(key=lambda r: (r["slot"], r["signature"], r["ei"]))
    return trades


def load_snaps():
    snaps = {}
    with open(HERE / "snaps.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            snaps.setdefault(r["mint"], []).append(dict(t=ts(r["observed_at"]), vsol=int(Decimal(r["virtual_sol_reserves"]) * 10**9), vtok=int(Decimal(r["virtual_token_reserves"]) * 10**6), slot=int(r["slot"] or 0)))
    for m in snaps:
        snaps[m].sort(key=lambda r: r["t"])
    return snaps


def build_path(P, trades, snaps):
    """Hold path: list of (t, vsol, vtok, mark, trade-or-None).

    Tape trades after our entry (skipping our own) are applied on the entry-fill reserves; every `solana_rpc`
    photo with a slot >= the last applied trade slot re-syncs the reserves (heals tape holes). Photos without slot
    (`pumpfun_rest`) are only used when the mint has no tape at all. P['source'] = 'tape+photos' | 'photos'.
    """
    tokens = P["tokens"]
    T = [r for r in trades.get(P["mint"], []) if r["trader"] != OUR and (r["slot"] > P["entry_slot"])]
    S = [s for s in snaps.get(P["mint"], []) if s["t"] > P["entry_bt"]]
    vsol, vtok = P["vsol_after"], P["vtok_after"]
    path = [(P["entry_bt"], vsol, vtok, net(vsol, vtok, tokens), None)]
    P["resync_max_sol"] = 0.0
    P["n_trades"] = len(T)
    if T:
        P["source"] = "tape+photos"
        events = [(r["slot"], 0, r["bt"], r) for r in T] + [(s["slot"], 1, s["t"], s) for s in S if s["slot"] and s["slot"] >= P["entry_slot"]]
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        last_slot = P["entry_slot"]
        for slot, kind, t, e in events:
            if kind == 0:
                if e["side"] == "buy":
                    vsol += e["sol"]; vtok -= e["tok"]
                else:
                    vsol -= e["sol"]; vtok += e["tok"]
                last_slot = slot
                path.append((t, vsol, vtok, net(vsol, vtok, tokens), e))
            else:
                if slot < last_slot:
                    continue
                d = abs(e["vsol"] - vsol) / 1e9
                P["resync_max_sol"] = max(P["resync_max_sol"], d)
                vsol, vtok = e["vsol"], e["vtok"]
                path.append((t, vsol, vtok, net(vsol, vtok, tokens), None))
        P["tape_last"] = T[-1]["bt"]
    else:
        P["source"] = "photos"
        P["tape_last"] = None
        for s in S:
            path.append((s["t"], s["vsol"], s["vtok"], net(s["vsol"], s["vtok"], tokens), None))
    path.sort(key=lambda p: p[0])
    P["path"] = path
    return path


def fill_after(path, t, tokens):
    """Net proceeds if our sell lands at t (after every trade with block_time <= t)."""
    last = path[0]
    for p in path:
        if p[0] <= t:
            last = p
        else:
            break
    return net(last[1], last[2], tokens)


def load_all():
    positions = load_positions()
    trades = load_tape()
    snaps = load_snaps()
    for P in positions:
        build_path(P, trades, snaps)
    return positions, trades, snaps


if __name__ == "__main__":
    positions, trades, snaps = load_all()
    for P in positions:
        path = P["path"]
        end = P["entry_bt"] + timedelta(seconds=HOLD)
        n_in = sum(1 for p in path if p[0] <= end)
        print("%-12s %s %-10s %-12s src=%-11s trades=%4d points<=300s=%3d last=%s resync_max=%.4f SOL" % (
            P["tag"], brt(P["entry_at"]), P["set"], P["reason"], P["source"], P["n_trades"], n_in,
            brt(path[-1][0]) if len(path) > 1 else "-", P["resync_max_sol"]))
