"""Moving the kill switch is a write with an explanation attached.

DATABASE.md §18.7 makes that a schema fact: ``portfolios_kill_switch_is_audited``
is a constraint trigger, deferred to COMMIT, that refuses any change of
``portfolios.kill_switch_state`` without a matching ``kill_switch_transitions``
row in the same transaction. This module is the single application path that
writes both, so the two can never be written apart.

Three properties it is built to have:

- **It takes the wallet lock itself.** ``portfolio_risk_state`` is *the*
  serialisation point for a wallet (DATABASE.md §18.7), and a move written
  without holding it races the transaction that is applying an entry effect
  under it: the entry reads ACTIVE, this commits TRADING_DISABLED on another
  row, and the fill lands after the block because the two never contended
  (Astra, review of this diff). Re-taking a lock the caller already holds is a
  no-op, so callers do not have to know.
- **The ``UPDATE`` is conditional on the state that was read.** ``WHERE
  kill_switch_state = :from`` with ``rowcount == 1`` asserted: two evaluations
  racing on the same wallet produce one transition, and the loser raises rather
  than appending a second row describing a move that already happened.
- **The transition is inserted before the ``UPDATE``.** The trigger is deferred,
  so either order works today; inserting first also works if a caller ever makes
  the constraint immediate (Astra, T3.6 review).
- **``evidence`` carries the numbers, not prose.** ``reason`` is for a human;
  ``evidence`` is what makes the row auditable — the daily loss, the drawdown,
  the equity, the peak, the trading day and the thresholds in force.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import desc, insert, select, update

from hunter_core.db.models.identity import Organization
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.db.models.risk import KillSwitchTransition, RiskEvent
from hunter_core.domain.enums import (
    KillSwitchScope,
    KillSwitchState,
    RiskEventSeverity,
    RiskEventType,
)
from hunter_core.domain.types import uuid7
from hunter_core.events.outbox_store import enqueue
from hunter_core.events.streams import Streams
from hunter_risk.kill_switch import blocks_entries

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ACTOR_SYSTEM",
    "ACTOR_USER",
    "ConcurrentTransition",
    "build_evidence",
    "latest_transition",
    "organization_kill_switch",
    "organization_of",
    "record_transition",
    "severity_of",
]

ACTOR_SYSTEM = "system"
ACTOR_USER = "user"
PRODUCER = "risk-engine"


class ConcurrentTransition(RuntimeError):
    """The wallet left the state this transition was computed from.

    Raised instead of writing, so the transaction rolls back together with the
    audit row it had already inserted: a history entry describing a move another
    session already made is worse than no entry (RISK_ENGINE.md §5 — "o registro
    de uma transição que não muda nada é pior no log do que transição nenhuma").
    """


def build_evidence(
    *,
    daily_loss_pct: Decimal | None,
    drawdown_pct: Decimal | None,
    equity: Decimal | None,
    peak_equity: Decimal,
    day_start_equity: Decimal | None,
    trading_day: str | None,
    warning_thresholds: tuple[Decimal, Decimal],
    blocked_thresholds: tuple[Decimal, Decimal],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The numbers that justified a move, as JSON-safe strings.

    ``Decimal`` is rendered as ``str`` and never as ``float``: the whole engine
    refuses ``float`` on construction (RISK_ENGINE.md §8), and evidence that
    silently became ``0.30000000000000004`` would be evidence of nothing.
    """
    evidence: dict[str, Any] = {
        "daily_loss_pct": _num(daily_loss_pct),
        "drawdown_pct": _num(drawdown_pct),
        "equity": _num(equity),
        "peak_equity": _num(peak_equity),
        "day_start_equity": _num(day_start_equity),
        "trading_day": trading_day,
        "trading_day_timezone": "America/Sao_Paulo",
        "warning_daily_loss_pct": _num(warning_thresholds[0]),
        "warning_drawdown_pct": _num(warning_thresholds[1]),
        "blocked_daily_loss_pct": _num(blocked_thresholds[0]),
        "blocked_drawdown_pct": _num(blocked_thresholds[1]),
    }
    if extra:
        evidence.update(extra)
    return evidence


def _num(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def severity_of(to_state: KillSwitchState) -> RiskEventSeverity:
    """``critical`` from ``TRADING_DISABLED`` up — that is who OWNER/ADMIN hears about."""
    if blocks_entries(to_state):
        return RiskEventSeverity.CRITICAL
    if to_state is KillSwitchState.WARNING:
        return RiskEventSeverity.WARNING
    return RiskEventSeverity.INFO


async def record_transition(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    from_state: KillSwitchState,
    to_state: KillSwitchState,
    reason: str,
    evidence: dict[str, Any],
    actor_type: str,
    actor_id: uuid.UUID | None,
    now: datetime,
    publish: bool = False,
) -> uuid.UUID:
    """Write the audited move: history row, then the column the workers read.

    ``publish`` defaults to **False**, and the reason is a grant gap this task
    found and proved (``test_no_role_can_both_move_the_latch_and_publish_the_event``):
    ``hunter_app`` may ``UPDATE portfolios`` but holds ``SELECT`` only on
    ``outbox_events`` (``ddl/analysis.py``, ``ANALYSIS_APP_READ_ONLY_TABLES``),
    while ``hunter_worker`` may write the outbox but holds ``SELECT`` only on
    ``portfolios`` (``ddl/tables.py``, ``WORKER_WRITE_TABLES``). So **no role in
    this schema can move the switch and enqueue ``kill_switch.changed`` in one
    transaction.** The guarantee the contract rests on — workers re-reading the
    effective state every 10 s — is unaffected; the sub-second notification is
    not available until the grants are revised (notes-T3.6, finding 2), and
    passing ``publish=True`` today raises rather than degrading silently.
    """
    # The wallet lock, before anything is written. Imported here because
    # ``scopes`` imports this module for the organization scope.
    from hunter_core.risk.scopes import load_locked_state

    await load_locked_state(session, portfolio_id)
    if from_state is to_state:
        raise ValueError(
            f"kill switch of portfolio {portfolio_id} is already {to_state}: a transition moves, "
            "and the schema CHECK (a_transition_moves) refuses a row that does not"
        )
    transition_id = uuid7()
    await session.execute(
        insert(KillSwitchTransition).values(
            id=transition_id,
            organization_id=organization_id,
            scope=KillSwitchScope.PORTFOLIO,
            scope_id=portfolio_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            actor_type=actor_type,
            actor_id=actor_id,
            evidence=evidence,
            created_at=now,
        )
    )
    # ``session.execute`` is typed ``Result``; only the cursor result carries a
    # row count, and a DML statement always produces one (``outbox_store.prune``).
    moved = cast(
        "CursorResult[Any]",
        await session.execute(
            update(Portfolio)
            .where(
                Portfolio.id == portfolio_id,
                Portfolio.organization_id == organization_id,
                Portfolio.kill_switch_state == from_state,
            )
            .values(kill_switch_state=to_state, kill_switch_reason=reason)
        ),
    )
    if moved.rowcount != 1:
        raise ConcurrentTransition(
            f"portfolio {portfolio_id} is no longer {from_state}: another session moved the "
            "kill switch between this evaluation and its write"
        )
    await session.execute(
        insert(RiskEvent).values(
            id=uuid7(),
            organization_id=organization_id,
            portfolio_id=portfolio_id,
            type=RiskEventType.KILL_SWITCH_CHANGED,
            severity=severity_of(to_state),
            message=f"kill switch {from_state.value} -> {to_state.value}: {reason}",
            data={"from_state": from_state.value, "to_state": to_state.value, **evidence},
            triggered_by=actor_type,
            created_at=now,
        )
    )
    if publish:
        await enqueue(
            session,
            Streams.KILL_SWITCH_CHANGED,
            transition_id,
            {
                "scope": KillSwitchScope.PORTFOLIO.value,
                "scope_id": str(portfolio_id),
                "organization_id": str(organization_id),
                "from_state": from_state.value,
                "to_state": to_state.value,
                "reason": reason,
                "actor_type": actor_type,
                "evidence": evidence,
            },
            producer=PRODUCER,
            key=str(portfolio_id),
            ts=now,
        )
    return transition_id


async def latest_transition(
    session: AsyncSession, portfolio_id: uuid.UUID
) -> KillSwitchTransition | None:
    """The newest portfolio-scoped transition, or ``None`` for a wallet never moved.

    Two different questions read it: what the panel shows, and whether the
    WARNING the wallet sits in was written by a person — a manual WARNING does
    not clear itself at the turn of the day (joint M3 decision §5).
    """
    result = await session.execute(
        select(KillSwitchTransition)
        .where(
            KillSwitchTransition.scope == KillSwitchScope.PORTFOLIO,
            KillSwitchTransition.scope_id == portfolio_id,
        )
        .order_by(desc(KillSwitchTransition.created_at), desc(KillSwitchTransition.id))
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def organization_of(session: AsyncSession, portfolio_id: uuid.UUID) -> uuid.UUID | None:
    """The tenant owning ``portfolio_id`` — ``None`` when RLS hides it or it is gone."""
    return await session.scalar(
        select(Portfolio.organization_id).where(Portfolio.id == portfolio_id)
    )


async def organization_kill_switch(
    session: AsyncSession, organization_id: uuid.UUID, *, lock: bool = False
) -> KillSwitchState:
    """The organization scope's persisted latch (``organizations.kill_switch_state``).

    ``lock=True`` takes ``FOR SHARE`` on the tenant row — the middle rung of the
    contract's fixed acquisition order (system -> organization -> portfolio).
    Shared rather than exclusive: concurrent *readers* of the switch must not
    serialise on each other, while an organization-wide move (an ``UPDATE``,
    which takes the exclusive lock) still waits for every reader holding it.
    """
    statement = select(Organization.kill_switch_state).where(Organization.id == organization_id)
    if lock:
        statement = statement.with_for_update(read=True)
    state = await session.scalar(statement)
    return state if state is not None else KillSwitchState.ACTIVE
