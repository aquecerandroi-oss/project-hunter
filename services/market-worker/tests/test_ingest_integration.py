"""Event dispatch and tick flushing against a real Redis — hot state writes,
queueing for persist, and the exact ``EventEnvelope`` shape of every
published stream event."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.market import NormalizedCandle, NormalizedLiquidation
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import Streams
from hunter_core.redis import keys
from hunter_market_worker import wire as msgpack
from hunter_market_worker.ingest import (
    AcceptedEvents,
    TickCoalescer,
    flush_ticks,
    handle_event,
)
from hunter_market_worker.persist import PersistQueues
from hunter_market_worker.universe import MonitoredUniverse

from . import builders
from .fakes import FakeAdapter

pytestmark = pytest.mark.integration

PRODUCER = "market-worker@test:1"


async def _last_stream_payload(redis_client: Any, stream: str) -> EventEnvelope:
    entries = await redis_client.xrange(stream, "-", "+")
    assert entries, f"nothing published on {stream}"
    _id, fields = entries[-1]
    return EventEnvelope.from_bytes(fields[b"data"])


async def test_handle_event_ticker_writes_hot_state(redis_client: Any) -> None:
    queues = PersistQueues()
    coalescer = TickCoalescer()
    await handle_event(
        builders.ticker("BTCUSDT", "50000"),
        redis_client,
        PRODUCER,
        queues,
        coalescer,
        AcceptedEvents(),
    )
    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "BTCUSDT"))
    assert raw[b"last"] == b"50000"
    assert coalescer.dirty_items()  # also fed the coalescer


async def test_handle_event_final_candle_queues_and_publishes(redis_client: Any) -> None:
    queues = PersistQueues()
    candle = builders.candle("BTCUSDT", is_final=True)
    await handle_event(candle, redis_client, PRODUCER, queues, TickCoalescer(), AcceptedEvents())

    queued = queues.events.get_nowait()
    assert isinstance(queued, NormalizedCandle)
    assert queued is candle

    envelope = await _last_stream_payload(redis_client, Streams.MARKET_CANDLES_CLOSED)
    assert envelope.type == Streams.MARKET_CANDLES_CLOSED
    assert envelope.producer == PRODUCER
    assert envelope.key == f"{builders.EXCHANGE}:BTCUSDT"
    assert envelope.payload["is_final"] is True


async def test_handle_event_non_final_candle_is_not_queued(redis_client: Any) -> None:
    queues = PersistQueues()
    await handle_event(
        builders.candle("BTCUSDT", is_final=False),
        redis_client,
        PRODUCER,
        queues,
        TickCoalescer(),
        AcceptedEvents(),
    )
    assert queues.events.empty()


async def test_handle_event_forwards_event_ts_for_growing_partial_candle(
    redis_client: Any,
) -> None:
    """C1: handle_event must forward ``event.event_ts`` to ``push_candle`` so a
    growing partial of the same ``open_time`` is accepted, and a late partial
    (older ``event_ts``) is rejected — through the real dispatch path, not by
    calling ``push_candle`` directly."""
    queues = PersistQueues()
    coalescer = TickCoalescer()
    accepted = AcceptedEvents()
    first = builders.candle("BTCUSDT", is_final=False)
    t0 = first.open_time + timedelta(seconds=1)
    first = first.model_copy(update={"event_ts": t0})

    assert await handle_event(first, redis_client, PRODUCER, queues, coalescer, accepted)

    grown = first.model_copy(
        update={"volume": Decimal("20"), "event_ts": t0 + timedelta(seconds=5)}
    )
    assert await handle_event(grown, redis_client, PRODUCER, queues, coalescer, accepted)

    key = keys.candles_1m(builders.EXCHANGE, "BTCUSDT")
    rows = await redis_client.lrange(key, 0, -1)
    assert len(rows) == 1
    stored = msgpack.unpackb(rows[0])
    assert stored["volume"] == "20"

    late = first.model_copy(update={"event_ts": t0})  # older than grown's event_ts
    assert not await handle_event(late, redis_client, PRODUCER, queues, coalescer, accepted)
    rows = await redis_client.lrange(key, 0, -1)
    assert msgpack.unpackb(rows[0])["volume"] == "20"  # unchanged by the late partial


async def test_handle_event_liquidation_waits_for_commit(redis_client: Any) -> None:
    queues = PersistQueues()
    liq = builders.liquidation("BTCUSDT")
    await handle_event(liq, redis_client, PRODUCER, queues, TickCoalescer(), AcceptedEvents())

    queued = queues.events.get_nowait()
    assert isinstance(queued, NormalizedLiquidation)
    assert await redis_client.xlen(Streams.MARKET_LIQUIDATIONS) == 0


async def test_estimated_funding_rollover_never_becomes_realized(
    redis_client: Any,
) -> None:
    import datetime as dt

    queues = PersistQueues()
    coalescer = TickCoalescer()
    memory = AcceptedEvents()
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    t1 = dt.datetime(2026, 1, 1, 8, tzinfo=dt.UTC)

    await handle_event(
        builders.funding("BTCUSDT", "0.0001", next_funding_time=t0),
        redis_client,
        PRODUCER,
        queues,
        coalescer,
        memory,
    )
    assert queues.events.empty()  # first reading: nothing realized yet

    await handle_event(
        builders.funding("BTCUSDT", "0.0002", next_funding_time=t1),
        redis_client,
        PRODUCER,
        queues,
        coalescer,
        memory,
    )
    assert queues.events.empty()

    deriv = await redis_client.hgetall(keys.derivatives(builders.EXCHANGE, "BTCUSDT"))
    assert deriv[b"funding_rate"] == b"0.0002"

    envelope = await _last_stream_payload(redis_client, Streams.MARKET_DERIVATIVES)
    assert envelope.payload["funding_rate"] == "0.0002"


async def test_flush_ticks_publishes_once_for_ten_trades(redis_client: Any) -> None:
    coalescer = TickCoalescer()
    for i in range(10):
        coalescer.on_trade(builders.trade("BTCUSDT", "100", "1", trade_id=str(i)))

    published = await flush_ticks(coalescer, redis_client, PRODUCER)

    assert published == ["BTCUSDT"]
    length = await redis_client.xlen(Streams.MARKET_TICKS)
    assert length == 1
    envelope = await _last_stream_payload(redis_client, Streams.MARKET_TICKS)
    assert envelope.payload["trades_count"] == 10
    assert envelope.payload["volume_delta"] == "10"
    assert coalescer.dirty_items() == []  # flush reset it


async def test_watchdog_and_health_do_not_advance_on_duplicate_events(
    redis_client: Any,
) -> None:
    """H2: a duplicate/late event must not refresh freshness or watchdog
    progress — only an *accepted* event may."""
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once
    from hunter_market_worker.supervision import IngestionHealth, Watchdog

    async def warning(_message: str) -> None:
        return None

    health = IngestionHealth()
    watchdog = Watchdog(FakeAdapter(), warning)
    adapter = FakeAdapter()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    universe.changed.clear()
    state = HeartbeatState()

    task = asyncio.create_task(
        consume_once(
            adapter,
            list(universe.symbols),
            redis_client,
            PRODUCER,
            PersistQueues(),
            TickCoalescer(),
            AcceptedEvents(),
            universe,
            state,
            health,
            watchdog,
        )
    )
    try:
        async with asyncio.timeout(5):
            await adapter.stream_started.wait()
            ticker = builders.ticker("BTCUSDT", "100")
            await adapter.push_event(ticker)
            while health.last_data is None:  # noqa: ASYNC110 — polling a plain float, not an Event
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)
            last_data_after_first = health.last_data
            last_event_after_first = watchdog.last_event
            assert last_event_after_first is not None

            duplicate = ticker.model_copy()
            await adapter.push_event(duplicate)
            await adapter.push_event(duplicate)
            await asyncio.sleep(0.2)

        assert health.last_data == last_data_after_first
        assert watchdog.last_event == last_event_after_first
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_incremental_subscriptions_keep_existing_symbols(redis_client: Any) -> None:
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once

    adapter = FakeAdapter()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT", "ETHUSDT"])
    universe.changed.clear()
    state = HeartbeatState()
    task = asyncio.create_task(
        consume_once(
            adapter,
            list(universe.symbols),
            redis_client,
            PRODUCER,
            PersistQueues(),
            TickCoalescer(),
            AcceptedEvents(),
            universe,
            state,
        )
    )
    try:
        async with asyncio.timeout(5):
            await adapter.stream_started.wait()
            universe.set(["ETHUSDT", "SOLUSDT"])
            await adapter.subscriptions_updated.wait()
        assert adapter.subscription_changes == [(["SOLUSDT"], ["BTCUSDT"])]
        assert len(adapter.stream_calls) == 1
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
