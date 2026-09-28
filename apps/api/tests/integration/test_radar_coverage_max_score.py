"""``RadarCoverageRepository.max_score_ever`` under ``history_v2`` (27/09/2026).

Since the scanner samples ``opportunity_history`` sparsely (DATABASE.md §17.3a),
an ANOMALY episode that goes 30 → 45 → 30 inside five minutes without a status or
stage change leaves **no** 45 in the history — and the coverage strip would say
"maior score 30, primeiro degrau 40", which is false. ``opportunities.peak_score``
is kept on every sample (``hunter_indicators.opportunity.status``), so the ceiling
is the greater of the two, each aggregated on its own: an expired episode still
counts through its peak, and a history sample still counts after the episode
row's peak was never written (NULL). The API suite shares one database, so these
exact-value assertions run in a database of their own.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hunter_api.repositories.radar_coverage import RadarCoverageRepository

pytestmark = pytest.mark.integration

DB_NAME = "hunter_radar_coverage_max_it"


@pytest.fixture(scope="module")
def coverage_database_url(migrate_fresh_database: Callable[[str], str]) -> str:
    return migrate_fresh_database(DB_NAME)


@pytest_asyncio.fixture
async def factory(coverage_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(coverage_database_url, connect_args={"statement_cache_size": 0})
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE opportunity_history, opportunities CASCADE"))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _market(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    exchange_id, market_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'test') "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": exchange_id, "code": f"x{exchange_id.hex[:8]}"},
        )
        await session.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                "VALUES (:id, :exchange, :symbol, 'perpetual')"
            ),
            {"id": market_id, "exchange": exchange_id, "symbol": f"T{market_id.hex[:6]}USDT"},
        )
    return market_id


async def _episode(
    factory: async_sessionmaker[AsyncSession],
    *,
    score: str,
    peak: str | None,
    expired: bool = False,
    history: tuple[str, ...] = (),
) -> None:
    market_id = await _market(factory)
    opportunity_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO opportunities (id, market_id, direction, score, confidence, "
                "peak_score, status, expired_at) VALUES (:id, :market, 'long', :score, 0.5, "
                ":peak, CAST(:status AS opportunity_status), :expired_at)"
            ),
            {
                "id": opportunity_id,
                "market": market_id,
                "score": Decimal(score),
                "peak": None if peak is None else Decimal(peak),
                "status": "EXPIRED" if expired else "ANOMALY",
                "expired_at": now if expired else None,
            },
        )
        for index, value in enumerate(history):
            await session.execute(
                text(
                    "INSERT INTO opportunity_history (opportunity_id, ts, score, confidence, "
                    "status) VALUES (:id, :ts, :score, 0.5, 'ANOMALY')"
                ),
                {
                    "id": opportunity_id,
                    "ts": now.replace(microsecond=index),
                    "score": Decimal(value),
                },
            )


async def _max(factory: async_sessionmaker[AsyncSession]) -> Decimal | None:
    async with factory() as session:
        return await RadarCoverageRepository(session).max_score_ever()


async def test_a_peak_the_sparse_history_never_sampled_still_counts(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await _episode(factory, score="30", peak="45", history=("30", "30"))

    assert await _max(factory) == Decimal("45")


async def test_an_expired_episode_counts_through_its_peak_after_its_history_is_gone(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Right after the TRUNCATE of 27/09 there is no history at all."""
    await _episode(factory, score="12", peak="47.5", expired=True)
    await _episode(factory, score="20", peak="21")

    assert await _max(factory) == Decimal("47.5")


async def test_a_history_sample_above_every_peak_still_wins(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await _episode(factory, score="10", peak=None, history=("38.33",))

    assert await _max(factory) == Decimal("38.33")


async def test_nothing_scored_is_still_none(factory: async_sessionmaker[AsyncSession]) -> None:
    assert await _max(factory) is None


async def test_an_episode_with_neither_peak_nor_history_is_not_seen(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """The limit the web note words around (Astra, 27/09): a legacy row with a NULL
    ``peak_score`` whose history was pruned is invisible to the ceiling, so the note
    speaks of "the peaks stored and the history still retained", never of every
    score ever recorded."""
    await _episode(factory, score="65", peak=None)
    await _episode(factory, score="25", peak="30")

    assert await _max(factory) == Decimal("30")
