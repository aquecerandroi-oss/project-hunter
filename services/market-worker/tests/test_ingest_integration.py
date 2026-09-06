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
from hunter_market_worker.hot_state import TradeMemory
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
    """B3: the hot-state write is deferred to the coalescer's per-cycle
    flush, not done inside ``handle_event`` itself."""
    queues = PersistQueues()
    coalescer = TickCoalescer()
    await handle_event(
        builders.ticker("BTCUSDT", "50000"),
        redis_client,
        PRODUCER,
        queues,
        coalescer,
        AcceptedEvents(),
        TradeMemory(),
    )
    assert coalescer.dirty_items()  # fed the coalescer
    assert not await redis_client.exists(keys.ticker(builders.EXCHANGE, "BTCUSDT"))

    await flush_ticks(coalescer, redis_client, PRODUCER)
    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "BTCUSDT"))
    assert raw[b"last"] == b"50000"


async def test_handle_event_final_candle_queues_without_publishing(redis_client: Any) -> None:
    """T2.9: a closed candle is durable, so ingest only queues it. The
    ``market.candles.closed`` event is written to ``outbox_events`` inside the
    transaction that persists the candle and published from there — see
    ``test_outbox_producers.py``. Publishing here used to announce candles a
    failed flush never stored."""
    queues = PersistQueues()
    candle = builders.candle("BTCUSDT", is_final=True)
    await handle_event(
        candle, redis_client, PRODUCER, queues, TickCoalescer(), AcceptedEvents(), TradeMemory()
    )

    queued = queues.events.get_nowait()
    assert isinstance(queued, NormalizedCandle)
    assert queued is candle
    assert await redis_client.xrange(Streams.MARKET_CANDLES_CLOSED) == []


async def test_handle_event_non_final_candle_is_not_queued(redis_client: Any) -> None:
    queues = PersistQueues()
    await handle_event(
        builders.candle("BTCUSDT", is_final=False),
        redis_client,
        PRODUCER,
        queues,
        TickCoalescer(),
        AcceptedEvents(),
        TradeMemory(),
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
    trade_memory = TradeMemory()
    first = builders.candle("BTCUSDT", is_final=False)
    t0 = first.open_time + timedelta(seconds=1)
    first = first.model_copy(update={"event_ts": t0})

    assert await handle_event(
        first, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )

    grown = first.model_copy(
        update={"volume": Decimal("20"), "event_ts": t0 + timedelta(seconds=5)}
    )
    assert await handle_event(
        grown, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )

    key = keys.candles_1m(builders.EXCHANGE, "BTCUSDT")
    rows = await redis_client.lrange(key, 0, -1)
    assert len(rows) == 1
    stored = msgpack.unpackb(rows[0])
    assert stored["volume"] == "20"

    late = first.model_copy(update={"event_ts": t0})  # older than grown's event_ts
    assert not await handle_event(
        late, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )
    rows = await redis_client.lrange(key, 0, -1)
    assert msgpack.unpackb(rows[0])["volume"] == "20"  # unchanged by the late partial


async def test_handle_event_liquidation_waits_for_commit(redis_client: Any) -> None:
    queues = PersistQueues()
    liq = builders.liquidation("BTCUSDT")
    await handle_event(
        liq, redis_client, PRODUCER, queues, TickCoalescer(), AcceptedEvents(), TradeMemory()
    )

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
    trade_memory = TradeMemory()
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    t1 = dt.datetime(2026, 1, 1, 8, tzinfo=dt.UTC)

    await handle_event(
        builders.funding("BTCUSDT", "0.0001", next_funding_time=t0),
        redis_client,
        PRODUCER,
        queues,
        coalescer,
        memory,
        trade_memory,
    )
    assert queues.events.empty()  # first reading: nothing realized yet

    await handle_event(
        builders.funding("BTCUSDT", "0.0002", next_funding_time=t1),
        redis_client,
        PRODUCER,
        queues,
        coalescer,
        memory,
        trade_memory,
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
            TradeMemory(),
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
            TradeMemory(),
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


async def test_consume_once_returns_on_watchdog_restart_with_no_events_ever_arriving(
    redis_client: Any,
) -> None:
    """B1 regression: an ``async for`` rewrite of the consumer loop must not
    block forever waiting for the next event once the watchdog asks for a
    restart -- the housekeeping task must still be able to end the cycle on
    a completely silent stream."""
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once
    from hunter_market_worker.supervision import Watchdog

    async def warning(_message: str) -> None:
        return None

    adapter = FakeAdapter()
    watchdog = Watchdog(adapter, warning)
    watchdog.restart_stream = True
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    universe.changed.clear()
    state = HeartbeatState()

    async with asyncio.timeout(5):
        await consume_once(
            adapter,
            list(universe.symbols),
            redis_client,
            PRODUCER,
            PersistQueues(),
            TickCoalescer(),
            AcceptedEvents(),
            TradeMemory(),
            universe,
            state,
            None,
            watchdog,
        )

    assert watchdog.restart_stream is False  # cleared
    assert adapter.closed is True  # finally still closed the stream


async def test_consume_once_raises_when_adapter_lacks_update_subscriptions(
    redis_client: Any,
) -> None:
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once

    class NoUpdateAdapter:
        code = "fake"

        async def stream(self, symbols: Any, channels: Any) -> Any:
            await asyncio.Event().wait()
            yield  # pragma: no cover - unreachable, keeps this an async generator

        async def aclose(self) -> None:
            return None

    adapter = NoUpdateAdapter()
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
            TradeMemory(),
            universe,
            state,
        )
    )
    await asyncio.sleep(0)
    universe.set(["ETHUSDT"])  # a diff the next 100ms housekeeping tick must see

    with pytest.raises(RuntimeError, match="update_subscriptions"):
        async with asyncio.timeout(5):
            await task


async def test_consume_once_raises_runtime_error_when_stream_exhausts(
    redis_client: Any,
) -> None:
    """The old code caught ``StopAsyncIteration`` from a manual
    ``__anext__()`` and turned it into ``RuntimeError``; an ``async for``
    swallows ``StopAsyncIteration`` as normal loop exit, so this must be
    detected explicitly."""
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once

    class ExhaustingAdapter:
        code = "fake"

        async def stream(self, symbols: Any, channels: Any) -> Any:
            return
            yield  # pragma: no cover - unreachable, keeps this an async generator

        async def aclose(self) -> None:
            return None

    adapter = ExhaustingAdapter()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    universe.changed.clear()
    state = HeartbeatState()

    with pytest.raises(RuntimeError, match="task stream exited unexpectedly"):
        async with asyncio.timeout(5):
            await consume_once(
                adapter,
                list(universe.symbols),
                redis_client,
                PRODUCER,
                PersistQueues(),
                TickCoalescer(),
                AcceptedEvents(),
                TradeMemory(),
                universe,
                state,
            )


async def test_internal_reconnect_holds_covered_until_back_without_ending_the_generator(
    redis_client: Any,
) -> None:
    """T2.5-adapter (Astra diff review finding 1): a socket the adapter
    repairs *inside* its own reconnect loop, without ever ending
    :meth:`~hunter_market_worker.streaming.consume_once`'s ``stream()``
    generator, must still break the published coverage interval.
    ``consume_once`` never sees an exception or a fresh ``stream()`` call in
    this scenario (that is exactly the gap Astra's review found), so the fix
    reads the adapter's own ``connection_state()`` every housekeeping tick
    instead of waiting for the generator to end or for an event to arrive."""
    from hunter_market_worker.coverage import CoverageTracker
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once

    adapter = FakeAdapter()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    universe.changed.clear()
    state = HeartbeatState()
    coverage = CoverageTracker(adapter.code)
    coverage_key = keys.tape_coverage(adapter.code)

    task = asyncio.create_task(
        consume_once(
            adapter,
            list(universe.symbols),
            redis_client,
            PRODUCER,
            PersistQueues(),
            TickCoalescer(),
            AcceptedEvents(),
            TradeMemory(),
            universe,
            state,
            None,
            None,
            coverage,
        )
    )
    try:
        await adapter.stream_started.wait()
        # > COVERAGE_SAFETY_S (0.5s) must elapse before ``covered_until`` can
        # clear ``session_since`` at all — see ``coverage.py``'s margin.
        await asyncio.sleep(0.9)
        healthy = await redis_client.hgetall(coverage_key)
        assert healthy[b"covered_until"] != healthy[b"session_since"]  # genuinely advancing

        adapter.set_connection_state("reconnecting")  # internal reconnect: generator never ends
        await asyncio.sleep(0.4)
        frozen = await redis_client.hgetall(coverage_key)
        assert frozen[b"covered_until"] == healthy[b"covered_until"]  # held, never advanced

        adapter.set_connection_state("connected")
        await asyncio.sleep(0.4)
        resumed = await redis_client.hgetall(coverage_key)
        assert resumed[b"covered_until"] > frozen[b"covered_until"]  # resumes once healthy again
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_backlogged_adapter_queue_holds_covered_until_back(redis_client: Any) -> None:
    """T2.5-adapter (Astra diff review finding 1, second gap): an item the
    adapter's reader task has already popped off its own internal queue but
    has not yet yielded is invisible to ``_in_flight`` — the tracker must
    also refuse to advance past what the adapter reports as delivered."""
    from hunter_market_worker.coverage import CoverageTracker
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import consume_once

    adapter = FakeAdapter()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    universe.changed.clear()
    state = HeartbeatState()
    coverage = CoverageTracker(adapter.code)
    coverage_key = keys.tape_coverage(adapter.code)

    task = asyncio.create_task(
        consume_once(
            adapter,
            list(universe.symbols),
            redis_client,
            PRODUCER,
            PersistQueues(),
            TickCoalescer(),
            AcceptedEvents(),
            TradeMemory(),
            universe,
            state,
            None,
            None,
            coverage,
        )
    )
    try:
        await adapter.stream_started.wait()
        await asyncio.sleep(0.9)
        healthy = await redis_client.hgetall(coverage_key)
        assert healthy[b"covered_until"] != healthy[b"session_since"]

        adapter.set_queue_progress(enqueued=5, delivered=3)  # 2 items still in transit
        await asyncio.sleep(0.4)
        frozen = await redis_client.hgetall(coverage_key)
        assert frozen[b"covered_until"] == healthy[b"covered_until"]

        adapter.set_queue_progress(enqueued=5, delivered=5)  # caught up again
        await asyncio.sleep(0.4)
        resumed = await redis_client.hgetall(coverage_key)
        assert resumed[b"covered_until"] > frozen[b"covered_until"]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_handle_event_ticker_and_book_never_touch_redis(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B3: ``handle_event`` decides ticker/book acceptance purely from the
    in-memory ``AcceptedEvents`` gate -- both the accepted and the
    out-of-order case must cost zero Redis round trips. The actual write is
    deferred to the coalescer's periodic flush."""
    calls = {"n": 0}
    redis_cls: Any = redis_client.__class__
    original = redis_cls.execute_command

    async def counting(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(redis_cls, "execute_command", counting)

    queues = PersistQueues()
    coalescer = TickCoalescer()
    accepted = AcceptedEvents()
    trade_memory = TradeMemory()

    ticker = builders.ticker("BTCUSDT", "100")
    assert await handle_event(
        ticker, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )
    book = builders.order_book("BTCUSDT")
    assert await handle_event(
        book, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )
    assert calls["n"] == 0

    stale_ticker = ticker.model_copy(update={"ts": ticker.ts - timedelta(seconds=5)})
    assert not await handle_event(
        stale_ticker, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )
    stale_book = book.model_copy(update={"ts": book.ts - timedelta(seconds=5)})
    assert not await handle_event(
        stale_book, redis_client, PRODUCER, queues, coalescer, accepted, trade_memory
    )
    assert calls["n"] == 0


async def test_flush_ticks_writes_ticker_and_book_hot_state_in_the_same_cycle(
    redis_client: Any,
) -> None:
    """B3: the cost of coalescing is up to ``tick_coalesce_ms`` of extra
    staleness, never more -- a symbol dirty in this cycle must have its hot
    state written by *this* flush, not a later one."""
    coalescer = TickCoalescer()
    coalescer.on_ticker(builders.ticker("BTCUSDT", "50000"))
    coalescer.on_book(builders.order_book("BTCUSDT", "49999", "50001"))

    await flush_ticks(coalescer, redis_client, PRODUCER)

    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "BTCUSDT"))
    assert raw[b"last"] == b"50000"
    book_raw = await redis_client.get(keys.book(builders.EXCHANGE, "BTCUSDT"))
    assert book_raw is not None
    decoded = msgpack.unpackb(book_raw)
    assert decoded["bids"][0][0] == "49999"


async def test_coalesce_loop_flushes_buffered_state_on_cancellation(
    redis_client: Any,
) -> None:
    """B3: a shutdown/cancellation must flush what is buffered -- a ticker
    sitting in the coalescer at the moment of SIGTERM must not be silently
    lost just because the next 250ms tick never comes."""
    from hunter_core.settings import Settings
    from hunter_market_worker.ingest import coalesce_loop

    coalescer = TickCoalescer()
    coalescer.on_ticker(builders.ticker("BTCUSDT", "50000"))
    settings = Settings(tick_coalesce_ms=100_000)  # long enough only shutdown can flush it

    task = asyncio.create_task(coalesce_loop(coalescer, redis_client, settings, PRODUCER))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "BTCUSDT"))
    assert raw[b"last"] == b"50000"
