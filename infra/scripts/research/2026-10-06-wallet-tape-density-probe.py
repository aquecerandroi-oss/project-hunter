"""Per-mint event density of the WHOLE pump.fun + PumpSwap program (CPU plan step 3, 06/10/2026).

Why: the bounded wallets engine costs more than linearly per mint (a copy's stop scans the mint's
next hour), so the nightly CPU depends on how events spread over mints — and the wave-0 probe kept
only the SET of mints/pools (``ProbeStats.keys``), never a count per key. This script is the same
probe (``2026-10-05-wallet-tape-probe.py``: public RPC ``logsSubscribe``, read-only, never the VPS,
never ``.env``) with one more counter: swap events per key per minute, where the key is the curve
mint (``TradeEvent``) or the PumpSwap pool (``SellEvent``/``BuyEvent``; a log line carries no
account list, so pool → mint is not joined here: a graduated mint's curve and pool are two keys).

Output ``density.json`` in ``--out``: per key the minute counts; the histogram of events per key;
the top keys and their share; per key the most events inside ANY 60 min (an exact sliding window
over the event timestamps, not minute-aligned buckets) and how many keys reach 1 000 — only when
the run itself lasted ≥ 3 600 s (unrounded); a shorter run says so, never an extrapolation.
PumpSwap buys keyed by the INFERRED pool (a layout reading, not a confirmed decoder) are counted
apart (``inferred_keyed_swap_events``). The probe's usual
``snapshots.jsonl``/``summary.json`` are written too.

WebSocket only with ``--sample-every 0 --audit-every 0`` (the sampler, the tip poller and the
block audit return before opening an HTTP client). The run STOPS at the first server refusal and
at the first suspension of the machine (the probe's sleep detector), so the data is one
continuous stretch; ``stop_reason`` says which. Ask for 3 720 s: the capture is measured up to the
last frame received, so a 3 600-s run would end a hair short of a full hour.

    uv run --no-sync python infra/scripts/research/2026-10-06-wallet-tape-density-probe.py \\
        --seconds 3720 --sample-every 0 --audit-every 0 --keep-awake \\
        --out .claude/state/carteiras-lucro/density/run1
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from array import array
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wallet_tape_probe_core import AMM, PUMP, LogEvent, decode_event
from wallet_tape_probe_net import run
from wallet_tape_probe_rt import Runtime
from wallet_tape_probe_stats import ProbeStats

_BINS = (1, 10, 100, 1_000, 10_000, 100_000)
_HOUR_S = 3_600.0


class DensityStats(ProbeStats):
    """``ProbeStats`` plus swap events per (program, key): per minute since the start, and every
    event's receive time (8 bytes each, for the exact sliding hour)."""

    def __init__(self, started: float) -> None:
        super().__init__(started)
        self.per_key: dict[tuple[str, str], Counter[int]] = {}
        self.times: dict[tuple[str, str], array[float]] = {}
        self.unkeyed = 0
        self.inferred = 0
        self.last_received: float | None = None
        """Receive stamp of the latest notification, never cleared (``ProbeStats.last_t`` is
        dropped on every reconnect — Astra, round 3)."""
        self.refusals: list[str] = []

    def on_reject(self, sub: str, now: float, reason: str) -> None:
        super().on_reject(sub, now, reason)
        self.refusals.append(f"{sub} at {now - self.started:.1f}s: {reason[:160]}")

    def on_logs(
        self, sub: str, slot: int, sig: str, err: Any, logs: list[str], nbytes: int, now: float
    ) -> Any:
        self.last_received = now if self.last_received is None else max(self.last_received, now)
        return super().on_logs(sub, slot, sig, err, logs, nbytes, now)

    def _event(self, event: LogEvent, slot: int, sig: str, now: float) -> bool:
        swap = super()._event(event, slot, sig, now)
        if swap:
            d = decode_event(event)
            key = d.key if event.program == PUMP else (d.key or d.inferred_pool)
            if key is None:
                self.unkeyed += 1
            else:
                self.inferred += d.key is None
                prog = "curve" if event.program == PUMP else "pool" if event.program == AMM else "?"
                minute = int((now - self.started) // 60)
                self.per_key.setdefault((prog, key), Counter())[minute] += 1
                self.times.setdefault((prog, key), array("d")).append(now)
        return swap


def capture_seconds(stats: DensityStats, t0: float, requested: float) -> float:
    """How long reception lasted: up to the socket receive stamp of the last notification (not
    the end of the probe, whose queue drain after an interrupt can add up to 60 s — Astra,
    round 2), unrounded, never beyond the requested capture."""
    last = t0 if stats.last_received is None else stats.last_received
    return min(last - t0, requested)


def busiest_hour(times: array[float]) -> int:
    """The most events inside any window of 3 600 s (two pointers over the sorted times)."""
    ordered, best, lo = sorted(times), 0, 0
    for hi, t in enumerate(ordered):
        while t - ordered[lo] >= _HOUR_S:
            lo += 1
        best = max(best, hi - lo + 1)
    return best


def density(stats: DensityStats, elapsed_s: float) -> dict[str, Any]:
    totals = {k: sum(c.values()) for k, c in stats.per_key.items()}
    all_events = sum(totals.values())
    hist = Counter(
        next((f"<{b}" for b in _BINS if n < b), f">={_BINS[-1]}") for n in totals.values()
    )
    hours = {k: busiest_hour(t) for k, t in stats.times.items()} if elapsed_s >= _HOUR_S else {}
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:50]
    return {
        "elapsed_s": elapsed_s,
        "keys": len(totals),
        "keyed_swap_events": all_events,
        "unkeyed_swap_events": stats.unkeyed,
        "inferred_keyed_swap_events": stats.inferred,
        "histogram_events_per_key_whole_run": dict(sorted(hist.items())),
        "top": [
            {
                "program": k[0],
                "key": k[1],
                "events": n,
                "share": n / max(1, all_events),
                "max_per_minute": max(stats.per_key[k].values()),
                "busiest_60min": hours.get(k),
            }
            for k, n in top
        ],  # fmt: skip
        "top1_share": top[0][1] / max(1, all_events) if top else None,
        "top10_share": sum(n for _, n in top[:10]) / max(1, all_events),
        "busiest_60min_per_key": {f"{k[0]}:{k[1]}": v for k, v in hours.items()},
        "keys_over_1000_in_a_rolling_60min": (
            sum(1 for v in hours.values() if v >= 1_000)
            if elapsed_s >= _HOUR_S
            else f"run of {elapsed_s:.1f} s, shorter than 3 600 s"
        ),
        "per_key_minutes": {f"{k[0]}:{k[1]}": dict(c) for k, c in stats.per_key.items()},
    }


def main() -> None:
    spec = importlib.util.spec_from_file_location(
        "probe_main", Path(__file__).with_name("2026-10-05-wallet-tape-probe.py")
    )
    assert spec is not None and spec.loader is not None
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    async def run_density(rt: Runtime) -> None:
        stats = DensityStats(rt.t0)
        rt.stats = stats
        requested, stop = float(rt.args.seconds), {"reason": "requested duration"}

        async def guard() -> None:  # the probe's loop ends when ``seconds`` is reached
            while True:
                await asyncio.sleep(1)
                if stats.refusals or stats.suspensions:
                    stop["reason"] = "refusal" if stats.refusals else "suspension"
                    print(f"STOP: {stop['reason']}", flush=True)
                    rt.args.seconds = 0
                    return

        watcher = asyncio.create_task(guard())
        try:
            await run(rt)
        finally:
            watcher.cancel()
            elapsed = capture_seconds(stats, rt.t0, requested)
            out = density(stats, elapsed)
            out.update(stop_reason=stop["reason"], requested_s=requested,
                       refusals=stats.refusals, suspensions=stats.suspensions)  # fmt: skip
            (rt.out / "density.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    vars(probe)["run"] = run_density  # the probe's main builds the Runtime and awaits ``run``
    probe.main()


if __name__ == "__main__":
    main()
