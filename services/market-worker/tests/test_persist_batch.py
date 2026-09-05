"""CRITICAL-1/H6+D10: one INSERT per table per flush, Python-side dedupe
keeping the LAST row per conflict key. M1+D7: liquidation duplicates are
counted and only newly-inserted rows are reported as insertable. D11:
liquidation dedupe truncates to the millisecond, matching ``liquidation_id``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from hunter_core.db.models.market_data import (
    Candle,
    FundingRate,
    Liquidation,
    MarketSnapshot,
    OpenInterestHistory,
)
from hunter_core.db.session import role_session
from hunter_core.observability import market_liquidation_duplicates_total
from hunter_market_worker import persist
from hunter_market_worker.queues import PersistItem, RealizedFunding, Snapshot, losses_total

from . import builders
from .db_helpers import seed_market
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


class _StatementCounter:
    """Counts ``cursor.execute`` calls whose SQL contains ``needle`` — used
    to prove a batch issues exactly one round trip per table (CRITICAL-1)."""

    def __init__(self, session_factory: async_sessionmaker[Any], needle: str) -> None:
        self.needle = needle
        self.count = 0
        self._engine = session_factory.kw["bind"].sync_engine

    def __enter__(self) -> _StatementCounter:
        event.listen(self._engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc_info: object) -> None:
        event.remove(self._engine, "before_cursor_execute", self._on_execute)

    def _on_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if self.needle in statement:
            self.count += 1


async def test_snapshot_batch_issues_exactly_one_insert_statement(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    symbols = [f"SYM{i}USDT" for i in range(20)]
    for symbol in symbols:
        await seed_market(db_session_factory, code, symbol)
    now = builders.utcnow().replace(second=0, microsecond=0)
    batch: list[PersistItem] = [
        Snapshot(symbol=s, values={"ts": now, "price": builders.Decimal("100")}) for s in symbols
    ]

    with _StatementCounter(db_session_factory, "INSERT INTO market_snapshots") as counter:
        await persist.flush_batch(db_session_factory, code, batch)

    assert counter.count == 1


async def test_flush_batch_snapshot_is_idempotent_across_two_flushes(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = builders.utcnow().replace(second=0, microsecond=0)
    batch: list[PersistItem] = [
        Snapshot(symbol="BTCUSDT", values={"ts": now, "price": builders.Decimal("100")})
    ]

    await persist.flush_batch(db_session_factory, code, batch)
    await persist.flush_batch(db_session_factory, code, batch)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = list(
            await session.scalars(
                select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
            )
        )
    assert len(rows) == 1


async def test_oi_dedupe_within_bucket_keeps_last_value(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = builders.utcnow().replace(minute=10, second=0, microsecond=0)
    first = builders.open_interest("BTCUSDT", "10", ts=now, exchange=code)
    second = builders.open_interest("BTCUSDT", "99", ts=now + timedelta(seconds=30), exchange=code)

    await persist.flush_batch(db_session_factory, code, [first, second])

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = list(
            await session.scalars(
                select(OpenInterestHistory).where(OpenInterestHistory.market_id == market_id)
            )
        )
    assert len(rows) == 1
    assert rows[0].open_interest == builders.Decimal("99")


async def test_candle_dedupe_within_batch_keeps_last_occurrence(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    first = builders.candle("BTCUSDT", close=builders.Decimal("100"), exchange=code)
    second = first.model_copy(update={"close": builders.Decimal("200")})

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        market_ids = {"BTCUSDT": market_id}
        inserted = await persist.upsert_candles(session, [first, second], market_ids, source="ws")

    assert inserted == 1
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(select(Candle).where(Candle.market_id == market_id))
    assert row is not None and row.close == builders.Decimal("200")


async def test_funding_dedupe_within_batch_keeps_last_occurrence(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    base = builders.funding("BTCUSDT", "0.0001", exchange=code)
    first = RealizedFunding.model_validate(base.model_dump())
    second = first.model_copy(update={"funding_rate": builders.Decimal("0.0009")})

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_funding(session, [first, second], {"BTCUSDT": market_id})

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(select(FundingRate).where(FundingRate.market_id == market_id))
    assert row is not None and row.rate == builders.Decimal("0.0009")


async def test_two_identical_liquidations_in_one_batch_do_not_raise_and_produce_one_row(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    liq = builders.liquidation("BTCUSDT", exchange=code)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        inserted = await persist.upsert_liquidations(session, [liq, liq], {"BTCUSDT": market_id})

    assert len(inserted) == 1
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        count = await session.scalar(
            select(Liquidation.id).where(Liquidation.market_id == market_id)
        )
    assert count is not None


async def test_liquidation_ts_truncated_to_millisecond_dedupes_sub_millisecond_redelivery(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    ts = builders.utcnow().replace(microsecond=123456)
    first = builders.liquidation("BTCUSDT", exchange=code, ts=ts)
    second = first.model_copy(update={"ts": ts.replace(microsecond=123999)})

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_liquidations(session, [first, second], {"BTCUSDT": market_id})

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = list(
            await session.scalars(select(Liquidation).where(Liquidation.market_id == market_id))
        )
    assert len(rows) == 1


async def test_repeated_flush_counts_duplicates_and_returns_only_newly_inserted_ids(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    liqs: list[PersistItem] = [
        builders.liquidation("BTCUSDT", exchange=code, qty=str(i + 1)) for i in range(5)
    ]
    metric = cast(Any, market_liquidation_duplicates_total)
    before = metric._value.get()

    first_ids = await persist.flush_batch(db_session_factory, code, liqs)
    second_ids = await persist.flush_batch(db_session_factory, code, liqs)

    assert len(first_ids) == 5
    assert second_ids == set()
    assert metric._value.get() == before + 5


async def test_unknown_market_symbol_bumps_persistence_drops_metric(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    liq = builders.liquidation("NOPEUSDT", exchange=code)
    metric = cast(Any, losses_total.labels(kind="liquidation", reason="unknown_market"))
    before = metric._value.get()

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        inserted = await persist.upsert_liquidations(session, [liq], {})

    assert inserted == set()
    assert metric._value.get() == before + 1
