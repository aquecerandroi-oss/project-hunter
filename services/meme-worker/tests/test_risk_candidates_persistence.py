"""``pending_operator_mints`` against a real Postgres at ``head`` (T4.28g).

The unit file beside this one pins the statuses and the bounds of the SQL; this
one proves the selection itself, because the bug it closes was a ``WHERE`` clause
that matched nothing: an operator proposal the stage-1 executor had already moved
to ``approved`` stopped being a candidate for the rug-risk read, so the read landed
a median 103 s after the decision it existed for (R5, 16/09/2026).

Skips without Docker, like every Postgres-backed test here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.repo_tape import PENDING_LOOKBACK_S, pending_operator_mints

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
NOW = datetime(2026, 10, 5, 12, 10, 30, tzinfo=UTC)
SEED_OPERATOR = "01994d00-6c1a-7000-8000-000000000002"


async def _operator_set(engine: AsyncEngine) -> str:
    """This test's own ``operator`` set, copying the seed's params (owner write)."""
    rule_set_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, status, params, code_ref) "
                "SELECT :id, :name, '1', 'operator', 'active', params, code_ref "
                "FROM meme_rule_sets WHERE id = :seed"
            ),
            {"id": rule_set_id, "name": f"operator-{rule_set_id[:8]}", "seed": SEED_OPERATOR},
        )
    return rule_set_id


async def _proposal(
    engine: AsyncEngine,
    rule_set_id: str,
    *,
    mint: str,
    status: str,
    proposed_at: datetime,
    ttl_s: int = 180,
) -> str:
    proposal_id = str(uuid4())
    decided = status not in ("proposed", "expired")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "  expires_at, mode, decided_at, decided_by, decision) "
                "VALUES (:id, :mint, :rule_set_id, 'operator', :status, :proposed_at, "
                "  :expires_at, :mode, :decided_at, :decided_by, CAST(:decision AS jsonb))"
            ),
            {
                "id": proposal_id,
                "mint": mint,
                "rule_set_id": rule_set_id,
                "status": status,
                "proposed_at": proposed_at,
                "expires_at": proposed_at + timedelta(seconds=ttl_s),
                "mode": "live" if decided else "paper",
                "decided_at": proposed_at if decided else None,
                "decided_by": "executor:auto_stage1" if decided else None,
                "decision": json.dumps({"size_sol": "0.05"}) if decided else None,
            },
        )
    return proposal_id


async def _buy_order(
    engine: AsyncEngine, proposal_id: str, *, status: str, received_at: datetime
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, attempt, "
                "  intent, admission, status, reason, received_at, updated_at) "
                "VALUES (:id, :proposal_id, 'buy', :key, 1, '{}'::jsonb, '{}'::jsonb, :status, "
                "  :reason, :received_at, :received_at)"
            ),
            {
                "id": str(uuid4()),
                "proposal_id": proposal_id,
                "key": f"meme:{proposal_id}",
                "status": status,
                "reason": "test" if status in ("refused", "failed") else None,
                "received_at": received_at,
            },
        )


async def _candidates(factory: async_sessionmaker[AsyncSession]) -> frozenset[str]:
    async with role_session(factory, db_role=WORKER) as session:
        return await pending_operator_mints(session, now=NOW)


@pytest.mark.asyncio
async def test_a_proposal_the_executor_already_opened_is_still_a_candidate(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The measured regression, end to end: the desk files the row, the robot
    approves it 6 s later, and the reader's next tick must still ask
    ``/in-memory-coin`` about that mint. Before T4.28g it did not, and the
    admission refused ``bundled_share_unmeasurable`` 103 s before the answer."""
    rule_set_id = await _operator_set(db_engine)
    await _proposal(
        db_engine,
        rule_set_id,
        mint="APPROVEDpump",
        status="approved",
        proposed_at=NOW - timedelta(seconds=6),
    )
    assert "APPROVEDpump" in await _candidates(db_session_factory)


@pytest.mark.asyncio
async def test_a_fresh_proposal_awaiting_a_decision_is_still_covered(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.28b's own case must not regress."""
    rule_set_id = await _operator_set(db_engine)
    await _proposal(
        db_engine,
        rule_set_id,
        mint="PROPOSEDpump",
        status="proposed",
        proposed_at=NOW - timedelta(seconds=3),
    )
    assert "PROPOSEDpump" in await _candidates(db_session_factory)


@pytest.mark.asyncio
async def test_an_expired_proposal_awaiting_a_click_is_not_read(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A ``proposed`` row past ``expires_at`` can no longer be approved
    (``proposal_state_refusal``), so spending the undocumented read on it is
    budget taken from a coin that can still be bought."""
    rule_set_id = await _operator_set(db_engine)
    await _proposal(
        db_engine,
        rule_set_id,
        mint="EXPIREDpump",
        status="proposed",
        proposed_at=NOW - timedelta(seconds=300),
    )
    assert "EXPIREDpump" not in await _candidates(db_session_factory)


@pytest.mark.asyncio
async def test_a_rejected_proposal_is_not_a_candidate(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """No decision is pending on it; the mint comes back only when the desk
    proposes it again."""
    rule_set_id = await _operator_set(db_engine)
    await _proposal(
        db_engine,
        rule_set_id,
        mint="REJECTEDpump",
        status="rejected",
        proposed_at=NOW - timedelta(seconds=30),
    )
    assert "REJECTEDpump" not in await _candidates(db_session_factory)


@pytest.mark.asyncio
async def test_a_mint_with_a_buy_in_flight_is_covered_until_it_settles(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Money in flight: the proposal is already ``filled``/``unfilled`` in shadow,
    but the order has not settled, and the exit side needs the rug numbers."""
    rule_set_id = await _operator_set(db_engine)
    in_flight = await _proposal(
        db_engine,
        rule_set_id,
        mint="INFLIGHTpump",
        status="rejected",
        proposed_at=NOW - timedelta(seconds=400),
    )
    await _buy_order(
        db_engine, in_flight, status="admitted", received_at=NOW - timedelta(seconds=20)
    )
    assert "INFLIGHTpump" in await _candidates(db_session_factory)


@pytest.mark.asyncio
async def test_a_settled_order_stops_being_a_candidate(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    rule_set_id = await _operator_set(db_engine)
    settled = await _proposal(
        db_engine,
        rule_set_id,
        mint="SETTLEDpump",
        status="rejected",
        proposed_at=NOW - timedelta(seconds=400),
    )
    await _buy_order(db_engine, settled, status="refused", received_at=NOW - timedelta(seconds=20))
    assert "SETTLEDpump" not in await _candidates(db_session_factory)


@pytest.mark.asyncio
async def test_the_ten_minute_window_bounds_the_scan(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The rule the post-incident review left: a per-tick query cannot grow with
    the table. An ``approved`` row nobody ever admitted stops being read."""
    assert PENDING_LOOKBACK_S == 600
    rule_set_id = await _operator_set(db_engine)
    await _proposal(
        db_engine,
        rule_set_id,
        mint="ANCIENTpump",
        status="approved",
        proposed_at=NOW - timedelta(seconds=PENDING_LOOKBACK_S + 60),
    )
    await _proposal(
        db_engine,
        rule_set_id,
        mint="RECENTpump",
        status="approved",
        proposed_at=NOW - timedelta(seconds=PENDING_LOOKBACK_S - 60),
    )
    mints = await _candidates(db_session_factory)
    assert "RECENTpump" in mints
    assert "ANCIENTpump" not in mints
