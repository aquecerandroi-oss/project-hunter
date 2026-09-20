"""R64 Q2 — exit-rule grid replay on the 24 real positions (method = R62 var8.py, extended).

trailing {10,15,20,30 %} x arm {from entry, after +10 %, after +20 %} x target {none, 1.15, 1.30, 1.50}, max_hold 300 s,
trigger -> landing delay L (1.5 s; sensitivity 5 s), fee 1.25 % (inside `net`). Event-driven exits stay on: a position
the real desk closed by an event (creator_dump) is closed at the same instant in every arm if still open.
"""
import json
import sys
from datetime import timedelta

from load import HERE, HOLD, fill_after, load_all

EVENT_REASONS = ("creator_dump", "early_exit", "migrated", "rug")


def run(P, trailing, arm, target, L):
    path, spent, tokens, entry = P["path"], P["spent"], P["tokens"], P["entry_bt"]
    if P["source"] == "photos":
        return P["exit_net"], "real(no tape)"  # 15 s photos cannot resolve a 10 % trailing: keep the real outcome
    event_at = P["exit_bt"] if P["reason"] in EVENT_REASONS else None
    armed = arm == 0
    peak = path[0][3] if armed else None
    for p in path[1:]:
        t, m = p[0], p[3]
        dt = (t - entry).total_seconds()
        if event_at is not None and t >= event_at:
            return P["exit_net"], "event"
        if dt > HOLD:
            return fill_after(path, entry + timedelta(seconds=HOLD + L), tokens), "time"
        if target and m >= target * spent:
            return fill_after(path, t + timedelta(seconds=L), tokens), "target"
        if trailing is not None:
            if not armed and m >= (1 + arm) * spent:
                armed, peak = True, m
            if armed:
                peak = max(peak, m)
                if m <= peak * (1 - trailing):
                    return fill_after(path, t + timedelta(seconds=L), tokens), "trailing"
    if event_at is not None:
        return P["exit_net"], "event"
    last = path[-1]
    if (last[0] - entry).total_seconds() >= HOLD - 20:
        return fill_after(path, entry + timedelta(seconds=HOLD + L), tokens), "time"
    return last[3], "censored"


def grid(positions, L):
    arms = []
    for trailing in (0.10, 0.15, 0.20, 0.30):
        for arm in (0, 0.10, 0.20):
            for target in (None, 1.15, 1.30, 1.50):
                arms.append((trailing, arm, target))
    for target in (None, 1.15, 1.30, 1.50):
        arms.append((None, None, target))  # reference: no trailing at all
    out = []
    for trailing, arm, target in arms:
        cells = {}
        tot = 0
        wins = 0
        reasons = {}
        for P in positions:
            net, why = run(P, trailing, arm, target, L)
            pnl = net - P["spent"]
            tot += pnl
            wins += pnl > 0
            reasons[why] = reasons.get(why, 0) + 1
            cells[P["tag"]] = (round(pnl / 1e9, 4), why)
        name = "trail %s / arm %s / target %s" % (
            "none" if trailing is None else "%d%%" % round(trailing * 100),
            "-" if arm is None else ("entry" if arm == 0 else "+%d%%" % round(arm * 100)),
            "none" if target is None else "%.2f" % target)
        out.append(dict(name=name, trailing=trailing, arm=arm, target=target, total=round(tot / 1e9, 4), wins=wins, reasons=reasons, cells=cells))
    return out


if __name__ == "__main__":
    positions, _, _ = load_all()
    real = sum(P["exit_net"] - P["spent"] for P in positions) / 1e9
    res = {}
    for L in (1.5, 5.0):
        g = grid(positions, L)
        res[str(L)] = g
        base = next(x for x in g if x["trailing"] == 0.10 and x["arm"] == 0 and x["target"] == 1.15)
        ranked = sorted(g, key=lambda x: -x["total"])
        tape = [P for P in positions if P["source"] != "photos"]
        real_tape = sum(P["exit_net"] - P["spent"] for P in tape) / 1e9
        print("== L = %.1f s | real %+.4f SOL (19 with tape %+.4f) | baseline sim (trail 10 / entry / 1.15) %+.4f SOL wins %d %s" % (L, real, real_tape, base["total"], base["wins"], base["reasons"]))
        print("   baseline per position:", {k: v for k, v in base["cells"].items()})
        print("   rank | arm | total SOL | wins | reasons")
        for i, x in enumerate(ranked):
            flag = " <- baseline" if x is base else ""
            if i < 12 or x is base or x["trailing"] is None:
                print("   %2d | %-36s | %+.4f | %2d | %s%s" % (i + 1, x["name"], x["total"], x["wins"], x["reasons"], flag))
        for x in ranked[:3]:
            print("   top:", x["name"], x["cells"])
        # marginals
        for dim, vals in (("trailing", (0.10, 0.15, 0.20, 0.30, None)), ("arm", (0, 0.10, 0.20)), ("target", (None, 1.15, 1.30, 1.50))):
            print("   marginal by", dim, {str(v): round(sum(x["total"] for x in g if x[dim] == v and (dim == "trailing" or x["trailing"] is not None)) / max(1, sum(1 for x in g if x[dim] == v and (dim == "trailing" or x["trailing"] is not None))), 4) for v in vals})
    json.dump(res, open(HERE / "grid.json", "w"), indent=1)
