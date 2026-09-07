"""One proposal, one reservation cycle — DATABASE.md §18.3, RISK_ENGINE.md §4.

``trade_proposals`` carries the commitment on a single axis
(``reservation_state``) next to the decision's label (``status``), and the
schema keeps that axis single without keeping it *forward-only*: nothing in the
DDL stops an ``UPDATE`` from moving ``consumed`` back to ``held``. DATABASE.md
§18.3 says so in as many words and hands the invariant to this service — so it
lives in :func:`next_state`, in one place, with a test.

What a reservation holds is three different numbers (§18.3, "três dinheiros"):
``reserved_notional`` for exposure and for the participation budget,
``reserved_cash`` for the cash the purchase actually needs (fees included) and
``reserved_risk`` for the planned loss at the stop. The slot is a fourth,
boolean, commitment, and it only exists while the reservation is standing: a
fill *converts* the reserved slot into the position's, never adds a second.

The tenure is 30 seconds (``PIPELINE.md`` §5: "propostas approved sem ordem após
30 s expiram"). Expiry competes for the same wallet lock as admission, which is
why :func:`expire_reservations` takes a wallet rather than sweeping the table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hunter_core.admission.participation import ParticipationRepository
from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.db.repositories.base import TenantRepository
from hunter_core.domain.enums import ParticipationEntryKind, ReservationState
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.sizing import entry_cash_multiplier

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "RESERVATION_TTL",
    "ReservationCycleClosed",
    "ReservationRepository",
    "ReservationRow",
    "expire_reservations",
    "next_state",
    "reserved_cash_for",
]

logger = get_logger(__name__)

RESERVATION_TTL = timedelta(seconds=30)
"""How long an approved proposal holds the wallet's capital without an order."""

_TERMINAL = (ReservationState.CONSUMED, ReservationState.RELEASED, ReservationState.EXPIRED)
_ZERO = Decimal(0)


class ReservationCycleClosed(RuntimeError):
    """The reservation is not standing, so it cannot be closed (again) or reopened."""


def next_state(current: ReservationState, target: ReservationState) -> ReservationState:
    """The only legal move: ``held`` -> one terminal state, once."""
    if current is ReservationState.HELD and target in _TERMINAL:
        return target
    raise ReservationCycleClosed(
        f"a reservation in {current.value} may not move to {target.value}: a proposal has exactly "
        "one reservation cycle, it only ever closes, and reopening it would hand the wallet's "
        "cash, risk and slot to a commitment that was already given back"
    )


def reserved_cash_for(notional: Decimal, costs: AssumedCosts) -> Decimal:
    """What the purchase holds of the cash: the notional plus its assumed fees.

    The mirror of the engine's cash ceiling (``(1 + deslocamento) x (1 + fee)``),
    computed from the **proposal's own** cost hypothesis and then frozen on the
    row: re-estimating a standing reservation with the next candidate's costs is
    how a candidate declaring no costs shrinks somebody else's commitment
    (RISK_ENGINE.md §4).
    """
    return notional * entry_cash_multiplier(costs)


class ReservationRow(BaseModel):
    """A reservation as the database holds it, with its executed part."""

    model_config = ConfigDict(frozen=True)

    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    reservation_state: ReservationState
    reserved_notional: Decimal | None
    reserved_cash: Decimal | None
    reserved_risk: Decimal | None
    reserved_until: datetime | None
    executed_notional: Decimal
    """Sum of the ``executed`` entries of this proposal's budget log. What a
    terminal cancellation gives back is the notional **minus** this."""


class ReservationRepository(TenantRepository):
    """The reservation half of ``trade_proposals``, scoped to one organization."""

    _SELECT = (
        "SELECT p.id AS proposal_id, p.portfolio_id, p.market_id, "
        "p.reservation_state::text AS reservation_state, p.reserved_notional, p.reserved_cash, "
        "p.reserved_risk, p.reserved_until, coalesce((SELECT sum(c.notional) FROM "
        "participation_consumptions c WHERE c.proposal_id = p.id AND c.kind = 'executed'), 0) "
        "AS executed_notional FROM trade_proposals p WHERE p.organization_id = :org "
    )

    async def lock(self, proposal_id: uuid.UUID) -> ReservationRow | None:
        """The proposal's own row, ``FOR UPDATE``.

        The wallet lock already serialises admission and expiry; this one bounds
        two closers of the *same* proposal arriving from different wallets'
        code paths (a fill and a cancellation), which is a different race.
        """
        rows = await self.session.execute(
            text(f"{self._SELECT} AND p.id = :id FOR UPDATE OF p"),
            {"org": self.organization_id, "id": proposal_id},
        )
        row = rows.one_or_none()
        return None if row is None else ReservationRow.model_validate(row, from_attributes=True)

    async def standing(
        self, *, portfolio_id: uuid.UUID, expired_at: datetime
    ) -> tuple[ReservationRow, ...]:
        """Held reservations of this wallet whose tenure ran out at ``expired_at``."""
        rows = await self.session.execute(
            text(
                f"{self._SELECT} AND p.portfolio_id = :pf AND p.reservation_state = 'held' "
                "AND p.reserved_until <= :now ORDER BY p.admission_seq FOR UPDATE OF p"
            ),
            {"org": self.organization_id, "pf": portfolio_id, "now": ensure_utc(expired_at)},
        )
        return tuple(ReservationRow.model_validate(row, from_attributes=True) for row in rows)

    async def hold(
        self,
        *,
        proposal_id: uuid.UUID,
        notional: Decimal,
        cash: Decimal,
        risk: Decimal,
        until: datetime,
    ) -> None:
        """Put the commitment on the proposal that was just decided.

        Guarded by ``reservation_state = 'none'`` in the predicate rather than by
        a read: a row that already reserved must not reserve twice, and the
        check has to be the write itself.
        """
        reserved = await self.session.scalar(
            text(
                "UPDATE trade_proposals SET reservation_state = 'held', reserved_notional = "
                ":notional, reserved_cash = :cash, reserved_risk = :risk, reserved_slot = true, "
                "reserved_until = :until WHERE id = :id AND organization_id = :org "
                "AND reservation_state = 'none' RETURNING id"
            ),
            {
                "id": proposal_id,
                "org": self.organization_id,
                "notional": notional,
                "cash": cash,
                "risk": risk,
                "until": ensure_utc(until),
            },
        )
        if reserved is None:
            raise ReservationCycleClosed(
                f"proposal {proposal_id} did not move into a reservation: it already carries one, "
                "and one proposal has exactly one cycle"
            )

    async def close(self, row: ReservationRow, target: ReservationState) -> None:
        """Move a standing reservation to its terminal state, keeping the amounts.

        The amounts stay as history (the schema's two implications instead of a
        biconditional) and ``reserved_slot`` goes false, because what counts
        against a limit is decided by the state.
        """
        next_state(row.reservation_state, target)
        await self.session.execute(
            text(
                "UPDATE trade_proposals SET reservation_state = :target, reserved_slot = false "
                "WHERE id = :id AND organization_id = :org AND reservation_state = 'held'"
            ),
            {"id": row.proposal_id, "org": self.organization_id, "target": target.value},
        )


async def close_reservation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    proposal_id: uuid.UUID,
    target: ReservationState,
    now: datetime,
    actor_id: str = "system",
    reason: str = "",
) -> ReservationRow:
    """Close one standing reservation and give back what was not executed.

    Used by the execution path for ``consumed`` (the fill converting the
    reservation) and ``released`` (a terminal cancellation), and by
    :func:`expire_reservations` for ``expired``. The unexecuted part is returned
    to the market's participation budget in the same transaction — cancelling
    frees only what was not executed (RISK_ENGINE.md §4).
    """
    reservations = ReservationRepository(session, organization_id)
    await reservations.require_tenant_context()
    row = await reservations.lock(proposal_id)
    if row is None:
        raise ReservationCycleClosed(
            f"proposal {proposal_id} is not visible to this transaction; there is no reservation "
            "to close"
        )
    await _close_row(
        session,
        row,
        target,
        organization_id=organization_id,
        now=now,
        actor_id=actor_id,
        reason=reason,
    )
    return row


async def _close_row(
    session: AsyncSession,
    row: ReservationRow,
    target: ReservationState,
    *,
    organization_id: uuid.UUID,
    now: datetime,
    actor_id: str,
    reason: str,
) -> None:
    moment = ensure_utc(now)
    reservations = ReservationRepository(session, organization_id)
    await reservations.close(row, target)
    reserved = row.reserved_notional or _ZERO
    unexecuted = max(_ZERO, reserved - row.executed_notional)
    if target is not ReservationState.CONSUMED and unexecuted > _ZERO:
        await ParticipationRepository(session, organization_id).append(
            portfolio_id=row.portfolio_id,
            market_id=row.market_id,
            proposal_id=row.proposal_id,
            kind=ParticipationEntryKind.RELEASED,
            notional=unexecuted,
            occurred_at=moment,
        )
    await SqlAuditSink(session).record(
        AuditEvent(
            actor_type="system" if actor_id == "system" else "user",
            actor_id=actor_id,
            organization_id=organization_id,
            action=f"proposal.reservation_{target.value}",
            entity_type="trade_proposal",
            entity_id=str(row.proposal_id),
            before={"reservation_state": row.reservation_state.value},
            after={"reservation_state": target.value},
            metadata={
                "portfolio_id": str(row.portfolio_id),
                "market_id": str(row.market_id),
                "reserved_notional": str(reserved),
                "executed_notional": str(row.executed_notional),
                "released_notional": str(unexecuted),
                "reserved_until": row.reserved_until.isoformat() if row.reserved_until else None,
                "reason": reason,
            },
            ts=moment,
        )
    )
    logger.info(
        "proposal_reservation_closed",
        proposal_id=str(row.proposal_id),
        portfolio_id=str(row.portfolio_id),
        organization_id=str(organization_id),
        state=target.value,
        released_notional=str(unexecuted),
        reason=reason,
    )


async def expire_reservations(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    now: datetime,
    actor_id: str = "system",
) -> tuple[uuid.UUID, ...]:
    """Expire every reservation of this wallet whose 30 s ran out. Audited.

    **The caller holds the wallet lock**: expiry competes for
    ``portfolio_risk_state`` with admission, and a sweep that ran outside it
    would free a slot the admission next to it has already counted. The
    admission service calls this under its own lock before it builds the state,
    so an entry is never refused by a commitment that has already died.

    ``status`` is deliberately left alone. It is the label of what the Risk
    Engine decided, and the decision does not stop being true when the
    reservation runs out (DATABASE.md §18.3); the tenure is the other axis, and
    it is this one.
    """
    moment = ensure_utc(now)
    reservations = ReservationRepository(session, organization_id)
    await reservations.require_tenant_context()
    rows = await reservations.standing(portfolio_id=portfolio_id, expired_at=moment)
    for row in rows:
        await _close_row(
            session,
            row,
            ReservationState.EXPIRED,
            organization_id=organization_id,
            now=moment,
            actor_id=actor_id,
            reason="reserved_until reached with no order",
        )
    return tuple(row.proposal_id for row in rows)
