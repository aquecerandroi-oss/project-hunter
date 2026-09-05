"""T1.7 item 1: fake adapter -> worker -> Redis -> Postgres -> API -> WS.

Every step below calls the exact function ``hunter_market_worker.main.run_market``
composes (``refresh_universe``, ``handle_event``, ``flush_ticks``,
``persist_rows.flush_batch``, ``sampling.write_snapshots``, ``run_heartbeat``)
against a real Postgres + Redis (testcontainers) and a scripted
``FakeExchangeAdapter`` -- no network, no real exchange, per docs/plans/M1.md
T1.7's own line and ``.claude/state/review-T1.7.md`` (b). ``run_market`` itself
is not driven as one ``TaskGroup`` here: its constituent tasks are boundary-
aligned (``snapshot_loop``/``oi_poll_loop`` sleep until the next UTC minute/5-
minute grid mark before doing anything), so exercising them through their own
sleep loops would make this suite either flaky or minutes long. Calling the
same functions directly is the "clock injetável, não sleep longo" the review
kit asks for (c) while still running every line of the real worker + API code.

Reads through the real FastAPI app (``pipeline_client``, JWT signed and
verified, no Clerk credential -- ``tests/integration/conftest.py``), so the
five endpoints in the brief are exercised as actual HTTP contracts, not
service-layer calls.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import orjson
import pytest

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.events.streams import Streams
from hunter_core.redis import keys
from hunter_exchanges.testing.fake_adapter import FakeExchangeAdapter
from hunter_market_worker import hot_state
from hunter_market_worker.heartbeat import HeartbeatState, run_heartbeat
from hunter_market_worker.ingest import (
    AcceptedEvents,
    TickCoalescer,
    flush_ticks,
    handle_event,
)
from hunter_market_worker.persist import PersistQueues
from hunter_market_worker.persist_rows import flush_batch
from hunter_market_worker.universe import MonitoredUniverse, refresh_universe

from . import pipeline_builders as b

pytestmark = pytest.mark.integration

EXCHANGE = b.EXCHANGE
SYMBOL = "BTCUSDT"
PRODUCER = "market-worker@pipeline-it:1"


async def _drain(queues: PersistQueues) -> list[Any]:
    items: list[Any] = []
    while not queues.events.empty():
        items.append(queues.events.get_nowait())
    return items


@pytest.fixture
def scripted_adapter() -> FakeExchangeAdapter:
    return FakeExchangeAdapter(
        code=EXCHANGE,
        markets=[b.market(SYMBOL, "BTC")],
        ticker=b.ticker(SYMBOL, "50000"),
        connection_states=("connected",),
    )


async def test_full_pipeline_fake_adapter_to_redis_to_postgres_to_api(
    scripted_adapter: FakeExchangeAdapter,
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,  # redis-py's own stubs leave PubSub untyped (test_heartbeat.py's own convention)
    worker_settings: Settings,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    adapter = scripted_adapter
    universe = MonitoredUniverse()

    # ---- 1. universe: real perpetual -> real markets/assets rows ----------
    monitored = await refresh_universe(
        worker_session_factory, adapter, worker_redis, worker_settings, producer=PRODUCER
    )
    universe.set(monitored)
    assert monitored == [SYMBOL]
    universe_envelope = await _last_stream_entry(worker_redis, Streams.MARKET_UNIVERSE_CHANGED)
    assert universe_envelope["payload"]["added"] == [SYMBOL]

    # ---- 2. scripted stream: ticker, trade, book, kline partial->final,
    #         markPrice (funding), forceOrder (liquidation) ----------------
    queues = PersistQueues()
    coalescer = TickCoalescer()
    accepted = AcceptedEvents()
    trade_memory = hot_state.TradeMemory()

    open_time = align_open_time(utcnow(), Timeframe.M1)
    t0 = open_time + timedelta(seconds=1)
    t1 = open_time + timedelta(seconds=5)

    ticker_event = b.ticker(SYMBOL, "50000.50")
    trade_event = b.trade(SYMBOL, "50000.60", "0.01", trade_id="t1")
    book_event = b.order_book(SYMBOL, "50000.4", "50000.7")
    partial = b.candle(
        SYMBOL,
        open_time,
        is_final=False,
        open=Decimal("49990"),
        high=Decimal("50000"),
        low=Decimal("49990"),
        close=Decimal("50000"),
        volume=Decimal("1"),
        event_ts=t0,
    )
    grown_partial = partial.model_copy(
        update={
            "high": Decimal("50010"),
            "close": Decimal("50010"),
            "volume": Decimal("2"),
            "event_ts": t1,
        }
    )
    final = b.candle(
        SYMBOL,
        open_time,
        is_final=True,
        open=Decimal("49990"),
        high=Decimal("50020"),
        low=Decimal("49990"),
        close=Decimal("50020"),
        volume=Decimal("5"),
    )
    funding_event = b.funding(SYMBOL, "0.0001", mark_price=Decimal("50000.5"))
    liq_event = b.liquidation(SYMBOL, price="49990", qty="0.5")

    pubsub: Any = worker_redis.pubsub()  # redis-py's stubs leave PubSub's own methods untyped
    await pubsub.subscribe(f"rt:market:{EXCHANGE}:{SYMBOL}")

    args = (worker_redis, PRODUCER, queues, coalescer, accepted, trade_memory)
    assert await handle_event(ticker_event, *args)
    assert await handle_event(trade_event, *args)
    assert await handle_event(book_event, *args)
    assert await handle_event(partial, *args)
    assert await handle_event(grown_partial, *args)
    assert await handle_event(final, *args)
    # H10/invariant: a late/duplicate partial after the final must never
    # replace it (docs/plans/M1.md T1.3, "parcial nunca substitui final").
    late_partial = partial.model_copy(update={"close": Decimal("1"), "event_ts": open_time})
    assert not await handle_event(late_partial, *args)
    assert await handle_event(funding_event, *args)
    assert await handle_event(liq_event, *args)

    # ---- candle + derivatives hot state (written immediately, unlike
    # ticker/book below, which the coalescer defers to its own flush -- B3) --
    import hunter_market_worker.wire as msgpack

    candles_raw = await worker_redis.lrange(keys.candles_1m(EXCHANGE, SYMBOL), 0, -1)
    assert len(candles_raw) == 1  # one open_time, final wins, late partial rejected
    stored_candle = msgpack.unpackb(cast(bytes, candles_raw[0]))
    assert stored_candle["is_final"] is True
    assert stored_candle["close"] == "50020"  # not "1" from the rejected late partial

    deriv_raw = await worker_redis.hgetall(keys.derivatives(EXCHANGE, SYMBOL))
    assert deriv_raw[b"mark_price"] == b"50000.5"
    assert deriv_raw[b"funding_kind"] == b"estimated"

    trades_raw = await worker_redis.lrange(keys.trades(EXCHANGE, SYMBOL), 0, -1)
    assert len(trades_raw) == 1
    assert msgpack.unpackb(cast(bytes, trades_raw[0]))["trade_id"] == "t1"

    # ---- coalesced tick: one market.ticks event + rt:market:* publish, and
    # (B3) this is also when the ticker/book hot state actually lands ------
    published = await flush_ticks(coalescer, worker_redis, PRODUCER)
    assert published == [SYMBOL]
    tick_envelope = await _last_stream_entry(worker_redis, Streams.MARKET_TICKS)
    assert tick_envelope["payload"]["price"] == "50000.60"  # last trade price wins
    assert tick_envelope["payload"]["trades_count"] == 1

    message = await _next_pubsub_message(pubsub)
    tick_payload = orjson.loads(message["data"])
    assert tick_payload["symbol"] == SYMBOL
    await pubsub.unsubscribe()
    await pubsub.aclose()

    raw_ticker = await worker_redis.hgetall(keys.ticker(EXCHANGE, SYMBOL))
    assert raw_ticker[b"last"] == b"50000.50"
    assert raw_ticker[b"bid"] == str(ticker_event.bid).encode()
    assert b"ts" in raw_ticker

    raw_book = await worker_redis.get(keys.book(EXCHANGE, SYMBOL))
    book_payload = msgpack.unpackb(cast(bytes, raw_book))
    assert book_payload["depth"] == 20
    assert book_payload["kind"] == "snapshot"
    assert book_payload["bids"][0] == [str(book_event.bids[0].price), str(book_event.bids[0].qty)]

    # ---- 3. persistence: candles final-only, liquidations deduped ---------
    batch = await _drain(queues)
    from hunter_core.domain.market import NormalizedCandle

    assert sum(isinstance(i, NormalizedCandle) for i in batch) == 1  # partial never queued
    inserted_liq_ids = await flush_batch(worker_session_factory, EXCHANGE, batch)
    assert len(inserted_liq_ids) == 1
    from hunter_market_worker.publication import liquidation_id

    assert liquidation_id(liq_event) in inserted_liq_ids  # event_id == deterministic uuid5

    # replaying the exact same batch must not duplicate anything (idempotent
    # persistence: candle ON CONFLICT (market_id, timeframe, open_time) DO
    # NOTHING; liquidation ON CONFLICT (id, ts) DO NOTHING).
    replay_ids = await flush_batch(worker_session_factory, EXCHANGE, batch)
    assert replay_ids == set()  # nothing "newly" inserted the second time

    # (F6-style isolation: this suite shares one Postgres database across many
    # test files/functions -- see ``tests/integration/README.md`` note in the
    # module docstring -- so every whole-table assertion below is scoped to
    # THIS market's id, never a bare `select(Candle)` that would also pick up
    # rows another test in the same session left behind.)
    from hunter_market_worker.persist_rows import load_market_ids

    async with worker_session_factory() as session:
        from sqlalchemy import select

        from hunter_core.db.models.market_data import Candle, Liquidation

        market_id = (await load_market_ids(session, EXCHANGE, {SYMBOL}))[SYMBOL]
        candle_rows = (
            (await session.execute(select(Candle).where(Candle.market_id == market_id)))
            .scalars()
            .all()
        )
        assert len(candle_rows) == 1
        assert candle_rows[0].is_final is True
        assert candle_rows[0].open_time == open_time
        assert candle_rows[0].open_time == align_open_time(candle_rows[0].open_time, Timeframe.M1)

        liq_rows = (
            (await session.execute(select(Liquidation).where(Liquidation.market_id == market_id)))
            .scalars()
            .all()
        )
        assert len(liq_rows) == 1
        assert liq_rows[0].id == liquidation_id(liq_event)

    # ---- market_snapshots: one per minute, none with no hot state ---------
    from hunter_market_worker.sampling import write_snapshots

    await write_snapshots(worker_session_factory, worker_redis, EXCHANGE, [SYMBOL], worker_settings)
    await write_snapshots(worker_session_factory, worker_redis, EXCHANGE, [SYMBOL], worker_settings)
    async with worker_session_factory() as session:
        from sqlalchemy import select

        from hunter_core.db.models.market_data import MarketSnapshot

        snap_rows = (
            (
                await session.execute(
                    select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(snap_rows) == 1  # ON CONFLICT (market_id, ts) DO NOTHING -- not two

    # ---- 4. API responses ---------------------------------------------------
    list_resp = await pipeline_client.get("/api/v1/markets", headers=authed_actor)
    assert list_resp.status_code == 200, list_resp.text
    body = list_resp.json()
    row = next(item for item in body["items"] if item["symbol"] == SYMBOL)
    assert row["data_quality"] == "ok"  # ticker+book+mark all fresh, no gap
    assert row["last_price"] == "50000.50"
    assert row["bid"] == str(ticker_event.bid)

    detail_resp = await pipeline_client.get(
        f"/api/v1/markets/{EXCHANGE}/{SYMBOL}", headers=authed_actor
    )
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert detail["book"]["depth"] == 20
    assert detail["book"]["kind"] == "snapshot"
    assert len(detail["recent_trades"]) == 1
    assert detail["recent_trades"][0]["price"] == "50000.60"

    candles_resp = await pipeline_client.get(
        f"/api/v1/markets/{EXCHANGE}/{SYMBOL}/candles", headers=authed_actor
    )
    assert candles_resp.status_code == 200, candles_resp.text
    candles_body = candles_resp.json()
    assert len(candles_body) == 1  # endpoint is final-only by construction (no is_final field)
    assert Decimal(candles_body[0]["close"]) == Decimal("50020")
    assert isinstance(candles_body[0]["close"], str)  # Decimal-as-string, never float
    parsed_open_time = datetime.fromisoformat(candles_body[0]["open_time"])
    assert parsed_open_time == open_time == align_open_time(open_time, Timeframe.M1)

    # ---- 5. heartbeat -> /system/workers, /system/market-status, rt:system -
    state = HeartbeatState()
    hb_pubsub: Any = worker_redis.pubsub()
    await hb_pubsub.subscribe("rt:system")
    hb_task = asyncio.create_task(
        run_heartbeat(
            cast("WorkerRuntime", _FakeRuntime(worker_redis)),
            adapter,
            universe,
            state,
            worker_session_factory,
        )
    )
    try:
        system_message = await _next_pubsub_message(hb_pubsub)
    finally:
        hb_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb_task
        await hb_pubsub.unsubscribe()
        await hb_pubsub.aclose()
    system_payload = orjson.loads(system_message["data"])
    assert system_payload["type"] == "market_status"
    assert system_payload["exchange"] == EXCHANGE
    assert system_payload["ws_state"] == "connected"

    workers_resp = await pipeline_client.get("/api/v1/system/workers", headers=authed_actor)
    assert workers_resp.status_code == 200, workers_resp.text
    worker_rows = workers_resp.json()
    assert any(w["role"] == "market" and w["instance"] == EXCHANGE for w in worker_rows)

    status_resp = await pipeline_client.get("/api/v1/system/market-status", headers=authed_actor)
    assert status_resp.status_code == 200, status_resp.text
    status_body = status_resp.json()
    exchange_row = next(e for e in status_body["exchanges"] if e["exchange"] == EXCHANGE)
    assert exchange_row["ws_state"] == "connected"
    # `>= 1`, not `== 1`: this Postgres database is shared across every file
    # in this suite (see the isolation note above `load_market_ids` earlier
    # in this test) -- other tests' own single-market universes may also be
    # monitored right now. "no gap for BTCUSDT specifically" is already
    # proven, order-independently, by `row["data_quality"] == "ok"` above
    # (the aggregate rule forces `degraded` whenever `has_open_gap` is true).
    assert exchange_row["markets_monitored"] >= 1
    assert isinstance(exchange_row["open_gaps"], int)


async def test_the_real_ingest_loop_consumes_adapter_stream_into_hot_state(
    worker_redis: Any, worker_settings: Settings
) -> None:
    """Astra's second opinion (T1.7): the main pipeline test above builds
    ``NormalizedEvent``s and dispatches them to ``handle_event`` directly --
    it never actually drives ``adapter.stream()`` through the real
    ``run_ingest``/``consume_once`` consumption loop
    (``services/market-worker/hunter_market_worker/streaming.py``), so a
    regression in how that loop reads the adapter's async iterator, filters
    by symbol, or wires up ``AcceptedEvents``/``TradeMemory`` could pass
    unnoticed. This test scripts events onto ``FakeExchangeAdapter`` itself
    (the T1.2 public contract) and lets the real ``run_ingest`` pull them.
    """
    from hunter_market_worker.heartbeat import HeartbeatState
    from hunter_market_worker.streaming import run_ingest
    from hunter_market_worker.supervision import IngestionHealth, Watchdog
    from hunter_market_worker.universe import MonitoredUniverse

    symbol = "INGESTLOOPUSDT"
    ticker_event = b.ticker(symbol, "777")
    trade_event = b.trade(symbol, "778", "1", trade_id="loop-1")
    adapter = FakeExchangeAdapter(code=EXCHANGE, events=[ticker_event, trade_event])

    universe = MonitoredUniverse()
    universe.set([symbol])
    queues = PersistQueues()
    coalescer = TickCoalescer()
    heartbeat_state = HeartbeatState()
    health = IngestionHealth()
    watchdog = Watchdog(adapter, lambda _msg: _noop())
    runtime = _FakeRuntime(worker_redis)

    task = asyncio.create_task(
        run_ingest(
            adapter,
            worker_redis,
            worker_settings,
            universe,
            queues,
            heartbeat_state,
            runtime,
            coalescer,
            health,
            watchdog,
        )
    )
    try:
        async with asyncio.timeout(5):
            key = keys.trades(EXCHANGE, symbol)
            while await worker_redis.llen(key) == 0:  # noqa: ASYNC110 -- polling a Redis list length, not a plain asyncio.Event
                await asyncio.sleep(0.02)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # The trade is written immediately by the real dispatch path inside
    # `consume_once` -> `handle_event`.
    trades_raw = await worker_redis.lrange(keys.trades(EXCHANGE, symbol), 0, -1)
    assert len(trades_raw) == 1
    # The ticker only reaches hot state on the coalescer's own flush (B3) --
    # confirm it was accepted into the coalescer by the real loop.
    published = await flush_ticks(coalescer, worker_redis, f"market-worker@{runtime.instance}")
    assert published == [symbol]
    raw_ticker = await worker_redis.hgetall(keys.ticker(EXCHANGE, symbol))
    assert raw_ticker[b"last"] == b"777"


async def _noop() -> None:
    return None


class _FakeRuntime:
    """The handful of ``WorkerRuntime`` attributes ``run_heartbeat`` touches --
    a real ``WorkerRuntime`` would also open its own engine/health server,
    neither of which this test needs."""

    def __init__(self, redis: Any) -> None:
        self.redis = redis
        self.instance = "pipeline-it"

    def mark_success(self) -> None:
        return None

    def mark_error(self) -> None:
        return None


async def _last_stream_entry(redis: Any, stream: str) -> dict[str, Any]:
    entries = await redis.xrange(stream, "-", "+")
    assert entries, f"nothing published on {stream}"
    _id, fields = entries[-1]
    from hunter_core.events.envelope import EventEnvelope

    envelope = EventEnvelope.from_bytes(fields[b"data"])
    return envelope.model_dump(mode="json")


async def _next_pubsub_message(pubsub: Any, wait_up_to_s: float = 5.0) -> dict[str, Any]:
    async with asyncio.timeout(wait_up_to_s):
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None:
                return message
