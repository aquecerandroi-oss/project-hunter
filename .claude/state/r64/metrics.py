"""R64 Q1/Q3/Q4 — per-position MFE/MAE/hold-to-time, cuts by hour/set/reason, same-mint cooldown."""
import csv
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from load import HERE, HOLD, brt, fill_after, load_all, ts

L = 1.5  # s, trigger -> landing (R62 median 1.64 s)


def pct(a, b):
    return (a / b - 1) * 100


def per_position(P):
    path, spent, tokens = P["path"], P["spent"], P["tokens"]
    entry = P["entry_bt"]
    end = entry + timedelta(seconds=HOLD)
    win = [p for p in path if p[0] <= end]
    pre = [p for p in path if p[0] < P["exit_bt"]] or [path[0]]
    mfe = max(win, key=lambda p: p[3])
    mae = min(win, key=lambda p: p[3])
    mfe_pre = max(pre, key=lambda p: p[3])
    hold_net = fill_after(path, end + timedelta(seconds=L), tokens)
    post = [p for p in win if p[0] > P["exit_bt"]]
    post_max = max(post, key=lambda p: p[3]) if post else None
    return dict(
        tag=P["tag"], set=P["set"], reason=P["reason"], source=P["source"], entry_brt=brt(P["entry_at"]),
        hour_brt=int(brt(P["entry_at"], "%H")), held_s=int((P["exit_at"] - P["entry_at"]).total_seconds()),
        spent=spent, net=P["exit_net"], pnl_sol=str(P["pnl_sol"]), pnl_pct=pct(P["exit_net"], spent),
        mark0_pct=pct(path[0][3], spent), mfe_pct=pct(mfe[3], spent), mfe_s=int((mfe[0] - entry).total_seconds()),
        mfe_pre_exit_pct=pct(mfe_pre[3], spent), hw_db_pct=pct(int(P["hw"] * 10**9), spent), mae_pct=pct(mae[3], spent), mae_s=int((mae[0] - entry).total_seconds()),
        hold300_pct=pct(hold_net, spent), hold300_pnl_sol=(hold_net - spent) / 1e9,
        post_exit_max_pct=pct(post_max[3], spent) if post_max else None,
        last_point_s=int((win[-1][0] - entry).total_seconds()), n_points=len(win),
    )


def cuts(rows):
    def agg(key):
        g = defaultdict(list)
        for r in rows:
            g[key(r)].append(r)
        out = []
        for k in sorted(g):
            rs = g[k]
            wins = sum(1 for r in rs if r["net"] > r["spent"])
            out.append(dict(key=k, n=len(rs), wins=wins, hit="%.0f%%" % (100 * wins / len(rs)),
                            pnl_sol="%+.4f" % (sum(r["net"] - r["spent"] for r in rs) / 1e9),
                            mfe_med="%+.1f%%" % sorted(r["mfe_pct"] for r in rs)[len(rs) // 2],
                            mfe_avg="%+.1f%%" % (sum(r["mfe_pct"] for r in rs) / len(rs)),
                            hold300_sol="%+.4f" % sum(r["hold300_pnl_sol"] for r in rs)))
        return out
    return dict(by_hour=agg(lambda r: r["hour_brt"]), by_set=agg(lambda r: r["set"]), by_reason=agg(lambda r: r["reason"]))


def cooldown_positions(positions, minutes, after=("trailing",)):
    """Skip a position if the same mint had an exit with reason in `after` within `minutes` before its entry."""
    skipped = []
    for i, P in enumerate(positions):
        prev = [Q for Q in positions[:i] if Q["mint"] == P["mint"] and Q["reason"] in after and 0 <= (P["entry_at"] - Q["exit_at"]).total_seconds() <= minutes * 60]
        if prev:
            skipped.append(P)
    return skipped


def cooldown_bets(minutes, after=("trailing",)):
    bets = list(csv.DictReader(open(HERE / "bets.csv", newline="", encoding="utf-8")))
    for b in bets:
        b["entry"] = ts(b["entry_at"]); b["exit"] = ts(b["exit_at"]); b["pnl"] = Decimal(b["pnl_sol"] or "0")
        b["rm"] = Decimal(b["r_multiple"] or "0")
    bets.sort(key=lambda b: b["entry"])
    skipped = []
    for i, b in enumerate(bets):
        prev = [q for q in bets[:i] if q["mint"] == b["mint"] and q["exit_reason"] in after and 0 <= (b["entry"] - q["exit"]).total_seconds() <= minutes * 60]
        if prev:
            skipped.append(b)
    n = len(bets)
    return dict(minutes=minutes, after="|".join(after), n_bets=n, n_skipped=len(skipped),
                pnl_skipped=str(sum(b["pnl"] for b in skipped)), r_avg_skipped=str(round(sum(b["rm"] for b in skipped) / len(skipped), 4)) if skipped else "-",
                r_avg_all=str(round(sum(b["rm"] for b in bets) / n, 4)), wins_skipped=sum(1 for b in skipped if b["pnl"] > 0),
                skipped_tags=[b["symbol"] + "@" + brt(b["entry"]) for b in skipped][:12])


if __name__ == "__main__":
    positions, _, _ = load_all()
    rows = [per_position(P) for P in positions]
    print("tag | entry BRT | set | reason | pnl% | held s | mark0% | MFE% (s) | MFE pre-exit% | hw(db)% | MAE% (s) | hold300% | post-exit max% | source | last pt s")
    for r in rows:
        print("%-11s | %s | %s | %-12s | %+6.1f | %3d | %+5.1f | %+6.1f (%3d) | %+6.1f | %+6.1f | %+6.1f (%3d) | %+6.1f | %s | %s | %d" % (
            r["tag"], r["entry_brt"], r["set"][-1], r["reason"], r["pnl_pct"], r["held_s"], r["mark0_pct"], r["mfe_pct"], r["mfe_s"], r["mfe_pre_exit_pct"], r["hw_db_pct"],
            r["mae_pct"], r["mae_s"], r["hold300_pct"], ("%+.1f" % r["post_exit_max_pct"]) if r["post_exit_max_pct"] is not None else "-", r["source"], r["last_point_s"]))
    tot = sum(r["net"] - r["spent"] for r in rows) / 1e9
    print("TOTAL real %+.4f SOL | hold-to-300s %+.4f SOL | wins %d/%d" % (tot, sum(r["hold300_pnl_sol"] for r in rows), sum(1 for r in rows if r["net"] > r["spent"]), len(rows)))
    c = cuts(rows)
    for k, v in c.items():
        print("--", k)
        for x in v:
            print("   ", x)
    print("-- cooldown on the 24 (after trailing exit)")
    cd = {}
    for m in (5, 15, 60):
        sk = cooldown_positions(positions, m)
        cd[m] = dict(n=len(sk), pnl="%+.4f" % (sum(P["exit_net"] - P["spent"] for P in sk) / 1e9), tags=[P["tag"] for P in sk])
        print("   %2d min: skip %d %s pnl of skipped %s" % (m, len(sk), cd[m]["tags"], cd[m]["pnl"]))
    print("-- cooldown on the 24 (after any exit)")
    for m in (5, 15, 60):
        sk = cooldown_positions(positions, m, after=("trailing", "target", "creator_dump"))
        print("   %2d min: skip %d %s pnl of skipped %+.4f" % (m, len(sk), [P["tag"] for P in sk], sum(P["exit_net"] - P["spent"] for P in sk) / 1e9))
    print("-- cooldown on today's paper bets")
    cb = []
    for after in (("trailing",), ("trailing", "max_loss", "line_broken", "creator_dump")):
        for m in (5, 15, 60):
            x = cooldown_bets(m, after); cb.append(x); print("   ", x)
    json.dump(dict(rows=rows, cuts=c, cooldown24=cd, cooldown_bets=cb), open(HERE / "metrics.json", "w"), indent=1, default=str)
