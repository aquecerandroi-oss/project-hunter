"""T2.5e: "caught up" is a bounded delay, not an empty queue.

``.claude/state/brief-T2.5e-coverage-caught-up.md``: after T2.5-adapter,
``mkt:binance:coverage`` froze -- one transition to
``reason="queue_backlog"`` that never resolved, measured on the local stack
and on the VPS (21:24-21:40Z, 8 breaks). Confirmed here and on the running
local stack: under continuous flow (~150 msg/s across 200 markets), the old
rule (``enqueued == delivered + evicted``, ``hunter_market_worker.coverage``)
is caught true only in the instant the shared queue is fully empty, which is
almost never -- so the interval broke on nearly every stamp and, once
broken, stayed broken (the warning only logs on *entering* the break).

The fix (``CoverageTracker.stamp``, ``oldest_pending_ts``) trades "empty
queue" for "bounded delay": a nonzero backlog only breaks the interval when
the oldest pending event's own timestamp has itself reached the window a
stamp is about to claim covered.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import NormalizedTrade
from hunter_core.redis import keys
from hunter_exchanges.base import ConnectionState
from hunter_exchanges.binance.event_queue import StreamConsumer
from hunter_market_worker.coverage import COVERAGE_SAFETY_S, CoverageTracker


def _at(second: float) -> datetime:
    return datetime(2026, 9, 6, 21, 24, 0, tzinfo=UTC) + timedelta(seconds=second)


def _trade(seq: int, ts: datetime) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="binance",
        symbol="BTCUSDT",
        ts=ts,
        trade_id=str(seq),
        price=Decimal("1"),
        qty=Decimal("1"),
        side=OrderSide.BUY,
    )


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def hdel(self, key: str, *fields: str) -> int:
        entry = self.hashes.get(key, {})
        return sum(1 for field in fields if entry.pop(field, None) is not None)

    async def expire(self, key: str, ttl: int) -> bool:
        return True


# ---- Item 1: reproduction ----------------------------------------------------


async def test_a_continuous_producer_and_a_keeping_up_consumer_do_not_break_coverage() -> None:
    """The brief's reproduction: a real ``BoundedEventQueue``/``StreamConsumer``
    pair, one producer that never stops, one consumer that drains as fast as
    it can (no artificial slowness). Confirms the hypothesis first (exact
    equality is rare), then confirms the new rule does not break on it, and
    that ``covered_until`` only ever advances -- never past what the stamp
    itself computes as safe, and never freezing on a backlog that is, in
    fact, bounded and fresh."""
    consumer = StreamConsumer(maxsize=10_000)
    states = {"market:0": ConnectionState(route="market", ws_state="connected")}
    stop = asyncio.Event()
    seq = 0

    async def produce() -> None:
        # ~200 msg/s -- the brief's measured production throughput (~150/s
        # across 200 markets), not an unbounded tight loop: a producer with
        # no rate limit at all would outrun *any* consumer's per-item
        # overhead and is not what "keeps up" is meant to reproduce.
        nonlocal seq
        while not stop.is_set():
            seq += 1
            await consumer.put("market:0", _trade(seq, datetime.now(UTC)), states)
            await asyncio.sleep(0.005)

    async def close() -> None:
        return None

    async def consume() -> None:
        agen: Any = consumer.consume(close)
        async for _ in agen:
            pass  # keeps up: no delay between deliveries

    producer_task = asyncio.ensure_future(produce())
    consumer_task = asyncio.ensure_future(consume())
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"])
    redis: Any = FakeRedis()

    exact_equality_hits = 0
    total_stamps = 0
    covered_untils: list[str] = []
    try:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 1.0
        while loop.time() < deadline:
            await asyncio.sleep(0.05)
            enqueued, evicted = consumer.queue.progress()
            delivered = consumer.delivered
            total_stamps += 1
            if enqueued == delivered + evicted:
                exact_equality_hits += 1
            await tracker.stamp(
                redis,
                dropped_events=0,
                queue_progress=(enqueued, delivered, evicted),
                oldest_pending_ts=consumer.oldest_pending_ts(),
            )
            covered_untils.append(redis.hashes[keys.tape_coverage("binance")]["covered_until"])
    finally:
        stop.set()
        producer_task.cancel()
        consumer_task.cancel()
        for task in (producer_task, consumer_task):
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # Confirms the hypothesis: under continuous flow, exact equality
    # ("queue fully empty at stamp time") was not the common case.
    assert exact_equality_hits < total_stamps

    # The fix: the tracker never latched into a break that outlived it, and
    # the published interval kept advancing instead of freezing at its first
    # value -- the exact symptom measured in production (session_since ==
    # covered_until, frozen, `.claude/state/notes-T2.5.md` T2.5e section).
    assert tracker._break_reason is None
    assert len(set(covered_untils)) > 1
    assert covered_untils[-1] != covered_untils[0]

    # And it never claimed *past* what the fresh margin allows: every
    # published `covered_until` is at or behind `now - COVERAGE_SAFETY_S` at
    # the moment it was published (the wall clock, not `delivered`, is the
    # thing that still bounds progress -- `delivered` only ever widens the
    # backlog tolerance, never the claim itself).
    last_covered_until = datetime.fromisoformat(covered_untils[-1])
    assert last_covered_until <= datetime.now(UTC)


# ---- Item 2: honesty ----------------------------------------------------


async def test_a_consumer_that_falls_behind_still_breaks_by_queue_backlog() -> None:
    """A backlog that is not bounded -- growing, and old enough that its
    oldest member has itself reached the claimed window -- must still break.
    The bounded-delay rule is not "any backlog is fine"."""
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(
        redis, dropped_events=0, now=_at(1), queue_progress=(1, 1, 0), oldest_pending_ts=None
    )
    healthy = redis.hashes[keys.tape_coverage("binance")]["covered_until"]

    # The consumer has stopped keeping up: backlog grows, and the oldest
    # pending event is well behind the safety margin by the time of this
    # stamp (candidate cut is `_at(2) - 0.5s` = `_at(1.5)`).
    stale_pending = _at(1.5) - timedelta(seconds=1)
    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(2),
        queue_progress=(50, 1, 0),
        oldest_pending_ts=stale_pending,
    )

    frozen = redis.hashes[keys.tape_coverage("binance")]["covered_until"]
    assert frozen == healthy
    assert tracker._break_reason == "queue_backlog"

    # It stays broken as the backlog keeps growing further behind.
    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(3),
        queue_progress=(90, 1, 0),
        oldest_pending_ts=stale_pending,
    )
    assert redis.hashes[keys.tape_coverage("binance")]["covered_until"] == healthy


async def test_an_item_stuck_past_the_safety_margin_freezes_even_with_a_backlog_of_one() -> None:
    """A single pending item is enough to break the interval once its own
    timestamp reaches the window a stamp is about to claim -- and enough,
    while it has not, to leave the interval advancing (the two halves of the
    rule tested independently)."""
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))

    # now=_at(2): candidate cut is _at(1.5). A pending item timestamped
    # _at(1.6) has not reached it -- the claim proceeds despite backlog=1.
    fresh_pending = _at(1.6)
    stamped = await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(2),
        queue_progress=(5, 4, 0),
        oldest_pending_ts=fresh_pending,
    )
    assert stamped is True
    assert (
        redis.hashes[keys.tape_coverage("binance")]["covered_until"]
        == (_at(2) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    )
    assert tracker._break_reason is None

    # now=_at(3): candidate cut is _at(2.5). The *same* pending item
    # (_at(1.6)) has now reached it -- the claim freezes.
    healthy = redis.hashes[keys.tape_coverage("binance")]["covered_until"]
    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(3),
        queue_progress=(5, 4, 0),
        oldest_pending_ts=fresh_pending,
    )
    frozen = redis.hashes[keys.tape_coverage("binance")]["covered_until"]
    assert frozen == healthy
    assert tracker._break_reason == "queue_backlog"


async def test_a_pending_item_exactly_at_the_candidate_cut_still_breaks() -> None:
    """The comparison is ``<=``, not ``<``: a pending item timestamped
    exactly at the candidate cut is inside the window a stamp would claim
    (the cut is the window's inclusive end, ``windows.trades_between``), so
    it must break rather than just barely pass."""
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))

    # now=_at(2): candidate cut is exactly _at(1.5).
    exactly_at_cut = _at(1.5)
    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(2),
        queue_progress=(5, 4, 0),
        oldest_pending_ts=exactly_at_cut,
    )

    assert tracker._break_reason == "queue_backlog"


async def test_resuming_from_a_queue_backlog_logs_how_long_it_was_frozen(
    monkeypatch: Any,
) -> None:
    """Astra diff review nice-to-have: a resumption log with the frozen
    duration, not just silence until someone notices (the break itself only
    logs once, on entry -- ``test_tape_coverage.py``'s existing tests already
    pin that)."""
    from hunter_market_worker import coverage as coverage_module

    calls: list[dict[str, Any]] = []

    class _RecordingLogger:
        def warning(self, event: str, **kwargs: Any) -> None:
            calls.append({"level": "warning", "event": event, **kwargs})

        def info(self, event: str, **kwargs: Any) -> None:
            calls.append({"level": "info", "event": event, **kwargs})

    monkeypatch.setattr(coverage_module, "logger", _RecordingLogger())
    # `frozen_for_s` is monotonic by design (Astra review: a wall-clock
    # adjustment must not report a negative duration) -- controlled here the
    # same way `_at()` controls the wall clock used for the coverage claim
    # itself, so the two clocks can be asserted independently.
    monotonic_values = iter([100.0, 103.0])
    monkeypatch.setattr(coverage_module, "monotonic", lambda: next(monotonic_values))

    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(
        redis, dropped_events=0, now=_at(1), queue_progress=(1, 1, 0), oldest_pending_ts=None
    )
    stale_pending = _at(1) - timedelta(seconds=1)
    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(2),
        queue_progress=(5, 1, 0),
        oldest_pending_ts=stale_pending,
    )
    assert tracker._break_reason == "queue_backlog"

    await tracker.stamp(
        redis, dropped_events=0, now=_at(5), queue_progress=(5, 5, 0), oldest_pending_ts=None
    )

    assert tracker._break_reason is None
    resumed = [call for call in calls if call["event"] == "tape_coverage_interval_resumed"]
    assert len(resumed) == 1
    assert resumed[0]["frozen_for_s"] == 3.0  # monotonic 100.0 -> 103.0


# ---- Item 3: reconnection semantics are untouched ----------------------------
# (`tests/test_tape_coverage.py`'s existing reconnect/generation tests already
# run unmodified and green against this same module -- see the T2.5e report.)
