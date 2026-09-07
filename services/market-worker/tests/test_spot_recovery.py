"""T3.0c — gaps, duplicates, reconnects and restart on the SPOT path.

The brief asks a direct question: *does the recovery cover both products?* It
does now, and it does it the only safe way — by resolving symbols to the right
``markets`` row. What follows proves that, and proves the perpetual's recovery
did not start seeing spot markets in the process.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.events.streams import Streams
from hunter_core.settings import Settings
from hunter_exchanges.base import ExchangeUnavailable
from hunter_market_worker import recovery, spot_universe
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.ingest import TickCoalescer
from hunter_market_worker.persist import PersistQueues, flush_batch
from hunter_market_worker.streaming import SPOT_CHANNELS, run_ingest
from hunter_market_worker.supervision import IngestionHealth, Watchdog
from hunter_market_worker.universe import MonitoredUniverse

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

SPOT = MarketType.SPOT
PERP = MarketType.PERPETUAL
PRODUCER = "market-worker@test:1"


async def _gaps(session_factory: Any, market_id: Any) -> list[IngestionGap]:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(IngestionGap).where(IngestionGap.market_id == market_id)
        )
        return list(rows)


async def test_spot_gap_detection_opens_gaps_against_the_spot_market_id(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    perpetual_id = await seed_market(db_session_factory, code, "BTCUSDT")
    spot_id = await seed_market(db_session_factory, code, "BTCUSDT", market_type=SPOT)
    adapter = FakeAdapter(code=code)
    end = align_open_time(utcnow() - recovery.DETECTION_GRACE, Timeframe.M1)
    adapter.candles_response["BTCUSDT"] = [
        builders.candle(
            "BTCUSDT", open_time=end - timedelta(minutes=5), exchange=code, market_type=SPOT
        )
    ]

    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], HeartbeatState(), SPOT)

    assert await _gaps(db_session_factory, spot_id), "no gap was opened for the spot listing"
    assert not await _gaps(db_session_factory, perpetual_id), (
        "the spot recovery opened gaps against the perpetual's market_id"
    )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        recovered = await session.scalar(
            select(func.count()).select_from(Candle).where(Candle.market_id == spot_id)
        )
    assert recovered == 1


async def test_the_perpetual_recovery_never_sees_the_spot_listing(
    db_session_factory: Any,
) -> None:
    """The mirror image, and the one that protects what is already running."""
    code = unique_code()
    perpetual_id = await seed_market(db_session_factory, code, "BTCUSDT")
    spot_id = await seed_market(db_session_factory, code, "BTCUSDT", market_type=SPOT)
    adapter = FakeAdapter(code=code)

    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], HeartbeatState())

    assert await _gaps(db_session_factory, perpetual_id)
    assert not await _gaps(db_session_factory, spot_id)


async def test_the_same_spot_candle_twice_is_one_row_and_one_announcement(
    db_session_factory: Any,
) -> None:
    """Mandatory case "duplicate candle", on the spot side of the identity."""
    code = unique_code()
    spot_id = await seed_market(db_session_factory, code, "BTCUSDT", market_type=SPOT)
    open_time = align_open_time(utcnow(), Timeframe.M1) - timedelta(minutes=1)
    candle = builders.candle(
        "BTCUSDT",
        open_time,
        exchange=code,
        market_type=SPOT,
        close=Decimal("222"),
        high=Decimal("222"),
    )

    await flush_batch(db_session_factory, code, [candle], producer=PRODUCER, market_type=SPOT)
    await flush_batch(db_session_factory, code, [candle], producer=PRODUCER, market_type=SPOT)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = await session.scalar(
            select(func.count()).select_from(Candle).where(Candle.market_id == spot_id)
        )
        # Filtered by this test's own exchange code: the container's database
        # is session-scoped and every other test's outbox rows are in here too.
        events = list(
            await session.scalars(
                select(OutboxEvent.payload).where(
                    OutboxEvent.stream == Streams.MARKET_CANDLES_CLOSED
                )
            )
        )
    announced = [e for e in events if str(e.get("key", "")).startswith(code)]
    assert rows == 1
    assert len(announced) == 1


async def test_a_spot_stream_error_reconnects_and_never_ends_the_task(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Mandatory case "reconnect with gap", from the worker's side: the stream
    raises, the collector counts a reconnect and comes back, and the coverage
    record it leaves behind is the *empty* one — "the collector is here and
    cannot prove continuity", never a claim stretched across the outage."""
    code = unique_code()
    adapter = FakeAdapter(code=code)
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    state = HeartbeatState()
    runtime = FakeRuntime(redis_client)
    await adapter.push_event(builders.trade("BTCUSDT", "100", "1", exchange=code, market_type=SPOT))
    await adapter.push_event(ExchangeUnavailable("socket closed", exchange=code))

    task = asyncio.ensure_future(
        run_ingest(
            adapter,
            redis_client,
            Settings(),
            universe,
            PersistQueues(),
            state,
            runtime,
            TickCoalescer(),
            IngestionHealth(),
            Watchdog(adapter, _noop_warning),
            market_type=SPOT,
            channels=SPOT_CHANNELS,
            shard=(0, 1),
        )
    )
    await asyncio.sleep(1.5)
    running = not task.done()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task

    assert running, "a stream error ended the spot ingest task instead of reconnecting"
    assert state.reconnects >= 1
    assert state.last_error == "socket closed"
    assert await redis_client.hgetall(f"mkt:{code}:spot:coverage") == {
        b"session_since": b"",
        b"covered_until": b"",
    }


async def _noop_warning(_message: str) -> None:
    return None


async def test_a_restart_collects_the_committed_spot_universe_before_any_refresh(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Mandatory case "restart": the last committed universe is what a fresh
    process subscribes to, instead of collecting nothing for a refresh interval."""
    code = unique_code()
    floor = spot_universe.SPOT_VOLUME_FLOOR_USDT
    adapter = FakeAdapter(code=code)
    for symbol, volume in (("BIGUSDT", floor * 2), ("SMALLUSDT", floor / 2)):
        adapter.markets.append(
            builders.market(symbol, symbol.removesuffix("USDT"), exchange=code, market_type=SPOT)
        )
        adapter.tickers[symbol] = builders.ticker_rest(
            symbol, "100", exchange=code, market_type=SPOT, quote_volume_24h=volume
        )
    await spot_universe.refresh_spot_universe(
        db_session_factory, adapter, redis_client, Settings(), producer=PRODUCER
    )

    restored = await spot_universe.monitored_spot_symbols(db_session_factory, code)

    assert restored == ["BIGUSDT"]
