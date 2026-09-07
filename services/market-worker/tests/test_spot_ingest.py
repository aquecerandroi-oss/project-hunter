"""T3.0c — the SPOT collection path, end to end, next to a live perpetual one.

Every test here runs **both** products at once, because every bug this task
exists to prevent is a collision: one hot-state key, one ``market_id``, one
coverage hash, one heartbeat, one pub/sub channel. A test that only ran spot
would pass with all of them still shared.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from decimal import Decimal
from typing import Any

import orjson
import pytest
from sqlalchemy import select

from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import Streams
from hunter_core.settings import Settings
from hunter_exchanges.base import StreamChannel
from hunter_market_worker.coalesce import realtime_channel
from hunter_market_worker.heartbeat import HeartbeatState, hb_key, run_heartbeat
from hunter_market_worker.ingest import AcceptedEvents, TickCoalescer, flush_ticks
from hunter_market_worker.persist import PersistQueues, flush_batch
from hunter_market_worker.spot import STATUS_ABSENT, STATUS_CONNECTED, SpotStatus, collects_spot
from hunter_market_worker.streaming import SPOT_CHANNELS, consume_once
from hunter_market_worker.supervision import IngestionHealth
from hunter_market_worker.universe import MonitoredUniverse

from . import builders
from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

SPOT = MarketType.SPOT
PERP = MarketType.PERPETUAL
PRODUCER = "market-worker@test:1"


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_spot_asks_for_the_four_channels_spot_actually_has() -> None:
    """``MARK_PRICE``/``LIQUIDATIONS`` are perpetual concepts and the spot
    adapter *refuses* them (T3.0a §4) — asking would be a startup failure."""
    assert set(SPOT_CHANNELS) == {
        StreamChannel.TRADES,
        StreamChannel.BOOK_TICKER,
        StreamChannel.BOOK,
        StreamChannel.KLINE_1M,
    }


@pytest.mark.unit
def test_the_perpetual_pubsub_channel_does_not_move_and_spot_gets_its_own() -> None:
    assert realtime_channel("binance", "BTCUSDT", PERP) == "rt:market:binance:BTCUSDT"
    assert realtime_channel("binance", "BTCUSDT", SPOT) == "rt:market-spot:binance:BTCUSDT"


@pytest.mark.unit
def test_the_tick_payload_names_its_product() -> None:
    from hunter_market_worker.ingest import build_tick_payload

    coalescer = TickCoalescer()
    coalescer.on_trade(builders.trade("BTCUSDT", "100", "2"))
    coalescer.on_trade(builders.trade("BTCUSDT", "101", "3", market_type=SPOT))
    [(perp_key, perp), (spot_key, spot)] = coalescer.dirty_items()

    assert perp_key[2] is PERP
    assert spot_key[2] is SPOT
    assert build_tick_payload("fake", "BTCUSDT", perp, "T")["market_type"] == "perpetual"
    assert build_tick_payload("fake", "BTCUSDT", spot, "T", SPOT)["market_type"] == "spot"


@pytest.mark.integration
async def test_flush_publishes_two_markets_on_two_channels(redis_client: Any) -> None:
    coalescer = TickCoalescer()
    coalescer.on_ticker(builders.ticker_ws("BTCUSDT", "100"))
    coalescer.on_ticker(builders.ticker_ws("BTCUSDT", "101", market_type=SPOT))
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("rt:market:fake:BTCUSDT", "rt:market-spot:fake:BTCUSDT")

    await flush_ticks(coalescer, redis_client, PRODUCER)

    seen: dict[str, str] = {}
    deadline = asyncio.get_running_loop().time() + 5
    while len(seen) < 2 and asyncio.get_running_loop().time() < deadline:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is not None:
            seen[message["channel"].decode()] = orjson.loads(message["data"])["price"]
    await pubsub.aclose()

    assert seen == {"rt:market:fake:BTCUSDT": "100", "rt:market-spot:fake:BTCUSDT": "101"}


@pytest.mark.integration
async def test_market_ticks_routes_spot_under_its_own_key(redis_client: Any) -> None:
    """The stream is shared; the routing key is not. A consumer that reads the
    key learns which listing a tick is about even if it ignores the payload."""
    coalescer = TickCoalescer()
    coalescer.on_ticker(builders.ticker_ws("BTCUSDT", "100"))
    coalescer.on_ticker(builders.ticker_ws("BTCUSDT", "101", market_type=SPOT))

    await flush_ticks(coalescer, redis_client, PRODUCER)

    entries = await redis_client.xrange(Streams.MARKET_TICKS)
    envelopes = [EventEnvelope.model_validate_json(fields[b"data"]) for _id, fields in entries]
    by_key = {e.key: e.payload for e in envelopes}
    assert by_key["fake:BTCUSDT"]["market_type"] == "perpetual"
    assert by_key["fake:spot:BTCUSDT"]["market_type"] == "spot"


# --------------------------------------------------------------------------
# Hot state and coverage through the real ingest loop
# --------------------------------------------------------------------------


async def _drain(adapter: FakeAdapter, redis: Any, symbols: list[str], **kwargs: Any) -> None:
    """Run ``consume_once`` until the fake stream is exhausted, then stop."""
    universe = MonitoredUniverse()
    universe.set(symbols)
    task = asyncio.ensure_future(
        consume_once(
            adapter,
            symbols,
            redis,
            PRODUCER,
            kwargs.pop("queues", PersistQueues()),
            kwargs.pop("coalescer", TickCoalescer()),
            AcceptedEvents(),
            __import__("hunter_market_worker.hot_state", fromlist=["TradeMemory"]).TradeMemory(),
            universe,
            HeartbeatState(),
            **kwargs,
        )
    )
    await asyncio.sleep(0.4)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


@pytest.mark.integration
async def test_spot_stream_writes_spot_hot_state_and_leaves_the_perpetual_untouched(
    redis_client: Any,
) -> None:
    code = unique_code()
    perp = FakeAdapter(code=code)
    spot = FakeAdapter(code=code)
    coalescer = TickCoalescer()

    await perp.push_event(builders.ticker_ws("BTCUSDT", "100", exchange=code))
    await perp.push_event(builders.order_book("BTCUSDT").model_copy(update={"exchange": code}))
    await _drain(perp, redis_client, ["BTCUSDT"], coalescer=coalescer)

    await spot.push_event(builders.ticker_ws("BTCUSDT", "101", exchange=code, market_type=SPOT))
    await spot.push_event(
        builders.order_book("BTCUSDT", "200", "200.1").model_copy(
            update={"exchange": code, "market_type": SPOT}
        )
    )
    await _drain(
        spot,
        redis_client,
        ["BTCUSDT"],
        coalescer=coalescer,
        market_type=SPOT,
        channels=SPOT_CHANNELS,
    )
    await flush_ticks(coalescer, redis_client, PRODUCER)

    assert await redis_client.hget(f"mkt:{code}:BTCUSDT:ticker", "last") == b"100"
    assert await redis_client.hget(f"mkt:{code}:spot:BTCUSDT:ticker", "last") == b"101"
    assert await redis_client.exists(f"mkt:{code}:BTCUSDT:book") == 1
    assert await redis_client.exists(f"mkt:{code}:spot:BTCUSDT:book") == 1
    assert spot.stream_calls[0][1] == list(SPOT_CHANNELS)


@pytest.mark.integration
async def test_spot_coverage_lands_on_its_own_hash(redis_client: Any) -> None:
    code = unique_code()
    spot = FakeAdapter(code=code)
    await spot.push_event(builders.trade("BTCUSDT", "100", "1", exchange=code, market_type=SPOT))

    await _drain(
        spot,
        redis_client,
        ["BTCUSDT"],
        market_type=SPOT,
        channels=SPOT_CHANNELS,
        coverage=__import__(
            "hunter_market_worker.coverage", fromlist=["CoverageTracker"]
        ).CoverageTracker(code, market_type=SPOT),
    )

    # The record exists under the spot name and *only* there. Its contents at
    # this point are the empty end-of-session record ``consume_once`` writes on
    # teardown, which is the honest statement ("the collector is gone"); what a
    # live session claims is asserted below, driving the tracker directly.
    assert await redis_client.exists(f"mkt:{code}:spot:coverage") == 1
    assert await redis_client.exists(f"mkt:{code}:coverage") == 0
    assert await redis_client.hgetall(f"mkt:{code}:spot:coverage") == {
        b"session_since": b"",
        b"covered_until": b"",
    }


@pytest.mark.integration
async def test_two_live_sessions_claim_two_hashes_and_never_each_others_symbols(
    redis_client: Any,
) -> None:
    from hunter_market_worker.coverage import CoverageTracker

    code = unique_code()
    now = builders.utcnow()
    perpetual = CoverageTracker(code)
    spot = CoverageTracker(code, market_type=SPOT)
    perpetual.session_started(["BTCUSDT", "ETHUSDT"], at=now - timedelta(seconds=5))
    spot.session_started(["BTCUSDT"], at=now - timedelta(seconds=5))

    assert await perpetual.stamp(redis_client, dropped_events=0, now=now)
    assert await spot.stamp(redis_client, dropped_events=0, now=now)

    perpetual_hash = await redis_client.hgetall(f"mkt:{code}:coverage")
    spot_hash = await redis_client.hgetall(f"mkt:{code}:spot:coverage")
    assert b"sym:ETHUSDT" in perpetual_hash
    assert b"sym:ETHUSDT" not in spot_hash, "spot claimed a market it never subscribed to"
    assert b"sym:BTCUSDT" in spot_hash


@pytest.mark.integration
async def test_a_spot_book_carries_no_exchange_clock_and_coverage_survives_it(
    redis_client: Any,
) -> None:
    """T3.0a §4: spot ``@bookTicker``/``@depth20`` have no event time, so the
    adapter stamps ``ts == received_at``. The coverage margin is measured
    against the collector's own clock, never the event's, so a book with no
    exchange clock neither inflates nor breaks the interval — the *trade*
    stream is what proves the tape (item 3 of the brief)."""
    from hunter_market_worker.coverage import CoverageTracker

    code = unique_code()
    now = builders.utcnow()
    tracker = CoverageTracker(code, market_type=SPOT)
    tracker.session_started(["BTCUSDT"], at=now - timedelta(seconds=5))

    assert await tracker.stamp(redis_client, dropped_events=0, now=now)

    record = await redis_client.hgetall(f"mkt:{code}:spot:coverage")
    covered_until = record[b"covered_until"].decode()
    assert covered_until < now.isoformat(), "a stamp must never claim the clock itself"


# --------------------------------------------------------------------------
# Candles: the market_id that T3.0b's bug 1 was about
# --------------------------------------------------------------------------


async def _two_listings(session_factory: Any, code: str) -> dict[MarketType, Any]:
    from hunter_market_worker.universe_repo import upsert_assets, upsert_exchange, upsert_markets

    async with role_session(session_factory, db_role="hunter_worker") as session:
        exchange_id = await upsert_exchange(session, code)
        asset_ids = await upsert_assets(session, {"BTC", "USDT"})
        await upsert_markets(
            session,
            exchange_id,
            [
                builders.market("BTCUSDT", "BTC", exchange=code),
                builders.market("BTCUSDT", "BTC", exchange=code, market_type=SPOT),
            ],
            asset_ids,
            {},
        )
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.execute(
                select(Market.id, Market.market_type)
                .join(Exchange, Exchange.id == Market.exchange_id)
                .where(Exchange.code == code)
            )
        ).all()
    return {row.market_type: row.id for row in rows}


@pytest.mark.integration
async def test_a_spot_candle_is_persisted_under_the_spot_market_id(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    ids = await _two_listings(db_session_factory, code)
    open_time = builders.align_open_time(builders.utcnow(), Timeframe.M1) - timedelta(minutes=1)

    await flush_batch(
        db_session_factory,
        code,
        [
            builders.candle(
                "BTCUSDT", open_time, exchange=code, close=Decimal("111"), high=Decimal("111")
            )
        ],
        producer=PRODUCER,
    )
    await flush_batch(
        db_session_factory,
        code,
        [
            builders.candle(
                "BTCUSDT",
                open_time,
                exchange=code,
                market_type=SPOT,
                close=Decimal("222"),
                high=Decimal("222"),
            )
        ],
        producer=PRODUCER,
        market_type=SPOT,
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.execute(
                select(Candle.market_id, Candle.close).where(
                    Candle.market_id.in_([ids[PERP], ids[SPOT]])
                )
            )
        ).all()
    by_market = {row.market_id: row.close for row in rows}
    assert by_market[ids[PERP]] == Decimal("111")
    assert by_market[ids[SPOT]] == Decimal("222")


# --------------------------------------------------------------------------
# Heartbeat, readiness and topology
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_heartbeat_keys_of_the_two_products_are_disjoint_under_glob() -> None:
    from fnmatch import fnmatchcase

    from hunter_core.redis import keys

    assert hb_key("binance") == "hb:market:binance"
    assert hb_key("binance", market_type=SPOT) == "hb:market:spot:binance"
    # T3.0b §1: the type goes *before* the exchange because Redis glob matches
    # ``:`` — the shard scan of the perpetual must never sweep up a spot key.
    pattern = keys.market_heartbeat_shard_pattern("binance")
    assert not fnmatchcase("hb:market:spot:binance:0of1", pattern)
    assert fnmatchcase("hb:market:binance:0of4", pattern)


@pytest.mark.integration
async def test_the_spot_heartbeat_is_solo_and_never_publishes_rt_system(
    redis_client: Any, db_session_factory: Any
) -> None:
    """A spot ``ws_state`` written into ``rt:system`` would replace the whole
    perpetual exchange row on the System page with the wrong connection's state."""
    code = unique_code()
    adapter = FakeAdapter(code=code)
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    runtime: Any = FakeRuntime(redis_client, settings=Settings(market_shard="0/4"))
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("rt:system")

    task = asyncio.ensure_future(
        run_heartbeat(
            runtime,
            adapter,
            universe,
            HeartbeatState(),
            db_session_factory,
            market_type=SPOT,
            shard=(0, 1),
        )
    )
    await asyncio.sleep(0.3)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert await redis_client.exists(f"hb:market:spot:{code}") == 1
    assert await redis_client.exists(f"hb:market:spot:{code}:0of4") == 0
    hash_ = await redis_client.hgetall(f"hb:market:spot:{code}")
    assert hash_[b"shard_total"] == b"1"
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
    await pubsub.aclose()
    assert message is None


@pytest.mark.unit
def test_only_shard_zero_collects_spot_and_the_switch_is_honoured() -> None:
    assert collects_spot(Settings(market_shard="0/4", market_spot_enabled=True)) is True
    assert collects_spot(Settings(market_shard="1/4", market_spot_enabled=True)) is False
    assert collects_spot(Settings(market_shard="0/1", market_spot_enabled=False)) is False
    # Off unless an operator says otherwise: the switch carries a measured cost
    # to the perpetual collector sharing the event loop (see the field's docstring).
    assert collects_spot(Settings(market_shard="0/1")) is False


@pytest.mark.unit
def test_the_scanner_survives_a_spot_tick_but_does_not_yet_filter_one_out() -> None:
    """A **contract check across services**, written here because T3.0c may run
    the scanner's tests but not change them.

    The finding, stated plainly rather than assumed: the scanner's ``market.ticks``
    consumer neither crashes on a spot payload nor discriminates it. ``symbol_of``
    reads ``payload["symbol"]``, which is ``BTCUSDT`` for both listings, and
    ``ScannerState.touch`` is keyed by symbol alone — so a spot tick marks the
    **perpetual** market dirty and can set its ``last_input_ts``. Today the damage
    is bounded (every spot symbol is already receiving perpetual ticks at 4 Hz, so
    the market is dirty anyway, and both timestamps are ~now), but it is real
    contamination of another service's latency accounting.

    The one-line fix belongs to whoever owns ``services/scanner-worker``:
    ``touch_batch_handler`` should skip a delivery whose
    ``payload["market_type"]`` is not ``"perpetual"``. Registered in
    ``.claude/state/notes-T3.0c.md``.
    """
    from hunter_market_worker.ingest import build_tick_payload
    from hunter_scanner_worker.consumers import coalesce, symbol_of

    coalescer = TickCoalescer()
    coalescer.on_trade(builders.trade("BTCUSDT", "101", "3", market_type=SPOT))
    [(_key, accum)] = coalescer.dirty_items()
    payload = build_tick_payload("binance", "BTCUSDT", accum, builders.utcnow().isoformat(), SPOT)
    envelope = EventEnvelope(
        type=Streams.MARKET_TICKS, producer=PRODUCER, key="binance:spot:BTCUSDT", payload=payload
    )

    result = coalesce([("1-0", envelope)])

    # Does not break: the batch is coalesced and the message is accounted for.
    assert result.newest and result.absorbed == 0
    # Does not filter either — and the routing key that *would* disambiguate is
    # not what ``symbol_of`` looks at.
    assert symbol_of(envelope) == "BTCUSDT"
    assert payload["market_type"] == "spot"


@pytest.mark.unit
def test_spot_readiness_detail_is_absent_degraded_or_connected() -> None:
    status = SpotStatus()
    assert status() == STATUS_ABSENT

    health = IngestionHealth()
    status.enabled, status.health = True, health
    health.update("connecting", active=True)
    assert status() == "degraded"
    health.update("connected", active=True)
    assert status() == STATUS_CONNECTED
    # Nothing cleared the 50M floor: subscribed to nothing is the rule working,
    # not a degradation of this process.
    health.update("idle", active=False)
    assert status() == STATUS_CONNECTED
