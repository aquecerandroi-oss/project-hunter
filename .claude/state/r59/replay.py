"""R59 — replay of exit rules over the 15 s series (meme_features_15s.mcap_sol).

Inputs (pipe-separated psql exports, see q_bets.sql / q_15s.sql / q_1m.sql):
  bets.psv  — paper bets of the 5 entry sets + the 12 live positions
  s15.psv   — meme_features_15s rows for those mints (as_of, mcap_sol, ...)
  s1m.psv   — meme_features_1m support lines (end_time, support_line_sol, slope, creator_sold)

Price path: mcap_sol of the 15 s row (theoretical curve mcap, virtual reserves),
ratio to the entry mcap (paper: entry.snapshot.mcap_sol; live: post-fill virtual
reserves). Fees 1.25 % each way, stake normalised to 0.05 SOL, no slippage.
Decision instant = as_of (no look-ahead: the row only holds observations <= as_of).
A rule that has not fired by the last row is force-closed on that row (censored).

Usage: uv run python .claude/state/r59/replay.py <dir with bets.psv s15.psv s1m.psv>
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

STAKE = 0.05
import os
FEE = float(os.environ.get("R59_FEE", "0.0125"))
MIN_COVER_S = int(sys.argv[2]) if len(sys.argv) > 2 else 600
MODE = sys.argv[3] if len(sys.argv) > 3 else "hold"  # hold = force-close at series end; earlier = rule may only fire before the recorded exit, else the recorded exit
NL = chr(10)


def ts(s):
    if not s:
        return None
    s = s.replace("T", " ")
    if s.endswith("+00"):
        s += ":00"
    if s.endswith("+00:00"):
        s = s[:-6]
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def load(path):
    rows = [
        l.rstrip(NL).split("|")
        for l in open(path, encoding="utf-8")
        if l.strip() and not l.startswith("SET") and not l.startswith("(")
    ]
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:]]


def fnum(x):
    return float(x) if x not in (None, "") else None


S = sys.argv[1]
bets = load(S + "/bets.psv")
s15 = defaultdict(list)
for r in load(S + "/s15.psv"):
    s15[r["mint"]].append(
        (ts(r["as_of"]), fnum(r["mcap_sol"]), fnum(r["mcap_executable_sol"]), fnum(r["curve_progress_pct"]), r["creator_net_seller"])
    )
s1m = defaultdict(list)
for r in load(S + "/s1m.psv"):
    s1m[r["mint"]].append((ts(r["end_time"]), fnum(r["support_line_sol"]), fnum(r["support_line_slope"]), r["creator_sold"]))


def support_at(lines, at):
    usable = [l for l in lines if l[0] <= at and l[1] is not None]
    if not usable:
        return None
    l = max(usable, key=lambda x: x[0])
    return l[1] + (l[2] or 0.0) * (at - l[0]).total_seconds() / 60.0


def pnl_of(mult):
    """net PnL at stake 0.05 for a gross price multiple, 1.25 % fee each way."""
    return STAKE * (1 - FEE) ** 2 * mult - STAKE


# ---- build per-bet paths -------------------------------------------------
paths = []
for b in bets:
    t0 = ts(b["entry_at"])
    p0 = fnum(b["entry_mcap"])
    if p0 is None or p0 <= 0:
        continue
    rows = [r for r in s15.get(b["mint"], []) if r[0] > t0 and r[1] is not None]
    if MODE == "earlier":
        rows = [r for r in rows if r[0] <= ts(b["exit_at"])]
    if not rows:
        b["_cover"] = 0
        paths.append((b, None))
        continue
    cover = (rows[-1][0] - t0).total_seconds()
    b["_cover"] = cover
    b["_hold"] = (ts(b["exit_at"]) - t0).total_seconds()
    if cover < MIN_COVER_S or (MODE == "earlier" and not b["exit_mcap"]):
        paths.append((b, None))
        continue
    t = np.array([(r[0] - t0).total_seconds() for r in rows])
    p = np.array([r[1] / p0 for r in rows])
    lines = s1m.get(b["mint"], [])
    sup = np.array([(lambda s: s / p0 if s else np.nan)(support_at(lines, r[0])) for r in rows])
    cs_seen = ts(b["creator_sold_seen_at"])
    first_cs_1m = min([l[0] for l in lines if l[3] == "t"], default=None)
    first_cs_15 = min([r[0] for r in rows if r[4] == "t"], default=None)
    as_ofs = np.array([r[0] for r in rows])

    def _idx(cands):
        cands = [x for x in cands if x is not None]
        if not cands:
            return None
        after = np.where(as_ofs >= min(cands))[0]
        return int(after[0]) if len(after) else None

    cs_idx = _idx((cs_seen, first_cs_1m))        # what the paper engine reads (creator_watch + 1m tape)
    cs15_idx = _idx((cs_seen, first_cs_1m, first_cs_15))  # plus the 15 s creator_net_seller
    b["_key"] = b["mint"] + "@" + t0.strftime("%Y%m%d%H%M")
    paths.append((b, dict(t=t, p=p, sup=sup, cs_idx=cs_idx, cs15_idx=cs15_idx, n=len(rows))))


# ---- rules ---------------------------------------------------------------
def rule_trailing(P, pct, arm=None, target=None, time_s=None):
    t, p = P["t"], P["p"]
    peak = 1.0
    for i in range(len(p)):
        peak = max(peak, p[i])
        if target is not None and p[i] >= target:
            return i, "target"
        if (arm is None or peak >= arm) and p[i] <= peak * (1 - pct):
            return i, "trailing"
        if time_s is not None and t[i] >= time_s:
            return i, "time_stop"
    return len(p) - 1, "censored"


def rule_time(P, time_s):
    t = P["t"]
    idx = np.where(t >= time_s)[0]
    return (int(idx[0]), "time_stop") if len(idx) else (len(t) - 1, "censored")


def rule_line(P, snaps=2, max_loss=None):
    p, sup = P["p"], P["sup"]
    streak = 0
    for i in range(len(p)):
        if max_loss is not None and p[i] <= 1 - max_loss:
            return i, "max_loss"
        if np.isnan(sup[i]) or sup[i] <= 0:  # unknown line: blind, streak unknown
            streak = 0
            continue
        streak = streak + 1 if p[i] < sup[i] else 0
        if streak >= snaps:
            return i, "line_broken"
    return len(p) - 1, "censored"


def rule_paper_full(P):
    """paper set alvo_3x_trailing_35_apos_1_5x_tempo_30m + line_break(2) + max_loss 50 + creator_dump."""
    t, p, sup = P["t"], P["p"], P["sup"]
    peak = 1.0
    streak = 0
    for i in range(len(p)):
        peak = max(peak, p[i])
        if P["cs_idx"] is not None and i >= P["cs_idx"]:
            return i, "creator_dump"
        if p[i] <= 0.5:
            return i, "max_loss"
        if not np.isnan(sup[i]) and sup[i] > 0:
            streak = streak + 1 if p[i] < sup[i] else 0
            if streak >= 2:
                return i, "line_broken"
        if p[i] >= 3.0:
            return i, "target"
        if peak >= 1.5 and p[i] <= peak * 0.65:
            return i, "trailing"
        if t[i] >= 1800:
            return i, "time_stop"
    return len(p) - 1, "censored"


def rule_creator(P, key="cs_idx"):
    if P[key] is not None:
        return P[key], "creator_sell"
    return P["n"] - 1, "censored"


def rule_combo(P, target=1.30, pct=0.20, time_s=300):
    return rule_trailing(P, pct, target=target, time_s=time_s)


RULES = {
    "b_line_broken(2)": lambda P: rule_line(P, 2),
    "b2_paper_full_set": rule_paper_full,
    "c_trail15": lambda P: rule_trailing(P, 0.15),
    "c_trail30": lambda P: rule_trailing(P, 0.30),
    "c_trail50": lambda P: rule_trailing(P, 0.50),
    "d_arm+25%_trail30": lambda P: rule_trailing(P, 0.30, arm=1.25),
    "d_arm+50%_trail30": lambda P: rule_trailing(P, 0.30, arm=1.50),
    "d_arm+100%_trail30": lambda P: rule_trailing(P, 0.30, arm=2.00),
    "d_arm+25%_trail15": lambda P: rule_trailing(P, 0.15, arm=1.25),
    "d_arm+50%_trail15": lambda P: rule_trailing(P, 0.15, arm=1.50),
    "d_tp+25%_else_trail30": lambda P: rule_trailing(P, 0.30, target=1.25),
    "d_tp+50%_else_trail30": lambda P: rule_trailing(P, 0.30, target=1.50),
    "d_tp+100%_else_trail30": lambda P: rule_trailing(P, 0.30, target=2.00),
    "e_time2m": lambda P: rule_time(P, 120),
    "e_time5m": lambda P: rule_time(P, 300),
    "e_time15m": lambda P: rule_time(P, 900),
    "e_time30m": lambda P: rule_time(P, 1800),
    "f_first_creator_sell": rule_creator,
    "f2_creator_sell_incl_15s_net_seller": lambda P: rule_creator(P, "cs15_idx"),
    "g_tp30_or_trail20_or_5m": lambda P: rule_combo(P),
    "g2_tp30_or_trail20_or_2m": lambda P: rule_combo(P, time_s=120),
    "g3_tp50_or_trail20_or_5m": lambda P: rule_combo(P, target=1.5),
    "g4_tp30_or_trail15_or_5m": lambda P: rule_combo(P, pct=0.15),
    "g5_tp30_or_trail15_or_2m": lambda P: rule_combo(P, pct=0.15, time_s=120),
    "h_tp100_or_trail30_or_5m": lambda P: rule_combo(P, target=2.0, pct=0.30, time_s=300),
    "h2_tp100_or_trail30_or_15m": lambda P: rule_combo(P, target=2.0, pct=0.30, time_s=900),
    "h3_tp100_or_trail30_or_30m": lambda P: rule_combo(P, target=2.0, pct=0.30, time_s=1800),
    "h4_tp300_or_trail30_or_30m": lambda P: rule_combo(P, target=3.0, pct=0.30, time_s=1800),
}

SETS = ["operator/5 real", "operator/5", "flow_v2/5", "flow_v2/2", "flow_v2/6", "flow_v2/8"]


def stats(pnls, exit_ts):
    pnls = np.array(pnls)
    n = len(pnls)
    if n == 0:
        return None
    order = np.argsort(exit_ts, kind="stable")
    eq = np.cumsum(pnls[order])
    peak = np.maximum.accumulate(np.maximum(eq, 0))
    mdd = float(np.max(peak - eq))
    top3 = float(np.sort(pnls)[-3:].sum())
    tot = float(pnls.sum())
    share = (top3 / tot) if tot > 0 else float("nan")
    return dict(n=n, hit=float((pnls > 0).mean()), meanR=float((pnls / STAKE).mean()), sum=tot, mdd=mdd, top3=share)


def fmt(s):
    if s is None:
        return "| — | | | | | |"
    sh = "—" if math.isnan(s["top3"]) else f"{s['top3'] * 100:.0f}%"
    return f"| {s['n']} | {s['hit'] * 100:.0f}% | {s['meanR']:+.3f} | {s['sum']:+.4f} | {s['mdd']:.4f} | {sh} |"


# ---- coverage ------------------------------------------------------------
print("## cobertura")
print(f"modo={MODE} min_cover={MIN_COVER_S}s taxa={FEE*100:.2f}% por perna")
print("| set | apostas | elegiveis | sem serie | cobertura mediana (s) | hold mediano (s) |")
print("|---|---|---|---|---|---|")
for st in SETS:
    bb = [b for b, P in paths if b["rs"] == st]
    ok = [b for b, P in paths if b["rs"] == st and P is not None]
    cov = [b["_cover"] for b in bb]
    hold = [(ts(b["exit_at"]) - ts(b["entry_at"])).total_seconds() for b in bb]
    print(f"| {st} | {len(bb)} | {len(ok)} | {sum(1 for c in cov if c == 0)} | {np.median(cov) if cov else 0:.0f} | {np.median(hold) if hold else 0:.0f} |")


def replay(b, P, r):
    if r == "a_actual_recorded":
        return float(b["r_multiple"]) * STAKE, ts(b["exit_at"]).timestamp(), b["exit_reason"], None
    if r == "a2_actual_exit_mcap_fee1.25":
        if not b["exit_mcap"]:
            return None
        return pnl_of(float(b["exit_mcap"]) / float(b["entry_mcap"])), ts(b["exit_at"]).timestamp(), b["exit_reason"], None
    i, why = RULES[r](P)
    if MODE == "earlier" and why == "censored":
        return pnl_of(float(b["exit_mcap"]) / float(b["entry_mcap"])), ts(b["exit_at"]).timestamp(), "actual:" + b["exit_reason"], b["_hold"]
    return pnl_of(P["p"][i]), (ts(b["entry_at"]) + timedelta(seconds=float(P["t"][i]))).timestamp(), why, float(P["t"][i])


rules_all = ["a_actual_recorded", "a2_actual_exit_mcap_fee1.25"] + list(RULES)
results = {}
detail_real = defaultdict(dict)
for st in SETS + ["papel (5 sets)", "papel unico (mint@minuto)"]:
    if st == "papel (5 sets)":
        sub = [(b, P) for b, P in paths if b["rs"] in SETS[1:] and P is not None]
    elif st == "papel unico (mint@minuto)":
        seen = set()
        sub = []
        for b, P in paths:
            if b["rs"] in SETS[1:] and P is not None and b["_key"] not in seen:
                seen.add(b["_key"])
                sub.append((b, P))
    else:
        sub = [(b, P) for b, P in paths if b["rs"] == st and P is not None]
    print(f"{NL}## {st}")
    print("| regra | n | hit | R medio | soma SOL | MDD SOL | top3 | motivos |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rules_all:
        pn, et, reasons = [], [], defaultdict(int)
        for b, P in sub:
            out = replay(b, P, r)
            if out is None:
                continue
            v, t_, why, held = out
            pn.append(v)
            et.append(t_)
            reasons[why] += 1
            if st == "operator/5 real":
                detail_real[b["mint"][:8]][r] = (v, why, held)
        s = stats(pn, et)
        results[(r, st)] = s
        rs = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
        print(f"| {r} {fmt(s)} {rs} |")

print(f"{NL}## as posicoes reais, aposta a aposta (PnL a 0,05 SOL, taxas 1,25 %)")
cols = ["a_actual_recorded", "b_line_broken(2)", "c_trail15", "c_trail30", "e_time2m", "e_time5m", "f_first_creator_sell", "g_tp30_or_trail20_or_5m", "g5_tp30_or_trail15_or_2m"]
print("| mint | cobertura | " + " | ".join(cols) + " |")
print("|" + "---|" * (len(cols) + 2))
for b, P in paths:
    if b["rs"] != "operator/5 real":
        continue
    m = b["mint"][:8]
    held = (ts(b["exit_at"]) - ts(b["entry_at"])).total_seconds()
    cells = [f"{float(b['r_multiple']) * STAKE:+.4f} ({b['exit_reason']}, {held:.0f}s)"]
    if P is None:
        cells += ["sem serie"] * (len(cols) - 1)
    else:
        for c in cols[1:]:
            v, why, tt = detail_real[m][c]
            cells.append(f"{v:+.4f} ({why}, {tt:.0f}s)")
    print(f"| {m} | {b['_cover']:.0f}s | " + " | ".join(cells) + " |")

# ranking: sum SOL with top3 share < 50 % (pooled paper and per set)
print(f"{NL}## top-3 contribuintes (papel unico)")
seen = set()
sub = []
for b, P in paths:
    if b["rs"] in SETS[1:] and P is not None and b["_key"] not in seen:
        seen.add(b["_key"])
        sub.append((b, P))
for r in ["a2_actual_exit_mcap_fee1.25", "c_trail15", "c_trail30", "d_tp+100%_else_trail30", "e_time5m"]:
    outs = sorted(((replay(b, P, r), b) for b, P in sub if replay(b, P, r)), key=lambda x: -x[0][0])
    tot = sum(o[0][0] for o in outs)
    print(f"- {r}: soma {tot:+.4f}; top3 = " + "; ".join(f"{b['mint'][:8]} {o[0]:+.4f} ({o[2]}, {(o[3] or 0):.0f}s)" for o, b in outs[:3]))

print(f"{NL}## ranking (soma SOL, top3 < 50 %)")
for st in ["papel (5 sets)", "papel unico (mint@minuto)"] + SETS:
    ok = [(r, results[(r, st)]) for r in rules_all if results.get((r, st)) and not math.isnan(results[(r, st)]["top3"]) and results[(r, st)]["top3"] < 0.5]
    ok.sort(key=lambda x: -x[1]["sum"])
    best = ", ".join(f"{r} ({s['sum']:+.4f}, top3 {s['top3'] * 100:.0f}%)" for r, s in ok[:4])
    allr = sorted(((r, results[(r, st)]) for r in rules_all if results.get((r, st))), key=lambda x: -x[1]["sum"])
    print(f"- {st}: melhor com top3<50%: {best or 'nenhuma'} | melhor absoluta: {allr[0][0]} ({allr[0][1]['sum']:+.4f}, top3 {allr[0][1]['top3'] * 100:.0f}%)")

# ---- paired deltas vs the recorded exit replayed at 1.25 % (a2) ----------------
from math import comb

def sign_p(w, l):
    n = w + l
    if n == 0:
        return float("nan")
    k = max(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n)

print(f"{NL}## delta pareado por aposta (regra - saida registrada a 1,25 %), modo={MODE}")
for st in ["papel unico (mint@minuto)", "operator/5 real", "operator/5", "flow_v2/5", "flow_v2/2", "flow_v2/6", "flow_v2/8"]:
    if st.startswith("papel unico"):
        seen = set(); sub = []
        for b, P in paths:
            if b["rs"] in SETS[1:] and P is not None and b["_key"] not in seen:
                seen.add(b["_key"]); sub.append((b, P))
    else:
        sub = [(b, P) for b, P in paths if b["rs"] == st and P is not None]
    print(f"{NL}### {st} (n={len(sub)})")
    print("| regra | melhora | piora | igual | delta mediano | soma delta | top3 dos deltas>0 | p (sinal) |")
    print("|---|---|---|---|---|---|---|---|")
    for r in list(RULES):
        d = []
        for b, P in sub:
            a = replay(b, P, "a2_actual_exit_mcap_fee1.25"); x = replay(b, P, r)
            if a is None or x is None:
                continue
            d.append(x[0] - a[0])
        d = np.array(d)
        if not len(d):
            continue
        w = int((d > 1e-9).sum()); l = int((d < -1e-9).sum()); e = len(d) - w - l
        pos = np.sort(d[d > 0])[::-1]
        share = pos[:3].sum() / pos.sum() if pos.sum() > 0 else float("nan")
        print(f"| {r} | {w} | {l} | {e} | {np.median(d):+.4f} | {d.sum():+.4f} | {share * 100:.0f}% | {sign_p(w, l):.2f} |")
