"""T4.61b — the conviction read against a real Postgres: one statement, the 60 s
peak of ``meme_curve_snapshots`` and the newest fresh ``meme_features_15s`` row,
as ``hunter_worker`` (the role the admission reads with)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_executor.conviction import ConvictionConfig
from hunter_meme_executor.conviction_read import read_series_evidence
from hunter_meme_executor.journal_db import WORKER_ROLE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

MINT = "T461bConvictionReadMintXXXXXXXXXXXXXXXXXXpump"
NOW = datetime(2026, 9, 18, 18, 5, tzinfo=UTC)
CONFIG = ConvictionConfig()

_SNAPSHOT = text(
    "INSERT INTO meme_curve_snapshots (observed_at, mint, source, virtual_sol_reserves, "
    "  virtual_token_reserves, real_sol_reserves, real_token_reserves, total_supply, complete) "
    "VALUES (:at, :mint, :source, 30, 1000000000, :real, 700000000, 1000000000, false)"
)
_FEATURES = text(
    "INSERT INTO meme_features_15s (as_of, mint, features_version, snapshots_120s, "
    "  window_reason, progress_reason, holders, holders_prev, holders_rising, "
    "  buys_60s, sells_60s, unique_buyers_60s, net_sol_flow_60s, curve_volume_60s_sol, "
    "  creator_net_seller_reason, dev_share_reason, snipers_reason) "
    "VALUES (:at, :mint, 'meme_features_15s_v1', 0, 'no_snapshot', 'no_snapshot', "
    "  :holders, :holders_prev, :rising, 10, 2, :buyers, 1.5, 3.0, "
    "  'no_tape', 'no_reader', 'no_tape')"
)


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        for offset, real in ((-80, "40"), (-45, "12.5"), (-20, "9"), (5, "99")):
            # -80 s is outside the 60 s window; +5 s is in the future (never read).
            await connection.execute(
                _SNAPSHOT,
                {
                    "at": NOW + timedelta(seconds=offset),
                    "mint": MINT,
                    "source": "solana_rpc",
                    "real": Decimal(real),
                },
            )
        for offset, buyers, rising in ((-200, 50, True), (-30, 31, False), (-10, 12, True)):
            await connection.execute(
                _FEATURES,
                {
                    "at": NOW + timedelta(seconds=offset),
                    "mint": MINT,
                    "holders": 20,
                    "holders_prev": 18,
                    "rising": rising,
                    "buyers": buyers,
                },
            )


async def _clean(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM meme_curve_snapshots WHERE mint = :mint"), {"mint": MINT}
        )
        await connection.execute(
            text("DELETE FROM meme_features_15s WHERE mint = :mint"), {"mint": MINT}
        )


@pytest.mark.asyncio
async def test_the_peak_is_the_window_max_and_the_row_is_the_newest_fresh_one(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    await _clean(db_engine)
    await _seed(db_engine)
    try:
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            series = await read_series_evidence(session, MINT, config=CONFIG, now=NOW)
    finally:
        await _clean(db_engine)
    assert series["peak_real_sol"] == Decimal("12.5"), "not the 40 at -80 s, not the 99 at +5 s"
    assert series["peak_points"] == 2
    assert series["unique_buyers_60s"] == 12 and series["holders_rising"] is True
    assert series["as_of"] == NOW - timedelta(seconds=10)


@pytest.mark.asyncio
async def test_a_mint_nobody_photographed_reads_as_nothing(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        series = await read_series_evidence(session, "NoSuchMint", config=CONFIG, now=NOW)
    assert series["peak_real_sol"] is None and series["peak_points"] == 0
    assert series["unique_buyers_60s"] is None and series["holders_rising"] is None
