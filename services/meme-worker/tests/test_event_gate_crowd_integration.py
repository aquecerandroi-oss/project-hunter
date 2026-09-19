"""T4.66 (EXP-M19) against a real Postgres (testcontainers): the seeded
``flow_v2/10`` (``0054``), parsed by ``load_active_rule_sets`` exactly as the
worker parses it, refuses an event-lane row whose early wallets kept 40 % of
what they bought (``early_retention_below_min``) and lets one through whose
early wallets kept 90 % — while its control, ``flow_v2/6``, lets both through.
Run alone (``timeout 590``): shares the container fixture of ``conftest.py``.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from hunter_core.db.session import role_session
from hunter_indicators.meme.crowd import CrowdTrade
from hunter_indicators.meme.rules import evaluate_entry
from hunter_meme_worker.event_gate_rows import EventReserves, build_event_row
from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.proposals import entry_features_of
from hunter_meme_worker.proposals_row import GateRow

from .test_event_gate_integration import (
    CREATED,
    INITIAL_REAL_TOKEN,
    WORKER,
    _holders_pair,
    _lab,
    _prime_state,
    _radar,
    _rt,
    _seed_caches,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.lab_models import RuleSetSpec

pytestmark = pytest.mark.integration


async def _seeded(factory: async_sessionmaker[AsyncSession], label: str) -> RuleSetSpec:
    async with role_session(factory, db_role=WORKER) as session:
        specs = [s for s in await load_active_rule_sets(session) if s.label == label]
    assert len(specs) == 1, f"{label} is seeded once by the migrations"
    return specs[0]


def _crowd(state: MintEventState, *, as_of: datetime, sold_each: str) -> None:
    """Ten early wallets bought 100 each 89 s ago; each sold ``sold_each`` 10 s
    ago (retention = 1 − sold/100); six new wallets bought in the last 30 s."""
    born = state.covered_since
    state.crowd.creator = state.creator
    for i in range(10):
        at = born + timedelta(seconds=1, milliseconds=100 * i)
        state.crowd.push(CrowdTrade(at, at, f"EARLY_{state.mint}_{i}", "buy", Decimal(100)))
    late = as_of - timedelta(seconds=10)
    for i in range(10):
        state.crowd.push(
            CrowdTrade(late, late, f"EARLY_{state.mint}_{i}", "sell", Decimal(sold_each))
        )
    for i in range(6):
        at = as_of - timedelta(seconds=5 - i * 0.5)
        state.crowd.push(CrowdTrade(at, at, f"NEW_{state.mint}_{i}", "buy", Decimal(50)))


async def test_flow_v2_10_refuses_forty_percent_retention_and_passes_ninety(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    arm = await _seeded(db_session_factory, "flow_v2/10")
    control = await _seeded(db_session_factory, "flow_v2/6")
    assert arm.gate.min_early_retention_pct == Decimal("0.70")
    assert arm.gate.min_early_age_s == 60
    assert arm.gate.min_new_wallets_30s == 5
    assert arm.gate.max_quick_flip_share_30s == Decimal("0.20")
    assert control.gate.min_early_retention_pct is None
    outcomes: dict[str, tuple[str, ...]] = {}
    for label, sold_each in (("kept_40", "60"), ("kept_90", "10")):
        mint = f"CRW_{uuid4().hex[:12]}"
        lab = _lab(db_session_factory)
        await _seed_caches(db_session_factory, db_engine, mint, lab=lab)
        rt = _rt(_radar(db_session_factory), lab)
        as_of = CREATED + timedelta(seconds=130)
        _prime_state(rt, mint, as_of=as_of)
        state = rt.book.get(mint)
        assert state is not None and state.covered_from_birth
        _crowd(state, as_of=as_of, sold_each=sold_each)
        assert lab.caches is not None
        base = lab.caches.base_rows[mint]
        row: GateRow = build_event_row(
            base,
            state,
            as_of=as_of,
            reserves=EventReserves(Decimal("60"), INITIAL_REAL_TOKEN * Decimal("1.10")),
            holders_readings=_holders_pair(as_of, snipers=30),
        )
        # flow_v2/6 wants min_holders = 20 and snipers in [21, 1000]: the pair above
        # says 9 → 12 holders, so lift the newest reading as the boards would.
        row = replace(row, holders=25, holders_prev=22, holders_rising=True)
        assert row.new_wallets_30s == 6 and row.quick_flip_share_30s == Decimal(0)
        assert row.early_age_s is not None and row.early_age_s >= 60
        arm_decision = evaluate_entry(entry_features_of(row, arm), arm.gate)
        control_decision = evaluate_entry(entry_features_of(row, control), control.gate)
        assert control_decision.allowed, (label, control_decision.refusals)
        outcomes[label] = arm_decision.refusals
    assert outcomes == {"kept_40": ("early_retention_below_min",), "kept_90": ()}
