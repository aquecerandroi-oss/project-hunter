# pyright: reportPrivateUsage=false
"""T4.19 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: the ``0033`` seed parses into ``operator/3``
(15-second clock, ``ttl_s`` 180, the very gate and exclusions of
``flow_v2/1``) with ``operator/2`` gone from the active sets; on one
15-second row the two sets propose the **same coin** in the same tick —
``flow_v2/1`` approved by ``rules``, ``operator/3`` ``proposed`` with
``expires_at − proposed_at = 180 s`` and ``suggested.manual_plan`` persisted
as JSONB; and the operator proposal, once the desk approves it, fills on the
**next 15-second photo** through the same path as every other approval.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.repo import insert_snapshot
from hunter_meme_worker.repo_fast import insert_fast_rows

from .test_lab_fast import CREATED, _fast_row, _plant_token
from .test_lab_persistence import APP, FakeQuotes, Heartbeats, _bet_of, _one, _snapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
OPERATOR_3_ID = "01994d00-6c1a-7000-8000-00000000000a"
PLAN = (
    "Comprar 0,05 SOL de PEPE até 09:05:03 (proposta expira). "
    "Vender até 09:32 (30 min) — antes disso se triplicar (3×), se recuar 35 % do topo depois "
    "de 1,5×, se cair pela metade (−50 %), se o dev vender, ou se a linha de suporte quebrar."
)
"""``CREATED`` is 12:00 UTC = 09:00 BRT; the tick is at +123 s (09:02:03), the
proposal expires 180 s later (09:05:03) and the hold ends 30 min later (09:32)."""
_PROPOSALS_OF = (
    "SELECT p.id, r.name || '/' || r.version AS label, p.status, p.proposed_at, p.expires_at, "
    "       p.features_end_time, p.reasons, p.suggested, p.decision "
    "FROM meme_proposals p JOIN meme_rule_sets r ON r.id = p.rule_set_id "
    "WHERE p.mint = :m AND r.name IN ('flow_v2', 'operator') ORDER BY r.name"
)


@pytest_asyncio.fixture
async def lab(db_session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[LabContext]:
    yield LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )


async def _proposals_of(factory: async_sessionmaker[AsyncSession], mint: str) -> dict[str, Any]:
    async with role_session(factory, db_role=WORKER) as session:
        rows = (await session.execute(text(_PROPOSALS_OF), {"m": mint})).mappings().all()
    return {str(r["label"]): r for r in rows}


async def test_the_seed_hands_the_desk_to_operator_3_on_the_flow_gate(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = {s.label: s for s in await load_active_rule_sets(session)}
    operator, flow = specs["operator/3"], specs["flow_v2/1"]
    assert "operator/2" not in specs and operator.id == OPERATOR_3_ID
    assert operator.kind == "operator" and operator.exp_ref is None
    assert operator.clock == "15s" and operator.ttl_s == 180 and operator.max_open_positions == 2
    assert operator.pedigree_exclusions is flow.pedigree_exclusions is True
    assert replace(operator.gate, description=flow.gate.description) == flow.gate, "the E1 gate"
    assert (operator.size_sol, operator.target_x, operator.trailing_pct) == (
        flow.size_sol,
        flow.target_x,
        flow.trailing_pct,
    )
    assert operator.trailing_arm_x == flow.trailing_arm_x == Decimal("1.5")
    assert (operator.max_hold_s, operator.max_loss_pct) == (1800, Decimal(50))
    assert operator.exit_on_line_break and flow.ttl_s is None
    assert [s.label for s in specs.values() if s.kind == "operator"] == ["operator/3"], (
        "exactly one active operator set"
    )


async def test_operator_3_proposes_the_same_coin_as_flow_v2_waits_180_s_and_fills_once_approved(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = f"OP3_{uuid4().hex[:8]}"
    await _plant_token(
        db_session_factory, mint, created_at=CREATED, creator=f"C_{mint}", symbol="PEPE"
    )
    photo = CREATED + timedelta(seconds=120)
    as_of = photo + timedelta(seconds=2)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(session, [_fast_row(mint, as_of, photo)])
    tick_1 = photo + timedelta(seconds=3)
    report = await lab_tick(lab, now=tick_1)
    assert report.proposals >= 2 and report.fills.filled == 0
    by_set = await _proposals_of(db_session_factory, mint)
    research, proposal = by_set["flow_v2/1"], by_set["operator/3"]
    # The same coin, the same instant, the same decomposition — one approved by
    # rules, the other waiting for the desk 180 s (the set's ttl_s, not the loop's).
    assert research["status"] == "approved" and proposal["status"] == "proposed"
    assert proposal["features_end_time"] == research["features_end_time"] == as_of
    assert (
        proposal["reasons"][0]
        == research["reasons"][0]
        == {
            "rule": "fluxo_e_holders/1",
            "series": "meme_features_15s_v1",
        }
    )
    assert proposal["proposed_at"] == research["proposed_at"] == tick_1
    assert proposal["expires_at"] - proposal["proposed_at"] == timedelta(seconds=180)
    assert research["expires_at"] - research["proposed_at"] == timedelta(
        seconds=lab.config.lab_proposal_ttl_s
    )
    assert proposal["decision"] is None
    assert proposal["suggested"]["manual_plan"] == PLAN, "persisted as the loop wrote it"
    assert "manual_plan" not in research["suggested"]
    # The desk approves (what ``POST /proposals/{id}/approve`` writes), and the
    # next 15-second photo — observed after the decision — fills it.
    decided_at = tick_1 + timedelta(seconds=10)
    decision = {"size_sol": "0.05", "target_x": "3", "trailing_pct": "35", "max_hold_s": 1800}
    async with role_session(db_session_factory, db_role=APP) as session:
        await session.execute(
            text(
                "UPDATE meme_proposals SET status = 'approved', decision = CAST(:d AS jsonb), "
                "decided_by = 'user_test', decided_at = :at WHERE id = :id"
            ),
            {"d": json.dumps(decision), "at": decided_at, "id": proposal["id"]},
        )
    next_photo = photo + timedelta(seconds=15)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, next_photo, "35", "930000000"))
    report = await lab_tick(lab, now=tick_1 + timedelta(seconds=15))
    assert report.fills.filled >= 1
    bet = await _bet_of(db_session_factory, str(proposal["id"]))
    assert bet["proposal_status"] == "filled" and bet["status"] == "open"
    assert bet["entry_at"] == next_photo and bet["entry"]["decision_to_fill_s"] == 2
    assert str(bet["rule_set_id"]) == OPERATOR_3_ID
    assert (bet["params"]["target_x"], bet["params"]["max_hold_s"]) == ("3", 1800)
    assert bet["params"]["trailing_arm_x"] == "1.5" and bet["params"]["exit_on_line_break"]
    still_one = await _one(
        db_session_factory,
        "SELECT count(*) AS n FROM meme_proposals WHERE mint = :m "
        "AND rule_set_id = CAST(:rs AS uuid)",
        m=mint,
        rs=OPERATOR_3_ID,
    )
    assert still_one["n"] == 1, "an open bet keeps the mint from being proposed again"
