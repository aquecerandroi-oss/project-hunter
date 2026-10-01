"""KB-0172 — ``spot_exit_repo.set_stop_episode`` on a real migrated Postgres:
the episode key is added to and removed from ``exit_intent`` without touching
any other key, and never while a sell is in flight (``exit_order_id`` set) or
after the position closed."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_exit_repo import (
    STOP_EPISODE_KEY,
    clear_exit_pending,
    set_exit_pending,
    set_stop_episode,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
TAG = "kb0172ep"
MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"


async def _plant(engine: AsyncEngine, exit_intent: dict[str, Any] | None) -> str:
    ids = {k: str(uuid.uuid4()) for k in ("strategy", "version", "exchange", "market", "signal")}
    order, position, key = str(uuid.uuid4()), str(uuid.uuid4()), f"{TAG}{uuid.uuid4().hex[:8]}"
    async with engine.begin() as conn:
        for sql in (
            "INSERT INTO strategies (id, key, name) VALUES (:strategy, :key, :tag)",
            "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:version, :strategy, 'v1')",
            "INSERT INTO exchanges (id, code, name) VALUES (:exchange, :key, :tag)",
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:market, :exchange, 'WIFUSDT', 'perpetual')",
            "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, direction, "
            "  confidence) VALUES (:signal, :version, :market, :tag, 'long', 0.5)",
        ):  # fmt: skip
            await conn.execute(text(sql), {**ids, "tag": TAG, "key": key})
        await conn.execute(
            text(
                "INSERT INTO spot_orders (id, signal_id, market_symbol, mint, side, client_order_id, "
                "  status, tx_signature, fill, settled_at, updated_at) VALUES (:id, :s, 'WIFUSDT', "
                "  :m, 'buy', :k, 'confirmed', :sig, '{}', :at, :at)"
            ),
            {
                "id": order,
                "s": ids["signal"],
                "m": MINT,
                "k": f"spot:buy:{ids['signal']}",
                "sig": f"sig-{order}",
                "at": NOW,
            },  # fmt: skip
        )
        await conn.execute(
            text(
                "INSERT INTO spot_positions (id, signal_id, entry_order_id, market_symbol, mint, "
                "  status, entry_at, entry, tokens, sol_spent_lamports, initial_risk_sol, params, "
                "  exit_intent) VALUES (:id, :s, :o, 'WIFUSDT', :m, 'open', :e, '{}', 1, 1, 0.001, "
                "  '{}', CAST(:intent AS jsonb))"
            ),
            {
                "id": position,
                "s": ids["signal"],
                "o": order,
                "m": MINT,
                "e": NOW - timedelta(hours=1),
                "intent": None if exit_intent is None else json.dumps(exit_intent),
            },  # fmt: skip
        )
    return position


async def _intent(engine: AsyncEngine, position: str) -> Any:
    async with engine.connect() as conn:
        sql = text("SELECT exit_intent FROM spot_positions WHERE id = :id")
        return (await conn.execute(sql, {"id": position})).scalar()


async def _clean(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM spot_positions WHERE mint = :m"), {"m": MINT})
        await conn.execute(text("DELETE FROM spot_orders WHERE mint = :m"), {"m": MINT})
        for sql in (
            "DELETE FROM agent_signals WHERE params_hash = :tag",
            "DELETE FROM markets WHERE exchange_id IN (SELECT id FROM exchanges WHERE name = :tag)",
            "DELETE FROM exchanges WHERE name = :tag",
            "DELETE FROM strategy_versions WHERE strategy_id IN (SELECT id FROM strategies WHERE name = :tag)",
            "DELETE FROM strategies WHERE name = :tag",
        ):  # fmt: skip
            await conn.execute(text(sql), {"tag": TAG})


async def test_the_episode_key_comes_and_goes_and_nothing_else_moves(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    since = NOW - timedelta(seconds=20)
    try:
        bare = await _plant(db_engine, None)
        kept = await _plant(db_engine, {"status": "refused:x", "order_id": "o-9"})
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            assert await set_stop_episode(session, bare, since=since, now=NOW) is True
            assert await set_stop_episode(session, kept, since=since, now=NOW) is True
        assert await _intent(db_engine, bare) == {STOP_EPISODE_KEY: since.isoformat()}
        assert await _intent(db_engine, kept) == {
            "status": "refused:x", "order_id": "o-9", STOP_EPISODE_KEY: since.isoformat(),
        }  # fmt: skip
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            assert await set_stop_episode(session, kept, since=None, now=NOW) is True
        assert await _intent(db_engine, kept) == {"status": "refused:x", "order_id": "o-9"}
    finally:
        await _clean(db_engine)


async def test_no_episode_is_written_while_a_sell_is_in_flight_or_after_the_close(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    try:
        pending = await _plant(db_engine, {"status": "submitted_unconfirmed"})
        closed = await _plant(db_engine, None)
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE spot_positions SET exit_order_id = entry_order_id WHERE id = :id"),
                {"id": pending},
            )
            await conn.execute(
                text(
                    "UPDATE spot_positions SET status = 'closed', exit_at = :x, exit = '{}', "
                    "  pnl_sol = 0, r_multiple = 0 WHERE id = :id"
                ),
                {"id": closed, "x": NOW},
            )
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            assert await set_stop_episode(session, pending, since=NOW, now=NOW) is False
            assert await set_stop_episode(session, closed, since=NOW, now=NOW) is False
        assert await _intent(db_engine, pending) == {"status": "submitted_unconfirmed"}
    finally:
        await _clean(db_engine)


async def test_a_sell_in_flight_and_its_failure_keep_the_episode(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Astra, diff review: a forced stop whose sell fails must not open a fresh 60 s."""
    since = (NOW - timedelta(seconds=90)).isoformat()
    try:
        pid = await _plant(db_engine, {STOP_EPISODE_KEY: since})
        bare = await _plant(db_engine, None)
        async with db_engine.connect() as conn:
            sql = text("SELECT entry_order_id FROM spot_positions WHERE id = :id")
            order = str((await conn.execute(sql, {"id": pid})).scalar())
            bare_order = str((await conn.execute(sql, {"id": bare})).scalar())
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            assert await set_exit_pending(
                session, pid, order_id=order, reason="stop", attempt=1, now=NOW
            )
            assert await set_exit_pending(
                session, bare, order_id=bare_order, reason="time", attempt=1, now=NOW
            )
        pending = await _intent(db_engine, pid)
        assert pending["status"] == "submitted_unconfirmed" and pending[STOP_EPISODE_KEY] == since
        assert STOP_EPISODE_KEY not in await _intent(db_engine, bare), "no null key invented"
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            assert await clear_exit_pending(
                session, pid, order_id=order, outcome="refused:swap_build_failed:X", now=NOW
            )
        cleared = await _intent(db_engine, pid)
        assert cleared["status"] == "refused:swap_build_failed:X"
        assert cleared[STOP_EPISODE_KEY] == since
    finally:
        await _clean(db_engine)
