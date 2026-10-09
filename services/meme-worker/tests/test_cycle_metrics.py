"""EXP-M26 §6.8 — the cycle time of the chain loop and of the Lab loop, measured.

What this file keeps true:

- **a cycle is its wall duration in whole milliseconds**, kept in a fixed-size ring
  (bounded memory) — the percentiles are over that window, not since boot;
- **an unmeasured number is ``""``, never ``0``** (no cycle yet = no percentile);
- **an overrun is a cycle longer than the loop's nominal period**, counted every
  time and logged at most once per throttle window (no log spam);
- **the wrapper changes nothing about the loop**: it returns what the step
  returns, re-raises what the step raises (``forever`` takes the process down on
  a failure, as before), and a failing publish never stops the loop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_meme_worker.cycle_metrics import CycleMeter, announce, timed_step

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _meter(window: int = 5, nominal_s: float = 60.0) -> CycleMeter:
    return CycleMeter("chain", nominal_s=nominal_s, window=window)


def test_no_cycle_yet_publishes_empty_strings_not_zeros() -> None:
    fields = _meter().fields()
    assert fields["chain_cycles_total"] == "0"
    assert fields["chain_overruns_total"] == "0"
    for name in ("last_cycle_ms", "cycle_ms_p50", "cycle_ms_p95", "cycle_ms_p99", "last_cycle_at"):
        assert fields[f"chain_{name}"] == "", name
    assert fields["chain_cycle_nominal_ms"] == "60000"
    assert fields["chain_cycle_window_n"] == "0"


def test_percentiles_are_nearest_rank_over_the_window() -> None:
    meter = _meter(window=100)
    for ms in range(1, 101):  # 1..100 ms
        meter.record(ms, T0)
    fields = meter.fields()
    assert fields["chain_cycle_ms_p50"] == "50"
    assert fields["chain_cycle_ms_p95"] == "95"
    assert fields["chain_cycle_ms_p99"] == "99"
    assert fields["chain_cycle_ms_max"] == "100"
    assert fields["chain_last_cycle_ms"] == "100"
    assert fields["chain_cycles_total"] == "100"
    assert fields["chain_cycle_window_n"] == "100"


def test_the_ring_is_bounded_and_totals_keep_counting() -> None:
    meter = _meter(window=3)
    for ms in (900, 10, 20, 30):  # the 900 falls out of the window
        meter.record(ms, T0)
    fields = meter.fields()
    assert fields["chain_cycle_window_n"] == "3"
    assert fields["chain_cycle_ms_max"] == "30"
    assert fields["chain_cycles_total"] == "4"


def test_last_cycle_at_is_utc_iso() -> None:
    meter = _meter()
    meter.record(5, T0)
    assert meter.fields()["chain_last_cycle_at"] == "2026-10-07T12:00:00+00:00"


def test_an_overrun_is_a_cycle_longer_than_the_nominal_period() -> None:
    meter = _meter(nominal_s=60.0)
    assert meter.record(60_000, T0) is False  # exactly on time is not an overrun
    assert meter.record(60_001, T0) is True
    assert meter.record(120_000, T0) is True
    assert meter.fields()["chain_overruns_total"] == "2"


def test_a_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _meter().record(1, datetime(2026, 10, 7, 12, 0))  # noqa: DTZ001 - the point of the test


def test_a_non_utc_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="UTC"):
        _meter().record(1, datetime(2026, 10, 7, 9, 0, tzinfo=timezone(timedelta(hours=-3))))


def test_every_publication_names_its_generation() -> None:
    """Astra (must-fix 2): a reader must tell this process's numbers from a previous
    process's, so each meter carries a run id and its UTC start."""
    a = CycleMeter("chain", nominal_s=60.0, window=3, started_at=T0)
    b = CycleMeter("chain", nominal_s=60.0, window=3, started_at=T0)
    fields = a.fields()
    assert fields["chain_cycle_since"] == "2026-10-07T12:00:00+00:00"
    assert fields["chain_cycle_run_id"] == a.run_id != b.run_id
    a.record(5, T0)
    assert a.fields()["chain_cycle_run_id"] == a.run_id


def test_a_negative_duration_is_refused() -> None:
    with pytest.raises(ValueError, match="duration"):
        _meter().record(-1, T0)


def test_prefix_is_the_loop_name() -> None:
    meter = CycleMeter("lab", nominal_s=15.0, window=4)
    meter.record(20_000, T0)
    fields = meter.fields()
    assert fields["lab_last_cycle_ms"] == "20000"
    assert fields["lab_cycle_nominal_ms"] == "15000"
    assert all(key.startswith("lab_") for key in fields)


def test_window_must_be_positive() -> None:
    with pytest.raises(ValueError, match="window"):
        CycleMeter("chain", nominal_s=60.0, window=0)


class _Clock:
    """A monotonic nanosecond clock the test advances by hand."""

    def __init__(self) -> None:
        self.t = 100_000_000_000

    def advance(self, seconds: float) -> None:
        self.t += round(seconds * 1_000_000_000)

    def __call__(self) -> int:
        return self.t


def _wrapper(
    meter: CycleMeter,
    *,
    cost_s: float,
    published: list[dict[str, str]],
    clock: _Clock,
    log_every_s: float = 300.0,
    now: datetime = T0,
) -> Callable[[object], Coroutine[Any, Any, str]]:
    async def step(ctx: object) -> str:
        clock.advance(cost_s)
        return "report"

    async def publish(fields: dict[str, str]) -> None:
        published.append(fields)

    return timed_step(meter, step, publish, clock=clock, now=lambda: now, log_every_s=log_every_s)


def _run_wrapped(meter: CycleMeter, **kwargs: Any) -> str:
    return asyncio.run(_wrapper(meter, **kwargs)(object()))


def test_the_wrapper_returns_what_the_step_returns_and_publishes_the_cycle() -> None:
    meter, clock = _meter(), _Clock()
    published: list[dict[str, str]] = []
    result = _run_wrapped(meter, cost_s=1.5, published=published, clock=clock)
    assert result == "report"
    assert len(published) == 1
    assert published[0]["chain_last_cycle_ms"] == "1500"  # whole ms, never float
    assert published[0]["chain_cycles_total"] == "1"


def test_an_overrun_logs_once_per_throttle_window_and_always_counts() -> None:
    meter, clock = _meter(nominal_s=1.0), _Clock()
    published: list[dict[str, str]] = []
    with capture_logs() as logs:
        wrapped = _wrapper(meter, cost_s=3.0, published=published, clock=clock)
        for _ in range(3):  # three overruns in a row, 3 s apart on the monotonic clock
            asyncio.run(wrapped(object()))
    overruns = [e for e in logs if e["event"] == "meme_cycle_overrun"]
    assert len(overruns) == 1  # throttled
    assert overruns[0]["loop"] == "chain"
    assert overruns[0]["duration_ms"] == 3000
    assert overruns[0]["nominal_ms"] == 1000
    assert published[-1]["chain_overruns_total"] == "3"


def test_the_throttle_reopens_and_reports_what_it_swallowed() -> None:
    meter, clock = _meter(nominal_s=1.0), _Clock()
    published: list[dict[str, str]] = []
    with capture_logs() as logs:
        wrapped = _wrapper(meter, cost_s=3.0, published=published, clock=clock, log_every_s=5.0)
        for _ in range(3):
            asyncio.run(wrapped(object()))
    overruns = [e for e in logs if e["event"] == "meme_cycle_overrun"]
    assert len(overruns) == 2  # t=3 s logs; t=6 s is 3 s later, swallowed; t=9 s is 6 s later, logs
    assert overruns[1]["suppressed"] == 1


def test_an_on_time_cycle_does_not_log() -> None:
    meter, clock = _meter(nominal_s=60.0), _Clock()
    published: list[dict[str, str]] = []
    with capture_logs() as logs:
        _run_wrapped(meter, cost_s=0.5, published=published, clock=clock)
    assert [e for e in logs if e["event"] == "meme_cycle_overrun"] == []


def test_a_failing_step_is_reraised_and_not_recorded() -> None:
    meter, clock = _meter(), _Clock()
    published: list[dict[str, str]] = []

    async def boom(ctx: object) -> None:
        raise RuntimeError("chain exploded")

    async def publish(fields: dict[str, str]) -> None:
        published.append(fields)

    wrapped = timed_step(meter, boom, publish, clock=clock, now=lambda: T0)
    with pytest.raises(RuntimeError, match="chain exploded"):
        asyncio.run(wrapped(object()))
    assert published == []
    assert meter.fields()["chain_cycles_total"] == "0"


def test_a_failing_publish_never_stops_the_loop() -> None:
    meter, clock = _meter(), _Clock()

    async def step(ctx: object) -> str:
        clock.advance(0.01)
        return "ok"

    async def publish(fields: dict[str, str]) -> None:
        raise ConnectionError("redis down")

    wrapped = timed_step(meter, step, publish, clock=clock, now=lambda: T0)
    with capture_logs() as logs:
        assert asyncio.run(wrapped(object())) == "ok"
    assert any(e["event"] == "meme_cycle_metrics_publish_failed" for e in logs)
    assert meter.fields()["chain_cycles_total"] == "1"


def test_the_clock_is_the_only_time_source_for_duration() -> None:
    # utcnow's wall time must not leak into the duration: a step that "takes" a
    # day on the wall clock but 10 ms on the monotonic one is a 10 ms cycle.
    meter, clock = _meter(), _Clock()
    published: list[dict[str, str]] = []
    _run_wrapped(meter, cost_s=0.010, published=published, clock=clock, now=T0 + timedelta(days=1))
    assert published[0]["chain_last_cycle_ms"] == "10"
    assert published[0]["chain_last_cycle_at"].startswith("2026-10-08")


async def test_composed_with_forever_it_records_every_cycle_and_the_cancel_still_ends_the_loop() -> (
    None
):
    from hunter_meme_worker.collect import forever

    meter = CycleMeter("lab", nominal_s=15.0, window=4)
    seen: list[dict[str, str]] = []
    done = asyncio.Event()

    async def step(ctx: object) -> None:
        await asyncio.sleep(0)

    async def publish(fields: dict[str, str]) -> None:
        seen.append(fields)
        if len(seen) == 3:
            done.set()

    task = asyncio.create_task(forever("lab", 0.0, timed_step(meter, step, publish), object()))
    await asyncio.wait_for(done.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert seen[2]["lab_cycles_total"] == "3"
    assert seen[2]["lab_overruns_total"] == "0"


async def test_a_publish_that_hangs_costs_the_loop_only_its_budget() -> None:
    """Astra (must-fix 1): the extra HSET must not stall the loop for the Redis client's
    5 s x 3 retries. It has a budget of its own; a miss is counted, never raised."""
    meter, clock = _meter(), _Clock()

    async def step(ctx: object) -> str:
        clock.advance(0.01)
        return "ok"

    async def hang(fields: dict[str, str]) -> None:
        await asyncio.sleep(30)

    wrapped = timed_step(meter, step, hang, clock=clock, now=lambda: T0, publish_budget_s=0.05)
    started = time.monotonic()
    with capture_logs() as logs:
        assert await asyncio.wait_for(wrapped(object()), timeout=2) == "ok"
    assert time.monotonic() - started < 0.5  # the 50 ms budget, not the 1 s default
    assert any(e["event"] == "meme_cycle_metrics_publish_failed" for e in logs)
    assert meter.publish_failed_total == 1
    assert meter.fields()["chain_cycle_publish_failed_total"] == "1"


async def test_announce_publishes_the_empty_generation_before_the_first_cycle() -> None:
    """A fresh process overwrites the previous process's stale fields at boot."""
    meter = CycleMeter("lab", nominal_s=15.0, window=4, started_at=T0)
    seen: list[dict[str, str]] = []

    async def publish(fields: dict[str, str]) -> None:
        seen.append(fields)

    await announce(meter, publish)
    assert seen[0]["lab_cycles_total"] == "0"
    assert seen[0]["lab_cycle_ms_p95"] == ""
    assert seen[0]["lab_cycle_run_id"] == meter.run_id


async def test_announce_survives_a_dead_redis() -> None:
    async def publish(fields: dict[str, str]) -> None:
        raise ConnectionError("redis down")

    with capture_logs() as logs:
        await announce(_meter(), publish)
    assert any(e["event"] == "meme_cycle_metrics_publish_failed" for e in logs)
