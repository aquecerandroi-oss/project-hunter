"""Batch persistence: idempotent upserts and the drain/snapshot/OI loops."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.market_data import (
    Candle,
    FundingRate,
    Liquidation,
    MarketSnapshot,
    OpenInterestHistory,
)
from hunter_core.db.session import role_session
from hunter_core.observability import market_snapshot_skipped_no_data_total
from hunter_core.settings import Settings
from hunter_market_worker import hot_state, persist
from hunter_market_worker.queues import RealizedFunding

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_upsert_candles_is_idempotent_on_double_delivery(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    candle = builders.candle("BTCUSDT")

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        first = await persist.upsert_candles(session, [candle], {"BTCUSDT": market_id}, source="ws")
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        second = await persist.upsert_candles(
            session, [candle], {"BTCUSDT": market_id}, source="ws"
        )

    assert first == 1
    assert second == 0  # the redelivery hit ON CONFLICT DO NOTHING
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        count = await session.scalar(
            select(func.count()).select_from(Candle).where(Candle.market_id == market_id)
        )
    assert count == 1


async def testflush_batch_writes_candle_funding_and_liquidation(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ETHUSDT")
    candle = builders.candle("ETHUSDT")
    funding = builders.funding("ETHUSDT", "0.0002", next_funding_time=candle.open_time)
    funding = RealizedFunding.model_validate(funding.model_dump())
    liquidation = builders.liquidation("ETHUSDT")

    await persist.flush_batch(db_session_factory, exchange_code, [candle, funding, liquidation])

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        candle_count = await session.scalar(
            select(func.count()).select_from(Candle).where(Candle.market_id == market_id)
        )
        funding_count = await session.scalar(
            select(func.count()).select_from(FundingRate).where(FundingRate.market_id == market_id)
        )
        liq_count = await session.scalar(
            select(func.count()).select_from(Liquidation).where(Liquidation.market_id == market_id)
        )
    assert (candle_count, funding_count, liq_count) == (1, 1, 1)


async def test_liquidation_upsert_dedupes_identical_redelivery(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    liq = builders.liquidation("BTCUSDT", price="60000", qty="0.5")

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_liquidations(session, [liq], {"BTCUSDT": market_id})
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_liquidations(session, [liq], {"BTCUSDT": market_id})
        count = await session.scalar(
            select(func.count()).select_from(Liquidation).where(Liquidation.market_id == market_id)
        )
    assert count == 1


async def testsnapshot_loop_writes_one_row_with_nulls_when_hot_state_missing(
    db_session_factory: Any, redis_client: Any
) -> None:
    """D9 (orchestrator decision): no hot state at all -> "not observed", so
    no row is written (the insert is ON CONFLICT DO NOTHING and would make an
    all-NULL row permanent) and the skip is counted instead."""
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    metric = cast(Any, market_snapshot_skipped_no_data_total)
    before = metric._value.get()

    # no hot state written for BTCUSDT at all -> the market is skipped, not
    # persisted with nulls
    await persist.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["BTCUSDT"], Settings()
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is None
    assert metric._value.get() == before + 1  # pyright: ignore[reportPrivateUsage]


async def testsnapshot_loop_reads_hot_state_when_present(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ETHUSDT")
    ticker = builders.ticker("ETHUSDT", "3000", exchange=exchange_code)
    await hot_state.write_ticker(redis_client, ticker, source="rest")

    await persist.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["ETHUSDT"], Settings()
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is not None
    assert row.price == 3000


async def test_snapshot_carries_both_rest_volume_and_ws_spread_together(
    db_session_factory: Any, redis_client: Any
) -> None:
    """KB-0044, durable side: ``market_snapshots`` reads the ticker hash with
    one ``HGETALL`` (``sampling.py::write_snapshots``), so it inherited the
    field-clobbering bug wholesale -- a REST refresh and a WS bookTicker
    landing close together used to leave the hash (and therefore the
    snapshot) with only one side's fields. With per-producer ownership, a
    REST write followed by a WS write leaves both in the hash at once, and
    the persisted row carries volume_24h *and* bid/ask/spread_pct from the
    same snapshot cycle -- no change needed in ``sampling.py`` itself."""
    from datetime import timedelta

    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")

    rest = builders.ticker_rest("BTCUSDT", "100", exchange=exchange_code)
    await hot_state.write_ticker(redis_client, rest, source="rest")
    ws = builders.ticker_ws(
        "BTCUSDT", "100.5", exchange=exchange_code, ts=rest.ts + timedelta(milliseconds=250)
    )
    await hot_state.write_ticker(redis_client, ws, source="ws")

    await persist.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["BTCUSDT"], Settings()
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is not None
    assert row.volume_24h == 1000
    assert row.bid == ws.bid
    assert row.ask == ws.ask
    assert row.spread_pct is not None


async def testoi_poll_loop_writes_history_and_hot_state(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    adapter = FakeAdapter(code=exchange_code)
    adapter.open_interests["BTCUSDT"] = builders.open_interest(
        "BTCUSDT", "42", exchange=exchange_code
    )
    universe_symbols = ["BTCUSDT"]

    class _Universe:
        symbols = universe_symbols

    universe: Any = _Universe()
    runtime: Any = FakeRuntime(redis=redis_client)
    settings: Any = type("S", (), {"market_oi_poll_s": 0.01})()

    task = asyncio.ensure_future(
        persist.oi_poll_loop(db_session_factory, redis_client, adapter, universe, settings, runtime)
    )
    async with asyncio.timeout(5):
        await runtime.success.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert adapter.fetch_open_interest_calls
    deriv = await redis_client.hgetall(f"mkt:{exchange_code}:BTCUSDT:deriv")
    assert deriv[b"open_interest"] == b"42"
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        count = await session.scalar(
            select(func.count())
            .select_from(OpenInterestHistory)
            .where(OpenInterestHistory.market_id == market_id)
        )
    assert count is not None and count >= 1
