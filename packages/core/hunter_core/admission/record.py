"""Writing an admission down: the row, its FIFO place, the reservation, the trail.

Everything in this module runs inside the caller's transaction — the one
:func:`hunter_core.admission.service.admit` opened and that already holds the
wallet's lock. Nothing here commits, and nothing here touches the network: the
event goes to the outbox table, and the dispatcher publishes it afterwards
(ARCHITECTURE.md §5.1), so "decided" and "announced" cannot disagree.

The order the writes happen in is not cosmetic. The proposal row goes first,
inside a savepoint, because it is what the unique idempotency key arbitrates: a
transaction that lost that race must not have advanced the wallet's FIFO
counter, reserved capital or written an audit line for a decision that will
never exist.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hunter_core.admission.participation import ParticipationRepository
from hunter_core.admission.reservation import (
    RESERVATION_TTL,
    ReservationRepository,
    reserved_cash_for,
)
from hunter_core.admission.sources import admission_key
from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.domain.enums import (
    ParticipationEntryKind,
    ProposalSource,
    ProposalStatus,
    ReservationState,
)
from hunter_core.events.outbox_event import event_id_for
from hunter_core.events.outbox_store import enqueue
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.admission.sources import ProposalRequest
    from hunter_core.risk.scopes import EffectiveKillSwitch
    from hunter_risk.decision import RiskDecision

__all__ = [
    "Reservation",
    "insert_proposal",
    "kill_switch_snapshot",
    "next_admission_seq",
    "record_decision",
    "set_admission_seq",
]

logger = get_logger(__name__)

IDEMPOTENCY_CONSTRAINT = "uq_trade_proposals_idem"


class Reservation:
    """The three amounts and the tenure a standing reservation holds."""

    __slots__ = ("cash", "notional", "risk", "until")

    def __init__(self, *, notional: Decimal, cash: Decimal, risk: Decimal, until: datetime) -> None:
        self.notional = notional
        self.cash = cash
        self.risk = risk
        self.until = until


def kill_switch_snapshot(scopes: EffectiveKillSwitch) -> dict[str, Any]:
    """``trade_proposals.kill_switch_snapshot``: the three scopes it decided under."""
    return {
        "system": scopes.system.value,
        "organization": scopes.organization.value,
        "portfolio": scopes.portfolio.value,
        "effective": scopes.effective.value,
        "blocks_entries": scopes.blocks_entries,
    }


async def insert_proposal(
    session: AsyncSession,
    request: ProposalRequest,
    *,
    proposal_id: uuid.UUID,
    source: ProposalSource,
    key: str,
    decision: RiskDecision,
    scopes: EffectiveKillSwitch,
    as_of: datetime,
) -> bool:
    """Write the decision row. ``False`` when another transaction won the key.

    Inside a savepoint, and catching **only** the idempotency constraint: any
    other integrity error is a real fault and has to keep aborting the
    transaction rather than being read as "somebody else already did it".

    ``admission_seq`` is deliberately left null here and set once the row is
    known to exist (:func:`next_admission_seq`): a place in the queue that a
    conflict then rolled back would be a gap the operator cannot explain.
    """
    approved = decision.approved
    params: dict[str, Any] = {
        "id": proposal_id,
        "org": request.organization_id,
        "pf": request.portfolio_id,
        "agent": request.agent_id,
        "signal": request.signal_id,
        "market": request.market_id,
        "direction": request.direction.value,
        "risk_pct": request.requested_risk_pct,
        "status": (ProposalStatus.APPROVED if approved else ProposalStatus.REJECTED).value,
        "decision": json.dumps(decision.to_jsonable()),
        "reason": ", ".join(decision.rejection_reasons) or None,
        "snapshot": json.dumps(kill_switch_snapshot(scopes)),
        "key": key,
        "source": source.value,
        "created": as_of,
        "expires": as_of + RESERVATION_TTL if approved else None,
    }
    statement = text(
        "INSERT INTO trade_proposals (id, organization_id, portfolio_id, agent_id, signal_id, "
        "market_id, direction, requested_risk_pct, status, risk_decision, rejection_reason, "
        "kill_switch_snapshot, idempotency_key, source, created_at, decided_at, expires_at) "
        "VALUES (:id, :org, :pf, :agent, :signal, :market, :direction, :risk_pct, :status, "
        "CAST(:decision AS jsonb), :reason, CAST(:snapshot AS jsonb), :key, :source, :created, "
        ":created, :expires)"
    )
    try:
        async with session.begin_nested():
            await session.execute(statement, params)
    except IntegrityError as exc:
        if IDEMPOTENCY_CONSTRAINT not in str(exc.orig):
            raise
        return False
    return True


async def next_admission_seq(
    session: AsyncSession, *, organization_id: uuid.UUID, portfolio_id: uuid.UUID
) -> int:
    """``fifo_v1``: the wallet's counter, advanced under its own lock.

    Deliberately the counter on ``portfolio_risk_state`` and **not**
    ``max(admission_seq)``: that column is the durable admission order the
    operator is promised (DATABASE.md §18.7), and a derived maximum would leave
    it at zero for ever while claiming to implement it. It is also why this
    write needs a role the trigger of ``portfolio_risk_state`` accepts —
    notes-T3.12.md §2 records that coupling.
    """
    seq = await session.scalar(
        text(
            "UPDATE portfolio_risk_state SET last_admission_seq = last_admission_seq + 1 "
            "WHERE organization_id = :org AND portfolio_id = :pf RETURNING last_admission_seq"
        ),
        {"org": organization_id, "pf": portfolio_id},
    )
    if seq is None:
        raise LookupError(
            f"portfolio {portfolio_id} has no portfolio_risk_state row to take a FIFO place from"
        )
    return int(seq)


async def set_admission_seq(
    session: AsyncSession, *, organization_id: uuid.UUID, proposal_id: uuid.UUID, seq: int
) -> None:
    await session.execute(
        text(
            "UPDATE trade_proposals SET admission_seq = :seq WHERE id = :id "
            "AND organization_id = :org"
        ),
        {"seq": seq, "id": proposal_id, "org": organization_id},
    )


async def hold_reservation(
    session: AsyncSession,
    request: ProposalRequest,
    *,
    proposal_id: uuid.UUID,
    notional: Decimal,
    risk: Decimal,
    as_of: datetime,
) -> Reservation:
    """Commit cash, risk, exposure and the slot for the next 30 seconds."""
    reservation = Reservation(
        notional=notional,
        cash=reserved_cash_for(notional, request.assumed_costs),
        risk=risk,
        until=as_of + RESERVATION_TTL,
    )
    org = request.organization_id
    await ReservationRepository(session, org).hold(
        proposal_id=proposal_id,
        notional=reservation.notional,
        cash=reservation.cash,
        risk=reservation.risk,
        until=reservation.until,
    )
    await ParticipationRepository(session, org).append(
        portfolio_id=request.portfolio_id,
        market_id=request.market_id,
        proposal_id=proposal_id,
        kind=ParticipationEntryKind.RESERVED,
        notional=reservation.notional,
        occurred_at=as_of,
    )
    return reservation


def decision_payload(
    request: ProposalRequest,
    *,
    proposal_id: uuid.UUID,
    source: ProposalSource,
    decision: RiskDecision,
    seq: int,
    reservation: Reservation | None,
    as_of: datetime,
) -> dict[str, Any]:
    """The ``proposals.decided`` event body — facts, never a second decision."""
    sizing = decision.sizing
    return {
        "proposal_id": str(proposal_id),
        "organization_id": str(request.organization_id),
        "portfolio_id": str(request.portfolio_id),
        "market_id": str(request.market_id),
        "source": source.value,
        "status": (ProposalStatus.APPROVED if decision.approved else ProposalStatus.REJECTED).value,
        "approved": decision.approved,
        "admission_seq": seq,
        "binding_constraint": sizing.binding_constraint if sizing is not None else None,
        "qty": str(sizing.qty) if sizing is not None else None,
        "notional": str(reservation.notional) if reservation is not None else None,
        "reserved_cash": str(reservation.cash) if reservation is not None else None,
        "reserved_risk": str(reservation.risk) if reservation is not None else None,
        "reserved_until": reservation.until.isoformat() if reservation is not None else None,
        "rejection_reasons": list(decision.rejection_reasons),
        "effective_kill_switch": decision.effective_kill_switch.value,
        "decided_at": as_of.isoformat(),
    }


async def record_decision(
    session: AsyncSession,
    request: ProposalRequest,
    *,
    proposal_id: uuid.UUID,
    source: ProposalSource,
    decision: RiskDecision,
    seq: int,
    reservation: Reservation | None,
    scopes: EffectiveKillSwitch,
    as_of: datetime,
    unavailable_reasons: tuple[str, ...],
) -> None:
    """Audit row and outbox event, in the transaction that took the decision."""
    payload = decision_payload(
        request,
        proposal_id=proposal_id,
        source=source,
        decision=decision,
        seq=seq,
        reservation=reservation,
        as_of=as_of,
    )
    await SqlAuditSink(session).record(
        AuditEvent(
            actor_type="user" if request.actor_type == "user" else "system",
            actor_id=request.actor_id,
            organization_id=request.organization_id,
            action="proposal.admitted" if decision.approved else "proposal.rejected",
            entity_type="trade_proposal",
            entity_id=str(proposal_id),
            after={**payload, "kill_switch": kill_switch_snapshot(scopes)},
            metadata={
                "idempotency_key": admission_key(source, request.client_key),
                "unavailable": list(unavailable_reasons),
                "checks": {item.name: item.state.value for item in decision.checks},
            },
            ts=as_of,
        )
    )
    await enqueue(
        session,
        Streams.PROPOSALS_DECIDED,
        event_id_for(Streams.PROPOSALS_DECIDED, proposal_id),
        payload,
        producer="hunter_core.admission",
        key=str(request.portfolio_id),
        ts=as_of,
    )
    logger.info(
        "proposal_decided",
        proposal_id=str(proposal_id),
        organization_id=str(request.organization_id),
        portfolio_id=str(request.portfolio_id),
        source=source.value,
        approved=decision.approved,
        admission_seq=seq,
        reservation_state=(
            ReservationState.HELD if reservation is not None else ReservationState.NONE
        ).value,
        binding_constraint=(
            decision.sizing.binding_constraint if decision.sizing is not None else None
        ),
        rejection_reasons=list(decision.rejection_reasons),
    )
