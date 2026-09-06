"""BoundedEventQueue: overflow eviction policy, never a dropped final kline,
backpressure instead of unbounded growth.

``docs/plans/M1.md`` T1.2b: several WS reader tasks feed one queue; a slow
consumer must not let it grow without limit, but the eviction target is
never a final kline, and the drop is counted on the connection it came
from — this is unit-testable in complete isolation from any socket.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle, NormalizedTrade, close_time_for
from hunter_exchanges.base import ConnectionState
from hunter_exchanges.binance.event_queue import BoundedEventQueue, StreamConsumer

pytestmark = pytest.mark.unit


def _trade(price: str = "1", ts: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="binance",
        symbol="BTCUSDT",
        ts=ts,
        trade_id="1",
        price=Decimal(price),
        qty=Decimal("1"),
        side=OrderSide.BUY,
    )


def _candle(
    is_final: bool,
    open_time: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    event_ts: datetime | None = None,
) -> NormalizedCandle:
    return NormalizedCandle(
        exchange="binance",
        symbol="BTCUSDT",
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=close_time_for(open_time, Timeframe.M1),
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        is_final=is_final,
        event_ts=event_ts,
    )


def _states(*keys: str) -> dict[str, ConnectionState]:
    return {key: ConnectionState(route="market", ws_state="connected") for key in keys}


async def test_put_and_get_preserve_order() -> None:
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0")
    first, second = _trade("1"), _trade("2")

    await queue.put("market:0", first, states)
    await queue.put("market:0", second, states)

    assert await queue.get() is first
    assert await queue.get() is second


async def test_overflow_evicts_the_oldest_non_final_candle_event() -> None:
    queue = BoundedEventQueue(maxsize=2)
    states = _states("market:0")
    old_trade = _trade("1")
    await queue.put("market:0", old_trade, states)
    await queue.put("market:0", _trade("2"), states)

    await queue.put("market:0", _trade("3"), states)  # overflow: evicts old_trade

    assert len(queue) == 2
    remaining = [await queue.get(), await queue.get()]
    assert old_trade not in remaining
    assert states["market:0"].dropped_events == 1


async def test_overflow_never_evicts_a_final_kline() -> None:
    queue = BoundedEventQueue(maxsize=1)
    states = _states("market:0")
    final_candle = _candle(is_final=True)
    await queue.put("market:0", final_candle, states)

    await queue.put("market:0", _trade("1"), states)  # queue full of only a final kline

    # the final kline is never evicted; the incoming non-candle is the one dropped
    assert len(queue) == 1
    assert (await queue.get()) is final_candle
    assert states["market:0"].dropped_events == 1


async def test_final_kline_overflow_applies_backpressure_instead_of_growing_unbounded() -> None:
    """Neither the queued final nor the incoming final may ever be dropped —
    but the queue must still never exceed ``maxsize``: :meth:`put` blocks
    until :meth:`get` frees a slot (Astra review, T1.2b resume finding 4)."""
    queue = BoundedEventQueue(maxsize=1)
    states = _states("market:0")
    first_final = _candle(is_final=True)
    await queue.put("market:0", first_final, states)

    second_final = _candle(is_final=True, open_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC))
    put_task = asyncio.ensure_future(queue.put("market:0", second_final, states))
    await asyncio.sleep(0.01)
    assert not put_task.done()  # blocked: no room, and neither final may be dropped
    assert len(queue) == 1  # never exceeds maxsize, even transiently

    drained = await queue.get()
    assert drained is first_final
    await put_task  # unblocks once get() freed a slot

    assert len(queue) == 1
    assert (await queue.get()) is second_final
    assert states["market:0"].dropped_events == 0


async def test_eviction_counts_the_drop_on_the_connection_the_victim_came_from() -> None:
    queue = BoundedEventQueue(maxsize=1)
    states = _states("market:0", "market:1")
    await queue.put("market:0", _trade("1"), states)

    await queue.put("market:1", _trade("2"), states)

    assert states["market:0"].dropped_events == 1
    assert states["market:1"].dropped_events == 0


async def test_get_blocks_until_an_item_is_put() -> None:
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0")

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.02)

    await queue.put("market:0", _trade("1"), states)
    assert await asyncio.wait_for(queue.get(), timeout=0.02) is not None


# ---- T1.6b-A: O(1) eviction (ACHADO-1, .claude/state/t16b-profile.md) --------
#
# The old `_evict_one` scanned the whole deque from index 0 on every `put`
# while full (`isinstance` + attribute access per item, then an O(n) `del` on
# a deque) — 17.8% of one core at 200 markets, self-reinforcing under real
# saturation. These tests pin the *same observable contract* the scan
# implementation had (never evict a final, count on the victim's own
# connection, strict FIFO) while proving the O(1)-common-case shape.


async def test_fifo_order_preserved_across_mixed_final_and_non_final_events() -> None:
    """`get()` must still return strict FIFO order across an interleaving of
    trades and final klines — not just within one of the two categories."""
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0")
    events = [
        _trade("1"),
        _candle(is_final=True),
        _trade("2"),
        _candle(is_final=True, open_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC)),
        _trade("3"),
    ]
    for event in events:
        await queue.put("market:0", event, states)

    drained = [await queue.get() for _ in events]

    assert drained == events


async def test_overflow_with_a_final_kline_at_the_head_falls_back_to_the_next_non_final() -> None:
    """The O(1) common case evicts the head when it is not final; this pins
    the rare fallback (head *is* a queued final, but a later item is not) —
    the final at the head must survive, and the non-final behind it is the
    one dropped, not a linear-scan-avoidance regression that drops nothing
    or picks the wrong victim."""
    queue = BoundedEventQueue(maxsize=3)
    states = _states("market:0")
    final = _candle(is_final=True)
    old_trade = _trade("1")
    await queue.put("market:0", final, states)
    await queue.put("market:0", old_trade, states)
    await queue.put("market:0", _trade("2"), states)

    await queue.put("market:0", _trade("3"), states)  # overflow

    assert len(queue) == 3
    remaining = [await queue.get(), await queue.get(), await queue.get()]
    assert final in remaining
    assert old_trade not in remaining
    assert states["market:0"].dropped_events == 1


# ---- T2.5-adapter: enqueued/delivered/evicted (Astra diff review finding 1) -


async def test_enqueued_counts_every_successful_append_only() -> None:
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0")

    await queue.put("market:0", _trade("1"), states)
    await queue.put("market:0", _trade("2"), states)

    assert queue.enqueued == 2
    assert queue.evicted == 0
    assert queue.progress() == (2, 0)


async def test_an_incoming_dropped_event_is_never_counted_as_enqueued() -> None:
    """Queue full of only final klines, incoming non-final: the *incoming*
    event is the one dropped (never entered the queue), so it must not
    appear on either side of the ``enqueued``/``delivered``+``evicted``
    ledger — its loss is already ``dropped_events``' job."""
    queue = BoundedEventQueue(maxsize=1)
    states = _states("market:0")
    await queue.put("market:0", _candle(is_final=True), states)

    await queue.put("market:0", _trade("1"), states)  # dropped before entry

    assert queue.enqueued == 1
    assert queue.evicted == 0


async def test_eviction_increments_evicted_not_enqueued() -> None:
    queue = BoundedEventQueue(maxsize=2)
    states = _states("market:0")
    await queue.put("market:0", _trade("1"), states)
    await queue.put("market:0", _trade("2"), states)

    await queue.put("market:0", _trade("3"), states)  # overflow: evicts trade 1

    assert queue.enqueued == 3  # every item that ever entered, evicted or not
    assert queue.evicted == 1
    assert queue.progress() == (3, 1)


async def test_stream_consumer_delivered_counts_only_what_was_actually_yielded() -> None:
    consumer = StreamConsumer(maxsize=10)
    states = _states("market:0")
    await consumer.put("market:0", _trade("1"), states)
    await consumer.put("market:0", _trade("2"), states)

    # Nothing has been drained through ``consume()`` yet: two items sit
    # enqueued, none delivered -- exactly the backlog a plain queue-length
    # read after a `get()` would miss, since `enqueued` already reflects
    # both items regardless of whether anything popped them.
    assert consumer.queue.enqueued == 2
    assert consumer.delivered == 0

    async def close() -> None:
        return None

    agen: Any = consumer.consume(close)
    await agen.__anext__()
    assert consumer.delivered == 1
    await agen.__anext__()
    assert consumer.delivered == 2
    await agen.aclose()


async def test_fifty_thousand_puts_into_a_saturated_queue_stay_fast() -> None:
    """Performance regression guard for ACHADO-1: with the queue permanently
    full of ordinary (non-final) events — the real 200-market shape — every
    `put` must evict in O(1), not rescan the whole deque. A generous
    wall-clock budget: the old O(n) scan over a maxsize-1000 deque would take
    far longer than this at 50k puts."""
    queue = BoundedEventQueue(maxsize=1000)
    states = _states("market:0")
    for _ in range(1000):
        await queue.put("market:0", _trade("1"), states)

    start = time.perf_counter()
    for _ in range(50_000):
        await queue.put("market:0", _trade("1"), states)
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0


# ---- T2.5e: oldest_pending_ts (Astra diff review, T2.5e must-fix 1 and 2) ----


async def test_oldest_pending_ts_is_none_when_nothing_is_queued() -> None:
    queue = BoundedEventQueue(maxsize=10)
    assert queue.oldest_pending_ts() is None


async def test_oldest_pending_ts_is_the_minimum_across_the_queue_not_the_head() -> None:
    """Several reader tasks (one per connection) feed one shared queue by
    arrival order, not by the event's own timestamp -- a later-arriving item
    can carry an earlier ``ts`` (Astra diff review, must-fix 2). The head of
    the deque alone would have reported the *later* timestamp here."""
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0", "market:1")
    earlier_arrival_later_ts = _trade("1", ts=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    later_arrival_earlier_ts = _trade("2", ts=datetime(2026, 1, 1, 11, 59, tzinfo=UTC))
    await queue.put("market:1", earlier_arrival_later_ts, states)
    await queue.put("market:0", later_arrival_earlier_ts, states)

    assert queue.oldest_pending_ts() == later_arrival_earlier_ts.ts


async def test_oldest_pending_ts_falls_back_to_a_candles_close_time() -> None:
    """``NormalizedCandle`` has no ``ts`` field; without a wire ``event_ts``
    the close time is the conservative (never-too-early) stand-in."""
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0")
    candle = _candle(is_final=True)
    await queue.put("market:0", candle, states)

    assert queue.oldest_pending_ts() == candle.close_time


async def test_oldest_pending_ts_prefers_a_candles_own_event_ts_over_close_time() -> None:
    queue = BoundedEventQueue(maxsize=10)
    states = _states("market:0")
    event_ts = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
    candle = _candle(is_final=True, event_ts=event_ts)
    await queue.put("market:0", candle, states)

    assert queue.oldest_pending_ts() == event_ts


async def test_stream_consumer_oldest_pending_ts_is_none_before_anything_is_put() -> None:
    consumer = StreamConsumer(maxsize=10)
    assert consumer.oldest_pending_ts() is None


async def test_stream_consumer_oldest_pending_ts_counts_an_item_already_popped_but_not_yet_delivered() -> (
    None
):
    """Astra diff review, T2.5e must-fix 1: the item ``BoundedEventQueue.get``
    has already popped from its own deque is exactly as pending as anything
    still queued behind it. An external reader (``CoverageTracker``, via a
    different task) must not see it as "gone" just because :meth:`consume`
    has not resumed past its own ``await asyncio.wait(...)`` yet -- plain
    queue length, or a naive "check the deque" implementation, would have
    read ``None`` here despite nothing having been delivered."""
    consumer = StreamConsumer(maxsize=10)
    states = _states("market:0")
    trade = _trade("1", ts=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    await consumer.put("market:0", trade, states)

    # Reach into exactly the state ``consume()`` would be in mid-race: the
    # queue's own ``get()`` coroutine has already run to completion (the
    # item left the deque) inside a Task nobody has consumed the result of
    # yet.
    consumer._pending_get = asyncio.ensure_future(consumer.queue.get())
    await asyncio.sleep(0)  # let it run once; the item is already there, so it never blocks
    assert consumer._pending_get.done()
    assert len(consumer.queue) == 0  # gone from the deque...
    assert consumer.delivered == 0  # ...but not yet counted as delivered

    assert consumer.oldest_pending_ts() == trade.ts

    async def close() -> None:
        return None

    agen: Any = consumer.consume(close)
    await agen.__anext__()  # resumes past the same task, delivers it
    assert consumer.delivered == 1
    assert consumer.oldest_pending_ts() is None
    await agen.aclose()


async def test_stream_consumer_oldest_pending_ts_is_the_in_flight_item_not_a_fresher_one_behind_it() -> (
    None
):
    """Astra diff review nice-to-have: the in-flight ``get()`` result and the
    rest of the deque are combined by minimum, not by "whichever is checked
    first" -- an old item already popped must still win over a fresher one
    that arrived right behind it."""
    consumer = StreamConsumer(maxsize=10)
    states = _states("market:0")
    old_trade = _trade("1", ts=datetime(2026, 1, 1, 11, 0, tzinfo=UTC))
    await consumer.put("market:0", old_trade, states)

    consumer._pending_get = asyncio.ensure_future(consumer.queue.get())
    await asyncio.sleep(0)
    assert consumer._pending_get.done()
    assert len(consumer.queue) == 0

    fresher_trade = _trade("2", ts=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    await consumer.put("market:0", fresher_trade, states)
    assert len(consumer.queue) == 1

    assert consumer.oldest_pending_ts() == old_trade.ts
