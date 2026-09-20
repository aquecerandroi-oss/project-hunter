"""R64 extra — partial take-profit: sell fraction f at target 1.15 (delay L), trail the rest at X % (peak reset at the
partial fill), max_hold 300 s, event exits on. Photo-only positions keep the real outcome. Same fee/net as grid.py."""
import json
from datetime import timedelta

from grid import EVENT_REASONS
from load import HERE, HOLD, fill_after, load_all, net


def run_split(P, f, trailing, L, target=1.15, trail_before=0.10):
    path, spent, tokens, entry = P["path"], P["spent"], P["tokens"], P["entry_bt"]
    if P["source"] == "photos":
        return P["exit_net"], "real(no tape)"
    event_at = P["exit_bt"] if P["reason"] in EVENT_REASONS else None
    peak = path[0][3]
    stage, cash, left = 0, 0, tokens
    for p in path[1:]:
        t, vsol, vtok = p[0], p[1], p[2]
        m = net(vsol, vtok, left)
        dt = (t - entry).total_seconds()
        if event_at is not None and t >= event_at:
            return cash + (P["exit_net"] * left // tokens), "event"
        if dt > HOLD:
            return cash + fill_after_amt(path, entry + timedelta(seconds=HOLD + L), left), "time"
        if stage == 0:
            if m >= target * spent:
                land = t + timedelta(seconds=L)
                sold = int(tokens * f)
                cash = fill_after_amt(path, land, sold)
                left = tokens - sold
                stage, peak = 1, fill_after_amt(path, land, left)
                continue
            peak = max(peak, m)
            if m <= peak * (1 - trail_before):
                return fill_after_amt(path, t + timedelta(seconds=L), tokens), "trailing"
        else:
            peak = max(peak, m)
            if m <= peak * (1 - trailing):
                return cash + fill_after_amt(path, t + timedelta(seconds=L), left), "trail2"
    if event_at is not None:
        return cash + (P["exit_net"] * left // tokens), "event"
    last = path[-1]
    if (last[0] - entry).total_seconds() >= HOLD - 20:
        return cash + fill_after_amt(path, entry + timedelta(seconds=HOLD + L), left), "time"
    return cash + net(last[1], last[2], left), "censored"


def fill_after_amt(path, t, amount):
    last = path[0]
    for p in path:
        if p[0] <= t:
            last = p
        else:
            break
    return net(last[1], last[2], amount)


if __name__ == "__main__":
    positions, _, _ = load_all()
    real = sum(P["exit_net"] - P["spent"] for P in positions) / 1e9
    out = []
    for L in (1.5, 5.0):
        print("== L = %.1f | real %+.4f" % (L, real))
        for f in (0.5, 0.7):
            for trailing in (0.10, 0.20, 0.30, 0.50):
                tot = 0; wins = 0; cells = {}; reasons = {}
                for P in positions:
                    n, why = run_split(P, f, trailing, L)
                    pnl = n - P["spent"]; tot += pnl; wins += pnl > 0; reasons[why] = reasons.get(why, 0) + 1
                    cells[P["tag"]] = (round(pnl / 1e9, 4), why)
                name = "sell %d%% at 1.15, trail rest %d%%" % (f * 100, trailing * 100)
                out.append(dict(L=L, name=name, total=round(tot / 1e9, 4), wins=wins, reasons=reasons, cells=cells))
                print("   %-34s | %+.4f | %2d | %s" % (name, tot / 1e9, wins, reasons))
                if f == 0.5 and trailing == 0.30:
                    print("      ", {k: v for k, v in cells.items() if v[1] in ("trail2", "time", "censored")})
    json.dump(out, open(HERE / "split.json", "w"), indent=1)
