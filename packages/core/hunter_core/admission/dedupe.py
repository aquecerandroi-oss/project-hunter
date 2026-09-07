"""Replay of an admission request — the same answer, never a second decision.

``trade_proposals`` is unique on ``(organization_id, idempotency_key)``, and that
key is minted from the origin plus the caller's own client key
(:func:`hunter_core.admission.sources.admission_key`). A retry therefore finds
the row the first attempt wrote and gets *its* decision back: the same proposal
id, the same place in the FIFO queue, the same reservation — no second
evaluation, no second reservation, no second event (M3 joint decision, item 8:
"retry da mesma solicitação recupera identidade e resultado, sem nova posição na
fila").

**A reused key with a different request is a conflict, not a replay.** Answering
"buy SOL on wallet A" with the decision taken for "buy BTC on wallet B" because
the client reused a header would be the worst possible silence. Four columns
answer that — wallet, market, direction and origin — and the *geometry* is
compared against the stored decision itself: an approval always carries its
``sizing``, and ``sizing`` carries the ``entry_ref``, the ``stop`` and the
ceiling the caller asked for. So the dangerous case (a key reused with a
different price, a different stop or a smaller ceiling being answered with the
earlier, larger approval) is closed with what is already persisted.

**What is still open, declared rather than hidden:** a *rejected* proposal has
no ``sizing``, so a replay of a rejection only compares the four columns. It
commits nothing, which is why it is the tolerable half — and
``.claude/state/notes-T3.12.md`` §5 carries the request for a
``request_digest`` column that would close it outright.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hunter_core.db.repositories.base import TenantRepository
from hunter_core.domain.enums import (
    ProposalSource,
    ProposalStatus,
    ReservationState,
    TradeDirection,
)
from hunter_risk.decision import RiskDecision

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.admission.sources import ProposalRequest

__all__ = ["AdmittedProposal", "IdempotencyConflict", "find_admitted"]


class IdempotencyConflict(ValueError):
    """The key was already used for a **different** request."""


class AdmittedProposal(BaseModel):
    """The stored proposal, as a replay needs to read it back."""

    model_config = ConfigDict(frozen=True)

    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    source: ProposalSource
    status: ProposalStatus
    admission_seq: int | None
    reservation_state: ReservationState
    reserved_notional: Decimal | None
    reserved_cash: Decimal | None
    reserved_risk: Decimal | None
    reserved_until: datetime | None
    decided_at: datetime | None
    risk_decision: dict[str, Any]

    @property
    def decision(self) -> RiskDecision:
        """The decision exactly as it was taken, read back from JSONB.

        Validated rather than trusted: a row whose ``risk_decision`` cannot be
        parsed is not a decision this service may repeat, and failing loudly is
        the only honest answer to "what did we decide last time".
        """
        return RiskDecision.model_validate(self.risk_decision)


class ProposalLookup(TenantRepository):
    """The read half of ``trade_proposals``, scoped to one organization."""

    async def by_idempotency_key(self, key: str) -> AdmittedProposal | None:
        statement = text(
            "SELECT id AS proposal_id, portfolio_id, market_id, direction::text AS direction, "
            "source::text AS source, status::text AS status, admission_seq, "
            "reservation_state::text AS reservation_state, reserved_notional, reserved_cash, "
            "reserved_risk, reserved_until, decided_at, risk_decision FROM trade_proposals "
            "WHERE organization_id = :org AND idempotency_key = :key"
        )
        row = (
            await self.session.execute(statement, {"org": self.organization_id, "key": key})
        ).one_or_none()
        return None if row is None else AdmittedProposal.model_validate(row, from_attributes=True)


async def find_admitted(
    session: AsyncSession, *, organization_id: uuid.UUID, idempotency_key: str
) -> AdmittedProposal | None:
    """The proposal this key already produced, if any."""
    lookup = ProposalLookup(session, organization_id)
    await lookup.require_tenant_context()
    return await lookup.by_idempotency_key(idempotency_key)


def _differs(stored: Any, asked: Any) -> bool:
    """Whether two stored/requested values disagree.

    Money is compared **numerically**: a decision read back from JSONB carries
    ``100`` where the caller wrote ``100.00``, and refusing a retry over a
    trailing zero would break the very idempotency this exists to provide.
    """
    if isinstance(stored, Decimal) and isinstance(asked, Decimal):
        return stored != asked
    return str(stored) != str(asked)


def _geometry(existing: AdmittedProposal, request: ProposalRequest) -> list[tuple[str, Any, Any]]:
    """The price, the stop and the requested ceiling of the stored **approval**.

    Empty for a decision without ``sizing``: a rejection did not measure a price,
    and inventing a comparison against a number nobody stored would refuse
    legitimate retries.
    """
    sizing = existing.decision.sizing
    if sizing is None:
        return []
    asked = next((cap.notional for cap in sizing.caps if cap.name == "requested"), None)
    return [
        ("entry_ref", sizing.entry_ref, request.entry_ref),
        ("stop", sizing.stop, request.stop),
        ("requested_notional", asked, request.requested_notional),
    ]


def ensure_same_request(
    existing: AdmittedProposal, request: ProposalRequest, source: ProposalSource
) -> None:
    """Refuse a key that names a different order than the one it was minted for."""
    mismatches = [
        f"{name}: stored {stored}, requested {asked}"
        for name, stored, asked in [
            ("portfolio_id", existing.portfolio_id, request.portfolio_id),
            ("market_id", existing.market_id, request.market_id),
            ("direction", existing.direction.value, request.direction.value),
            ("source", existing.source.value, source.value),
            *_geometry(existing, request),
        ]
        if _differs(stored, asked)
    ]
    if mismatches:
        raise IdempotencyConflict(
            f"idempotency key already answered proposal {existing.proposal_id}, which is a "
            "different order: " + "; ".join(mismatches)
        )
