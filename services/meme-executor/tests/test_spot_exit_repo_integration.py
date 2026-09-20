"""T4.74-5 — the SQL of ``spot_exit_repo`` and the windowed ``closed_stats``
against a real migrated Postgres (``0057`` applied): every statement parses,
names existing columns and answers the empty-table shape. The behaviour over
rows is proven by the fakes; this is the proof that the strings are SQL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.db.session import role_session
from hunter_meme_executor import spot_exit_repo as repo
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_repo import closed_stats

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)
NO_ROW = "01996e2a-0000-7000-8000-0000000000ff"


async def test_every_statement_runs_on_the_real_schema(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        assert await repo.sell_attempts(session, NO_ROW) == repo.SellAttempts(0, 0)
        assert await repo.unconfirmed_spot_orders(session) == []
        assert await repo.confirmed_buys_without_position(session) == []
        assert await repo.confirmed_sells_still_pending(session) == []
        assert await repo.pending_exits_on_terminal_orders(session) == []
        assert await repo.abandoned_orders(session, before=NOW) == []
        assert await repo.fail_abandoned(session, NO_ROW, reason="x", now=NOW) is False
        assert await repo.open_position_by_id(session, NO_ROW) is None
        assert await repo.enabled_market_count(session) == 35, "the 0057 seed"
        assert (
            await repo.set_exit_pending(
                session, NO_ROW, order_id=NO_ROW, reason="stop", attempt=1, now=NOW
            )
            is False
        )
        assert (
            await repo.clear_exit_pending(session, NO_ROW, order_id=NO_ROW, outcome="x", now=NOW)
            is False
        )
        stats = await closed_stats(session, since=NOW - timedelta(days=1), min_trades=20)
        assert stats.n == 0 and stats.sum_pnl_sol == Decimal(0)
        assert stats.min_run_pnl_sol is None and stats.min_expectancy_r_net is None
