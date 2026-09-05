"""BoundedEventQueue: overflow eviction policy, never a dropped final kline,
backpressure instead of unbounded growth.

``docs/plans/M1.md`` T1.2b: several WS reader tasks feed one queue; a slow
consumer must not let it grow without limit, but the eviction target is
never a final kline, and the drop is counted on the connection it came
from — this is unit-testable in complete isolation from any socket.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle, NormalizedTrade, close_time_for
from hunter_exchanges.base import ConnectionState
from hunter_exchanges.binance.event_queue import BoundedEventQueue

pytestmark = pytest.mark.unit


def _trade(price: str = "1") -> NormalizedTrade:
    return NormalizedTrade(
        exchange="binance",
        symbol="BTCUSDT",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        trade_id="1",
        price=Decimal(price),
        qty=Decimal("1"),
        side=OrderSide.BUY,
    )


def _candle(
    is_final: bool, open_time: datetime = datetime(2026, 1, 1, tzinfo=UTC)
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
