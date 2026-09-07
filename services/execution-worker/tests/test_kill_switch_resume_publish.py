"""T3.5d finding 2 — a user resume the API could not publish reaches the stream.

``apps/api/hunter_api/routers/risk.py`` calls
``hunter_core.risk.resume.resume(..., publish=False)``: the route runs as
``hunter_app``, and ``0007_paper_roles`` denies it ``INSERT`` on
``outbox_events`` by design (SECURITY.md — the API never talks to the
transport directly). The transition is written, audited, and the latch moves,
but nothing is queued.

:func:`hunter_execution_worker.events.publish_resumed_transitions` is the
worker's side of the fix, run every 10 s
(:meth:`hunter_execution_worker.cycles.Cycles.kill_switch`): it enqueues, in
the **core's own shape** (the one
``hunter_core.risk.transitions.record_transition`` already uses for an
automatic move), every ``actor_type='user'`` transition of this wallet that has
no matching outbox row yet.

Nothing here fabricates the transition or the resume's business rules — both
come from the real functions in ``packages/core``, called exactly as the
worker's automatic ladder and the API's route call them. What is engineered is
the *evidence* a resume needs: a synthetic, fully recovered
``PortfolioState`` handed to ``resume(state=...)``, the same parameter a real
caller with a freshly computed state would use — this suite is about the event
reaching the outbox, not about re-proving the resume ladder itself, which
``packages/core/tests/integration/test_risk_kill_switch.py`` already does at
length.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.risk.resume import resume
from hunter_core.risk.transitions import ACTOR_SYSTEM, build_evidence, record_transition
from hunter_execution_worker import events
from hunter_execution_worker.wallet import WalletRef
from hunter_risk import PortfolioState, sao_paulo_day_start_utc

from .builders import NOW, create_tenant, open_wallet

if TYPE_CHECKING:
    import uuid as uuid_module

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WORKER_ROLE = "hunter_worker"
APP_ROLE = "hunter_app"
OPENING = Decimal("20000.0000000000")
RESUME_AT = NOW + timedelta(minutes=1)


class _SimulatedCrash(Exception):
    """Raised to force a transaction to roll back, as a killed process would."""


async def _latch_warning(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid_module.UUID,
    portfolio_id: uuid_module.UUID,
) -> None:
    """A ``system`` transition, ACTIVE -> WARNING — never published, exactly
    like the real automatic ladder before a caller opts into ``publish=True``."""
    async with tenant_session(factory, org_id, db_role=WORKER_ROLE) as session:
        await record_transition(
            session,
            organization_id=org_id,
            portfolio_id=portfolio_id,
            from_state=KillSwitchState.ACTIVE,
            to_state=KillSwitchState.WARNING,
            reason="a -1% day",
            evidence=build_evidence(
                daily_loss_pct=Decimal("0.01"),
                drawdown_pct=Decimal("0.0"),
                equity=Decimal("19800"),
                peak_equity=OPENING,
                day_start_equity=OPENING,
                trading_day=NOW.date().isoformat(),
                warning_thresholds=(Decimal("0.01"), Decimal("0.05")),
                blocked_thresholds=(Decimal("0.02"), Decimal("0.10")),
            ),
            actor_type=ACTOR_SYSTEM,
            actor_id=None,
            now=NOW,
            publish=False,
        )


def _recovered_state(portfolio_id: uuid_module.UUID, *, as_of: object) -> PortfolioState:
    return PortfolioState(
        portfolio_id=portfolio_id,
        as_of=as_of,  # type: ignore[arg-type]
        equity=OPENING,
        cash=OPENING,
        peak_equity=OPENING,
        day_start_equity=OPENING,
        day_start_utc=sao_paulo_day_start_utc(as_of),  # type: ignore[arg-type]
    )


async def _resume_as_the_api_would(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid_module.UUID,
    portfolio_id: uuid_module.UUID,
) -> None:
    """Exactly what ``routers/risk.py::resume_kill_switch`` does: ``hunter_app``,
    ``publish=False``. The wallet is left WARNING -> ACTIVE, ``actor_type='user'``,
    with an empty outbox."""
    async with tenant_session(factory, org_id, db_role=APP_ROLE) as session:
        outcome = await resume(
            session,
            portfolio_id,
            actor_id=uuid.uuid4(),
            reason="reviewed with Everton",
            now=RESUME_AT,
            state=_recovered_state(portfolio_id, as_of=RESUME_AT),
            publish=False,
        )
    assert outcome.to_state is KillSwitchState.ACTIVE


async def _kill_switch_changed_rows(
    engine: AsyncEngine, *, portfolio_id: uuid_module.UUID
) -> list[dict[str, Any]]:
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT payload->>'payload' AS body FROM outbox_events "
                    "WHERE payload->>'key' = :pf AND stream = 'kill_switch.changed'"
                ),
                {"pf": str(portfolio_id)},
            )
        ).all()
    return [json.loads(row.body) for row in rows]


async def _setup(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> tuple[uuid_module.UUID, uuid_module.UUID]:
    tenant = await create_tenant(engine)
    wallet = await open_wallet(factory, engine, tenant)
    await _latch_warning(factory, org_id=tenant.org_id, portfolio_id=wallet.portfolio_id)
    await _resume_as_the_api_would(factory, org_id=tenant.org_id, portfolio_id=wallet.portfolio_id)
    return tenant.org_id, wallet.portfolio_id


async def test_the_first_cycle_publishes_the_unreachable_resume(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    org_id, portfolio_id = await _setup(db_session_factory, db_engine)
    assert await _kill_switch_changed_rows(db_engine, portfolio_id=portfolio_id) == []

    async with tenant_session(db_session_factory, org_id, db_role=WORKER_ROLE) as session:
        published = await events.publish_resumed_transitions(
            session, wallet=WalletRef(org_id, portfolio_id), now=RESUME_AT + timedelta(seconds=1)
        )
    assert published == 1

    rows = await _kill_switch_changed_rows(db_engine, portfolio_id=portfolio_id)
    assert len(rows) == 1
    body = rows[0]
    assert body["scope"] == "portfolio"
    assert body["scope_id"] == str(portfolio_id)
    assert body["organization_id"] == str(org_id)
    assert body["from_state"] == "WARNING"
    assert body["to_state"] == "ACTIVE"
    assert body["actor_type"] == "user"
    assert "evidence" in body


async def test_a_second_cycle_publishes_nothing_more(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    org_id, portfolio_id = await _setup(db_session_factory, db_engine)
    wallet = WalletRef(org_id, portfolio_id)

    async with tenant_session(db_session_factory, org_id, db_role=WORKER_ROLE) as session:
        first = await events.publish_resumed_transitions(
            session, wallet=wallet, now=RESUME_AT + timedelta(seconds=1)
        )
    assert first == 1

    async with tenant_session(db_session_factory, org_id, db_role=WORKER_ROLE) as session:
        second = await events.publish_resumed_transitions(
            session, wallet=wallet, now=RESUME_AT + timedelta(seconds=11)
        )
    assert second == 0

    assert len(await _kill_switch_changed_rows(db_engine, portfolio_id=portfolio_id)) == 1


async def test_a_process_killed_between_the_read_and_the_enqueue_still_leaves_exactly_one(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """A cycle that never commits (the transaction it ran in is rolled back,
    exactly what a ``kill -9`` between the read and the ``enqueue`` leaves
    behind) queues nothing at all — never a half-written row. The next real
    cycle reads the same still-unpublished transition and queues it once."""
    org_id, portfolio_id = await _setup(db_session_factory, db_engine)
    wallet = WalletRef(org_id, portfolio_id)

    with pytest.raises(_SimulatedCrash):
        async with tenant_session(db_session_factory, org_id, db_role=WORKER_ROLE) as session:
            crashed = await events.publish_resumed_transitions(
                session, wallet=wallet, now=RESUME_AT + timedelta(seconds=1)
            )
            assert crashed == 1
            raise _SimulatedCrash

    assert await _kill_switch_changed_rows(db_engine, portfolio_id=portfolio_id) == []

    async with tenant_session(db_session_factory, org_id, db_role=WORKER_ROLE) as session:
        recovered = await events.publish_resumed_transitions(
            session, wallet=wallet, now=RESUME_AT + timedelta(seconds=11)
        )
    assert recovered == 1
    assert len(await _kill_switch_changed_rows(db_engine, portfolio_id=portfolio_id)) == 1
