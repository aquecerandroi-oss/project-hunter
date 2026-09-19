from datetime import timedelta
exec(open("sim.py").read().split("def fill_after")[0])
def fill_after(path, t, tokens):
    last = path[0]
    for p in path:
        if p[0] <= t: last = p
        else: break
    return net(last[1], last[2], tokens)
def everton(P, trailing, target=1.15, hold=300, L=2, arm_after=0):
    path = paths[P["tag"]]
    if not path: return None
    entry = ts(P["entry_bt"]); tokens = P["tokens"]; spent = P["spent"]
    peak = path[0][3]
    for p in path[1:]:
        dt = (p[0] - entry).total_seconds()
        if dt > hold: return fill_after(path, entry + timedelta(seconds=hold + L), tokens), "time"
        m = p[3]
        if dt >= arm_after: peak = max(peak, m)
        if m >= target * spent: return fill_after(path, p[0] + timedelta(seconds=L), tokens), "target"
        if trailing and dt >= arm_after and m <= peak * (1 - trailing): return fill_after(path, p[0] + timedelta(seconds=L), tokens), "trailing"
    return fill_after(path, path[-1][0], tokens), "censored"
print("variant | total SOL (7 with tape; Cupsey#2 real) | per position")
for name, kw in [("trail10 (real rule)", dict(trailing=0.10)), ("trail15", dict(trailing=0.15)), ("trail20", dict(trailing=0.20)), ("trail30", dict(trailing=0.30)), ("no trailing, 5 min", dict(trailing=None)), ("trail10 armed after 30 s", dict(trailing=0.10, arm_after=30)), ("trail20 + target 1.30", dict(trailing=0.20, target=1.30)), ("trail10 + target 1.50", dict(trailing=0.10, target=1.50))]:
    tot = 0; cells = []
    for P in positions:
        r = everton(P, **kw)
        if r is None: pnl = P["exit_net"] - P["spent"]; cells.append("%s %+.0f%%(real)" % (P["tag"], pnl / P["spent"] * 100))
        else: pnl = r[0] - P["spent"]; cells.append("%s %+.0f%%(%s)" % (P["tag"], pnl / P["spent"] * 100, r[1][:4]))
        tot += pnl
    print("%-26s | %+.4f | %s" % (name, tot / 1e9, ", ".join(cells)))
print("real total: %+.4f" % (sum(P["exit_net"] - P["spent"] for P in positions) / 1e9))
