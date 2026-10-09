"""The launch claim can only claim a launch proposal (H-037 R4, finding F3), against a real Postgres.

``launch_repo._CLAIM`` is the one statement besides ``approval.DECIDE_PROPOSAL`` that writes
``meme_proposals.mode = 'live'``, and ``repo.live_candidates`` turns every such row into a real buy.
Before this test the statement was scoped by id only: its safety rested on the caller having taken the
id from ``launch_candidates``. The paper copy lane (``hunter_meme_worker.copy_repo``) writes exactly the
rows that statement accepted — ``origin = 'rules'``, ``mode = 'paper'``, ``approved``/``filled``/
``unfilled`` — so any caller that passed another id would have filed a copy for real money. Here each
claim runs as ``hunter_worker`` (the executor's role) and is rolled back: a regression never leaves a
``live`` row behind for another test to buy. The rows are labeled test fixtures in the copy lane's shape.
"""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_executor.launch_config import LAUNCH_RULE_SET_NAME, LAUNCH_SERIES
from hunter_meme_executor.launch_repo import claim_launch_proposal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
WORKER = "hunter_worker"

_RULE_SET = text(
    "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status, "
    "  retired_at) "
    "VALUES (:id, :name, :version, 'research_only', CAST(:params AS jsonb), "
    "  'tests/test_launch_claim_scope_integration', :exp, :status, :retired_at)"
)
_MODE = text("SELECT mode FROM meme_proposals WHERE id = :id")
_PROPOSAL = text(
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
    "  features_end_time, reasons, decision, decided_by, decided_at) "
    "VALUES (:id, :mint, :rs, 'rules', 'approved', :at, :expires, :at, CAST(:reasons AS jsonb), "
    "  CAST('{}' AS jsonb), :by, :at)"
)
_BET = text(
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, entry_at, entry, "
    "  initial_risk_sol, params) "
    "VALUES (:id, :proposal, :rs, :mint, :at, CAST('{}' AS jsonb), 0.05, CAST('{}' AS jsonb))"
)
_FILLED = text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id")
_UNFILLED = text(
    "UPDATE meme_proposals SET status = 'unfilled', refusal = 'sem_estado' WHERE id = :id"
)


class _RollbackError(Exception):
    """Raised inside the session so ``role_session``'s transaction rolls back."""


async def _rule_set(
    engine: AsyncEngine,
    *,
    name: str,
    params: dict[str, object],
    exp: str,
    retired: bool = False,
) -> str:
    rule_set_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            _RULE_SET,
            {
                "id": rule_set_id,
                "name": name,
                "version": f"t{uuid4().hex[:10]}",
                "params": json.dumps(params),
                "exp": exp,
                "status": "retired" if retired else "active",
                "retired_at": NOW if retired else None,
            },
        )
    return rule_set_id


async def _proposal(
    engine: AsyncEngine, rule_set_id: str, *, status: str, reasons: list[dict[str, object]], by: str
) -> str:
    proposal_id, mint = str(uuid4()), f"Mint{uuid4().hex}"
    async with engine.begin() as connection:
        await connection.execute(
            _PROPOSAL,
            {
                "id": proposal_id,
                "mint": mint,
                "rs": rule_set_id,
                "at": NOW,
                "expires": NOW + timedelta(hours=1),
                "reasons": json.dumps(reasons),
                "by": by,
            },
        )
        if status == "filled":
            bet_id = str(uuid4())
            await connection.execute(
                _BET,
                {"id": bet_id, "proposal": proposal_id, "rs": rule_set_id, "mint": mint, "at": NOW},
            )
            await connection.execute(_FILLED, {"id": proposal_id, "bet": bet_id})
        elif status == "unfilled":
            await connection.execute(_UNFILLED, {"id": proposal_id})
    return proposal_id


async def _claim(factory: async_sessionmaker[AsyncSession], proposal_id: str) -> tuple[bool, str]:
    """What the claim returns and the mode it leaves, read in its own transaction, then rolled back —
    and the rollback proven from outside: a fresh session reads ``paper`` again."""
    seen: tuple[bool, str] | None = None
    with suppress(_RollbackError):
        async with role_session(factory, db_role=WORKER) as session:
            claimed = await claim_launch_proposal(session, proposal_id, now=NOW)
            seen = (claimed, str(await session.scalar(_MODE, {"id": proposal_id})))
            raise _RollbackError
    async with role_session(factory, db_role=WORKER) as session:
        assert await session.scalar(_MODE, {"id": proposal_id}) == "paper"
    assert seen is not None
    return seen


def _launch_reasons() -> list[dict[str, object]]:
    """T4.67a's label, the one ``LaunchCandidate.is_launch`` reads."""
    return [{"rule": "launch_v0/1", "series": LAUNCH_SERIES}]


def _copy_reasons() -> list[dict[str, object]]:
    """``copy_repo._draft``'s shape: no ``series`` label."""
    return [{"rule": "copy_leader_first_observation", "stratum": "regra", "slot": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["approved", "filled", "unfilled"])
async def test_the_launch_claim_never_claims_a_paper_copy_proposal(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession], status: str
) -> None:
    copy_set = await _rule_set(db_engine, name="copy_v0", params={"clock": "copy"}, exp="EXP-M28")
    proposal_id = await _proposal(
        db_engine, copy_set, status=status, reasons=_copy_reasons(), by="rules:copy"
    )
    assert await _claim(db_session_factory, proposal_id) == (False, "paper")


@pytest.mark.asyncio
async def test_a_launch_set_row_without_the_lane_label_is_not_claimed(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """``LaunchCandidate.is_launch``'s rule, now in the statement too: the set's name alone is not enough."""
    launch_set = await _rule_set(
        db_engine, name=LAUNCH_RULE_SET_NAME, params={"clock": "event"}, exp="EXP-M18"
    )
    proposal_id = await _proposal(
        db_engine, launch_set, status="approved", reasons=[{"rule": "launch_v0/1"}], by="rules"
    )
    assert await _claim(db_session_factory, proposal_id) == (False, "paper")


@pytest.mark.asyncio
async def test_the_lane_label_on_another_set_is_not_enough(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The name guard alone: a copy row that carried the launch series would still not be claimed."""
    copy_set = await _rule_set(db_engine, name="copy_v0", params={"clock": "copy"}, exp="EXP-M28")
    proposal_id = await _proposal(
        db_engine, copy_set, status="approved", reasons=_launch_reasons(), by="rules:copy"
    )
    assert await _claim(db_session_factory, proposal_id) == (False, "paper")


@pytest.mark.asyncio
async def test_a_proposal_of_a_retired_launch_set_is_not_claimed(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The ``active`` guard alone, as ``_CANDIDATES`` has it: a set retired between the read and the
    claim loses the claim (the caller counts ``claim_lost_total`` and writes no order)."""
    retired_set = await _rule_set(
        db_engine, name=LAUNCH_RULE_SET_NAME, params={"clock": "event"}, exp="EXP-M18", retired=True
    )
    proposal_id = await _proposal(
        db_engine, retired_set, status="approved", reasons=_launch_reasons(), by="rules"
    )
    assert await _claim(db_session_factory, proposal_id) == (False, "paper")


@pytest.mark.asyncio
async def test_a_labeled_launch_proposal_is_still_claimed(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The control: scoping the statement must not stop the launch lane it exists for."""
    launch_set = await _rule_set(
        db_engine, name=LAUNCH_RULE_SET_NAME, params={"clock": "event"}, exp="EXP-M18"
    )
    proposal_id = await _proposal(
        db_engine, launch_set, status="approved", reasons=_launch_reasons(), by="rules"
    )
    assert await _claim(db_session_factory, proposal_id) == (True, "live")
