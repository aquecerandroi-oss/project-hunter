"""T4.8f, Postgres half of ``test_exit_decode_failure_t48f.py`` — the curve venue through the
real ``exits_once`` and real rows (``meme_live_orders`` / ``meme_live_positions``).

send -> the transaction lands, its TradeEvent cannot be read (``fill_decode_failed``) -> a
restarted executor reconciles by signature and sends nothing -> with the decoder healthy the
position closes once -> the orphan repair and another tick change nothing.

**NOT RUN when written (05/10/2026): Docker was not reachable.** Run with Docker up:
``uv run --no-sync pytest services/meme-executor/tests/test_exit_decode_failure_integration_t48f.py``.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.exit_settle import repair_confirmed_sells
from hunter_meme_executor.exits import exits_once

from .test_fills_t48e import _append_to_event_cpi
from .test_live_persistence import (  # noqa: F401  (``harness`` is a fixture)
    Harness,
    _context,
    _fixture,
    _plant_proposal,
    _rows,
    _signer,
    harness,  # pyright: ignore[reportUnusedImport]
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_an_exit_whose_fill_cannot_be_read_closes_once_when_the_decoder_returns(
    harness: Harness,  # noqa: F811
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET sell_requested_at = now(), "
                "sell_requested_by = 'everton' WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    good: dict[str, Any] = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    bad = copy.deepcopy(good)
    _append_to_event_cpi(bad, b"\x00" * 7, program=None)

    # 1. the send lands; the fill is unreadable
    first = _context(db_session_factory, _signer(), harness.redis)
    first.chain.tokens_on_chain = 10**9
    first.rpc.transaction = bad
    await exits_once(first.ctx)
    sells = await _rows(
        db_engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell'",
        p=proposal_id,
    )
    assert len(sells) == 1 and sells[0]["status"] == "submitted_unconfirmed", sells
    assert "fill_decode_failed" in str(sells[0]["reason"])
    assert len(first.rpc.sent) == 1

    # 2. restart with the decoder still incompatible: pending, nothing re-sent, still open
    second = _context(db_session_factory, _signer(), harness.redis)
    second.chain.tokens_on_chain = 10**9
    second.rpc.transaction = bad
    await exits_once(second.ctx)
    await exits_once(second.ctx)
    assert len(second.rpc.sent) == 0
    position = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert position[0]["status"] == "open"
    assert len(await _rows(db_engine, "SELECT id FROM meme_live_orders WHERE side = 'sell'")) == 1

    # 3. the decoder is back: one close
    third = _context(db_session_factory, _signer(), harness.redis)
    third.chain.tokens_on_chain = 10**9
    third.rpc.transaction = good
    await exits_once(third.ctx)
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert closed[0]["status"] == "closed" and closed[0]["pnl_sol"] is not None
    assert third.ctx.state.exits_confirmed == 1 and len(third.rpc.sent) == 0
    pnl = closed[0]["pnl_sol"]

    # 4. nothing closes it twice
    await repair_confirmed_sells(third.ctx)
    await exits_once(third.ctx)
    again = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert again[0]["pnl_sol"] == pnl and third.ctx.state.exits_confirmed == 1
    assert len(third.rpc.sent) == 0
    orders = await _rows(
        db_engine,
        "SELECT status FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell'",
        p=proposal_id,
    )
    assert [o["status"] for o in orders] == ["confirmed"]
