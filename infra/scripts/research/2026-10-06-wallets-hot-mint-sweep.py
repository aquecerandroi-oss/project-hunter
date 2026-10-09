"""How one hot mint's replay grows with its events per hour (CPU plan step 3, 06/10/2026).

SYNTHETIC — NOT MARKET DATA (generator ``kb0183-shape-v2``). The per-mint density of the real
program is unmeasured (the wave-0 probe kept no per-mint counts; see
``2026-10-06-wallet-tape-density-probe.py``), so the nightly cost can only be extrapolated
CONDITIONAL on it. This sweep measures, on the current engine, the replay of the generator's HOT
mint alone (``stream.replay_window``) for ``hot_fills`` events packed in ``hot_minutes``, on top
of the base background (8 000 fills/day, 2-day window, last night):

- CPU (``process_time``, min of ``--repeat``, the pricing memo emptied before each);
- deterministic work: the mint's copies (bets) and its stop quotes (``policy.sell_lamports``
  calls), immune to the shared machine's load.

Run: ``uv run python infra/scripts/research/2026-10-06-wallets-hot-mint-sweep.py --out <file>``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from hunter_indicators.meme.wallets import policy, pricing, stream
from hunter_indicators.meme.wallets.params import RankingParams

_spec = importlib.util.spec_from_file_location(
    "wbench", Path(__file__).with_name("2026-10-06-wallets-engine-workers.py")
)
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
sys.modules["wbench"] = bench
_spec.loader.exec_module(bench)


def point(hot: int, minutes: int, repeat: int) -> dict[str, Any]:
    cfg = replace(bench.gen.Config(), name=f"hot_{hot}", hot_fills=hot, hot_minutes=minutes)
    inputs, ws, day, _ = bench.nights(cfg)
    plan = stream.plan_night(inputs, day, params=RankingParams(window_days=cfg.window))
    window = next(w for w in ws if w.carry.mint == "HOT")
    saved, calls = policy.sell_lamports, [0]

    def counted(*a: Any, **k: Any) -> Any:
        calls[0] += 1
        return saved(*a, **k)

    policy.sell_lamports = counted  # type: ignore[assignment]
    try:
        pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
        stream.replay_window(plan, window)
    finally:
        policy.sell_lamports = saved  # type: ignore[assignment]
    cpus: list[float] = []
    for _ in range(repeat):
        pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
        c0 = time.process_time()
        stream.replay_window(plan, window)
        cpus.append(time.process_time() - c0)
    return {"hot_fills": hot, "hot_minutes": minutes, "events": plan.events["HOT"],
            "copies": len(plan.bets.get("HOT", ())), "stop_quotes": calls[0],
            "cpu_s": min(cpus), "cpu_runs": cpus}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hot", default="1000,2000,4000,8000,16000")
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    lines = ["SYNTHETIC sweep (not market data) — one hot mint's replay vs its events per hour"]
    rows: list[dict[str, Any]] = []
    for hot in (int(x) for x in args.hot.split(",")):
        row = point(hot, args.minutes, args.repeat)
        rows.append(row)
        line = (f"hot {hot:>6} in {args.minutes} min: events {row['events']:>6} copies "
                f"{row['copies']:>5} stop quotes {row['stop_quotes']:>10,} cpu {row['cpu_s']:.2f}s")  # fmt: skip
        print(line, flush=True)
        lines += ["ROW " + json.dumps(row), line]
    for key in ("stop_quotes", "cpu_s"):
        pairs = [(math.log(r["events"]), math.log(max(r[key], 1e-9))) for r in rows]
        for (x0, y0), (x1, y1) in zip(pairs, pairs[1:], strict=False):
            lines.append(f"local exponent of {key} vs events: {(y1 - y0) / (x1 - x0):.2f}")
    print("\n".join(lines[-2 * (len(rows) - 1) :]))
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
