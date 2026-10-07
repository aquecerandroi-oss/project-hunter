"""Conferência: a recomposição reproduz o R gravado pelo Lab? (instrumento, antes de qualquer agregação)."""
import collections, csv, gzip, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sweep
rows = list(csv.DictReader(gzip.open(Path(__file__).parent / "cache/out.csv.gz", "rt", encoding="utf-8")))
bad, skipped, diffs, diffs_ex, reasons, costs = 0, collections.Counter(), [], [], collections.Counter(), collections.Counter()
for r in rows:
    if not r["entry_c"] or not r["exit_base"] or not r["stop"]:
        skipped[(r["mt"], r["result"])] += 1; continue
    t = sweep.Trade.from_row(r)
    costs[(r["spread_bps"], r["slippage_bps"], r["fee_bps"])] += 1
    reasons[(t.mt, (r["r_net_reason"] or "-").split(":")[0], r["r_multiple"] == "")] += 1
    if t.r_lab is not None:
        diffs.append(abs(t.lab_r_recomputed() - t.r_lab))
    if t.r_lab_ex is not None:
        diffs_ex.append(abs(t.scenario_r(fee_bp=t.f_bp, slip_bp=t.c_bp, with_funding=False) - t.r_lab_ex))
print("linhas", len(rows), "sem insumos", dict(skipped))
print("custos assumidos (spread, slip, fee) ->", dict(costs))
print("motivo funding (mt, reason, r_multiple nulo) ->", dict(reasons))
print("r_multiple: n", len(diffs), "max|dif|", max(diffs), "n>1e-6", sum(d > 1e-6 for d in diffs))
print("r_ex_funding: n", len(diffs_ex), "max|dif|", max(diffs_ex), "n>1e-6", sum(d > 1e-6 for d in diffs_ex))
ts = [sweep.Trade.from_row(r) for r in rows]
small = collections.Counter((t.strategy, t.version) for t in ts if (t.open - t.stop) < 0.1 * t.risk)
print("abertura a < 10 % da unidade de risco do stop (O − S < 0,1·U; onde O − S como denominador explodiria):",
      sum(small.values()), dict(small.most_common(6)))
