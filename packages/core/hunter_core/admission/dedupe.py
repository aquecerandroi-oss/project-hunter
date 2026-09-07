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

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hunter_core.admission.sources import request_digest, request_payload
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

__all__ = [
    "AdmittedProposal",
    "IdempotencyConflict",
    "PendingRequest",
    "find_admitted",
    "find_pending",
]


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
    decided_at: datetime
    """Never null: :func:`find_admitted` only matches rows that were **decided**.
    A row still waiting for the engine has no decision to replay, and
    ``RiskDecision.model_validate({})`` on its empty ``risk_decision`` raised ten
    validation errors instead (adversarial review of 2026-09-07, must-fix 1)."""

    request_digest: str | None
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
            "reserved_risk, reserved_until, decided_at, request_digest, risk_decision "
            "FROM trade_proposals WHERE organization_id = :org AND idempotency_key = :key "
            "AND decided_at IS NOT NULL AND status <> 'pending'"
        )
        row = (
            await self.session.execute(statement, {"org": self.organization_id, "key": key})
        ).one_or_none()
        return None if row is None else AdmittedProposal.model_validate(row, from_attributes=True)


class PendingRequest(BaseModel):
    """A request the API filed and the engine has not decided yet (§19.4)."""

    model_config = ConfigDict(frozen=True)

    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    source: ProposalSource
    request_digest: str | None
    """Null on every row the API filed, since ``0009_paper_geometry``: the guard
    refuses a caller-supplied proof and the engine stamps its own when it decides
    (DATABASE.md §21.2). What a replay of a *pending* row compares instead is
    :attr:`request_payload`, the same information one step earlier."""

    request_payload: dict[str, Any] | None
    """The geometry the API archived (§21.1) — what a pending replay compares."""


async def find_admitted(
    session: AsyncSession, *, organization_id: uuid.UUID, idempotency_key: str
) -> AdmittedProposal | None:
    """The **decided** proposal this key already produced, if any.

    Decided, and only decided. A pending request written by the API carries no
    decision, so answering a replay with it would mean parsing ``{}`` as a
    ``RiskDecision`` — ten validation errors — and, in the role model of
    ``0007_paper_roles`` (the API files, the engine admits), a manual order that
    matched here would never be decided at all: it would replay as itself for
    ever (adversarial review of 2026-09-07, must-fix 1).
    """
    lookup = ProposalLookup(session, organization_id)
    await lookup.require_tenant_context()
    return await lookup.by_idempotency_key(idempotency_key)


async def find_pending(
    session: AsyncSession, *, organization_id: uuid.UUID, idempotency_key: str, lock: bool = True
) -> PendingRequest | None:
    """The undecided request this key filed, if there is one.

    ``lock=True`` (the default) is ``FOR UPDATE``: it is about to be decided
    **in its own row**, and two admissions racing for the same request must not
    both decide it — the shape :func:`~hunter_core.admission.service.admit`
    needs, running as ``hunter_worker``.

    ``lock=False`` is a plain read, for a caller that only compares a retry
    against what is already filed and never decides anything —
    ``apps/api/hunter_api/services/admission.file_manual_order``, running as
    ``hunter_app``. Postgres requires the ``UPDATE`` privilege for ``SELECT
    ... FOR UPDATE`` in addition to ``SELECT`` (not documented as an M3 rule,
    just how the database enforces locking), and ``0007_paper_roles`` revokes
    exactly that from ``hunter_app`` on this table (DATABASE.md §19.4): a
    locked read from the API role fails **permission denied**, not merely
    "no row", which is what a real end-to-end filing surfaced (T3.5c).
    """
    lookup = ProposalLookup(session, organization_id)
    await lookup.require_tenant_context()
    row = (
        await session.execute(
            # S608: the only variable fragment is the literal " FOR UPDATE" below,
            # chosen from a closed set of two constants — never caller input.
            text(
                "SELECT id AS proposal_id, portfolio_id, market_id, "  # noqa: S608
                "direction::text AS direction, source::text AS source, request_digest, "
                "request_payload FROM trade_proposals WHERE organization_id = :org "
                "AND idempotency_key = :key AND status = 'pending' AND decided_at IS NULL"
                + (" FOR UPDATE" if lock else "")
            ),
            {"org": organization_id, "key": idempotency_key},
        )
    ).one_or_none()
    return None if row is None else PendingRequest.model_validate(row, from_attributes=True)


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


def _digest_pair(
    stored: str | None, request: ProposalRequest, source: ProposalSource
) -> list[tuple[str, Any, Any]]:
    """The canonical identity of the request, when the stored row carries one.

    A row written before ``0007_paper_roles`` genuinely has no digest, and
    comparing against a null would refuse every legitimate retry of it. When it
    **is** there it closes the hole the four columns left open: a replayed
    *refusal* whose second request had a different price, stop or ceiling
    (T3.12, pendência 1).
    """
    return [] if stored is None else [("request_digest", stored, request_digest(request, source))]


def _payload_pair(
    stored: dict[str, Any] | None, request: ProposalRequest
) -> list[tuple[str, Any, Any]]:
    """The archived geometry, when the filed row carries one (§21.1).

    This is what took the digest's place for a **pending** row. Since
    ``0009_paper_geometry`` the API may not write ``request_digest`` at all — a
    proof chosen by the caller binds nobody (S1 of the ``0007`` security review)
    — so without this comparison a reused key naming a *different* order would
    come back as a replay of the first one: the exact silence
    :func:`ensure_same_request` exists to prevent, one step earlier in the
    request's life.

    Compared as canonical JSON because a payload read back from JSONB carries
    PostgreSQL's key order and not the writer's, and two orderings of the same
    object are the same object.
    """
    if stored is None:
        return []
    asked = request_payload(request)
    return [
        ("request_payload", json.dumps(stored, sort_keys=True), json.dumps(asked, sort_keys=True))
    ]


def ensure_pending_is_the_same_request(
    pending: PendingRequest, request: ProposalRequest, source: ProposalSource
) -> None:
    """Refuse to decide a filed request as if it were a different one."""
    mismatches = [
        f"{name}: stored {stored}, requested {asked}"
        for name, stored, asked in [
            ("portfolio_id", pending.portfolio_id, request.portfolio_id),
            ("market_id", pending.market_id, request.market_id),
            ("direction", pending.direction.value, request.direction.value),
            ("source", pending.source.value, source.value),
            *_digest_pair(pending.request_digest, request, source),
            *_payload_pair(pending.request_payload, request),
        ]
        if _differs(stored, asked)
    ]
    if mismatches:
        raise IdempotencyConflict(
            f"idempotency key already filed request {pending.proposal_id}, which is a different "
            "order: " + "; ".join(mismatches)
        )


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
            *_digest_pair(existing.request_digest, request, source),
            *_geometry(existing, request),
        ]
        if _differs(stored, asked)
    ]
    if mismatches:
        raise IdempotencyConflict(
            f"idempotency key already answered proposal {existing.proposal_id}, which is a "
            "different order: " + "; ".join(mismatches)
        )
