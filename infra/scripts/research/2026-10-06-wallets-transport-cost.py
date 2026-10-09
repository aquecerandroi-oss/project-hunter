"""What a worker pays besides the replay (CPU plan step 3, 06/10/2026) — measured in ONE process.

SYNTHETIC — NOT MARKET DATA (generator ``kb0183-shape-v2``). For the last night of a bench config
(``2026-10-06-wallets-engine-workers.py``), every mint goes through what the parallel engine
does around ``stream.replay_window``, timed by ``process_time`` and summed over the mints:

- ``load_window`` — unpickling the mint's window (the bench workers' ``FileFetch``; in
  production, the storage read);
- ``replay`` — the replay itself, with a fresh tally per mint;
- ``dump_part`` / ``load_part`` — the tallies and next carry pickled in the worker and unpickled
  by the coordinator (one part per mint here: the engine packs small mints, so this is the
  unpacked upper end);
- ``merge`` — the coordinator's exact reduction.

Plus the import of the engine in a fresh interpreter (what each spawned worker pays at start),
``--imports`` times. Windows' ``process_time`` ticks at 15.6 ms: per-mint sums are approximate.
Run: ``uv run python infra/scripts/research/2026-10-06-wallets-transport-cost.py --out <file>``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from hunter_indicators.meme.wallets import pricing, stream
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.stream_mint import Tallies

_spec = importlib.util.spec_from_file_location(
    "wbench", Path(__file__).with_name("2026-10-06-wallets-engine-workers.py")
)
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
sys.modules["wbench"] = bench
_spec.loader.exec_module(bench)
_IMPORT = (
    "import time; t = time.perf_counter(); "
    "import hunter_indicators.meme.wallets.stream_parallel; print(time.perf_counter() - t)"
)


def breakdown(name: str) -> dict[str, Any]:
    cfg = replace(bench.gen.Config(), **next(c for c in bench.CONFIGS if c["name"] == name))
    inputs, ws, day, window_fills = bench.nights(cfg)
    plan = stream.plan_night(inputs, day, params=RankingParams(window_days=cfg.window))
    blobs = [pickle.dumps(w) for w in ws]
    acc = dict.fromkeys(("load_window", "replay", "dump_part", "load_part", "merge"), 0.0)
    part_bytes, tallies = 0, Tallies()
    pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
    for blob in blobs:
        t = time.process_time()
        window = pickle.loads(blob)  # noqa: S301 — own bytes
        acc["load_window"] += time.process_time() - t
        t = time.process_time()
        part = stream.replay_window(plan, window)
        acc["replay"] += time.process_time() - t
        t = time.process_time()
        raw = pickle.dumps((part.tallies, part.carry))  # what a chunk carries back, per mint
        acc["dump_part"] += time.process_time() - t
        part_bytes += len(raw)
        t = time.process_time()
        back = pickle.loads(raw)  # noqa: S301 — own bytes
        acc["load_part"] += time.process_time() - t
        t = time.process_time()
        tallies.merge(back[0])
        acc["merge"] += time.process_time() - t
    return {"config": name, "mints": len(ws), "window_fills": window_fills,
            "window_events": sum(len(w.fills) for w in ws), "window_mb": sum(map(len, blobs)) / 1e6,
            "part_mb": part_bytes / 1e6, "cpu_s": acc}  # fmt: skip


def imports(times: int) -> list[float]:
    out: list[float] = []
    for _ in range(times):
        run = subprocess.run(
            [sys.executable, "-c", _IMPORT], capture_output=True, text=True, check=True
        )
        out.append(float(run.stdout.strip()))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="base,window7")
    ap.add_argument("--imports", type=int, default=3)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    lines = ["SYNTHETIC (not market data) — per-mint transport around the replay, one process"]
    for name in args.only.split(","):
        row = breakdown(name)
        cpu, n = row["cpu_s"], max(1, row["window_events"])
        line = (f"{name}: mints {row['mints']} window events {row['window_events']} | "
                + " ".join(f"{k} {v:.3f}s" for k, v in cpu.items())
                + f" | load {1e6 * cpu['load_window'] / n:.0f} us/event, parts round trip "
                f"{1e3 * (cpu['dump_part'] + cpu['load_part']) / row['mints']:.2f} ms/mint")  # fmt: skip
        print(line, flush=True)
        lines += ["ROW " + json.dumps(row), line]
    secs = imports(args.imports)
    line = f"engine import in a fresh interpreter: {', '.join(f'{s:.2f}' for s in secs)} s"
    print(line)
    lines.append(line)
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
