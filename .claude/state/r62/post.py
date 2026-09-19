import json
from datetime import timedelta
exec(open("sim.py").read().split("def fill_after")[0])
for P in positions:
    path = paths[P["tag"]]
    if not path: print(P["tag"], "no tape"); continue
    entry = ts(P["entry_bt"]); exit_bt = ts(P["exit_bt"]); tokens = P["tokens"]
    hold_end = entry + timedelta(seconds=300)
    after = [p for p in path if p[0] > exit_bt]
    within = [p for p in after if p[0] <= hold_end]
    mx = max(within, key=lambda p: p[3]) if within else None
    mx_all = max(after, key=lambda p: p[3]) if after else None
    at_end = [p for p in path if p[0] <= hold_end][-1]
    first_after = after[0] if after else None
    print("%-10s exit_net %.4f | max within hold %.4f at %s (%+.0f%% vs exit, %+.0f%% vs spent) | mark at hold end %.4f (%+.0f%% vs spent) | max ever %.4f at %s | next trade after exit %s" % (
        P["tag"], P["exit_net"] / 1e9, mx[3] / 1e9 if mx else 0, brt(mx[0]) if mx else "-", (mx[3] / P["exit_net"] - 1) * 100 if mx else 0, (mx[3] / P["spent"] - 1) * 100 if mx else 0,
        at_end[3] / 1e9, (at_end[3] / P["spent"] - 1) * 100, mx_all[3] / 1e9, brt(mx_all[0]), brt(first_after[0]) if first_after else "-"))
