"""The API's side of an admission: it **files a request**, it does not decide.

``0007_paper_roles`` §19.2 settles who does what: *the worker decides and writes
risk state; the API asks, reads and authorises people*. So the manual paper order
(T3.8) is filed here as a **pending request** — ``source = manual``,
``status = pending``, no decision, no FIFO place, no reservation — and the
execution-worker's admission cycle decides that same row, in place, one second
later (``hunter_core.admission.decide_pending``).

Three reasons this is not the API running ``admit()`` itself, and none of them is
style:

- ``fifo_v1`` is a counter on ``portfolio_risk_state`` and that row is the
  engine's: since ``0006`` the API's ``UPDATE`` is refused by privilege, not by a
  trigger;
- since ``0007`` the API has no ``UPDATE``/``DELETE`` on ``trade_proposals`` at
  all, so it could not attach a reservation or move a status even if it wanted to;
- ``outbox_events`` is worker-writable only, so an admission run by the API could
  decide and never announce.

The database enforces the shape rather than trusting this module:
``trade_proposals_the_app_only_files_requests`` (§19.4) refuses an ``INSERT`` by
the application role that carries a decision, a sequence or a reservation.

**Blocking gap, declared and not worked around.** ``trade_proposals`` has no
column for the *geometry* of a request — ``entry_ref``, ``stop``,
``requested_notional`` and ``assumed_costs`` are inputs of the Risk Engine and
none of them is persisted. A filed request can therefore be identified (key +
``request_digest``) but **not re-decided from the row alone**, so the manual
route is not end-to-end until a migration adds somewhere to keep it. Writing the
geometry into ``risk_decision`` is not an option (the guard refuses it, and it
would be a decision nobody took) and inventing values is worse. Registered in
``.claude/state/notes-T3.5.md`` §3 for T3.1d/T3.8.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hunter_api.errors import HunterError
from hunter_core.admission.dedupe import IdempotencyConflict, find_admitted, find_pending
from hunter_core.admission.sources import (
    OriginRefused,
    ProposalRequest,
    admission_key,
    request_digest,
)
from hunter_core.domain.enums import ProposalSource, ProposalStatus
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.auth.rbac import OrgContext
    from hunter_core.domain.enums import TradeDirection
    from hunter_core.strategies.envelope import AssumedCosts
    from hunter_risk.inputs import MarketIdentity

__all__ = [
    "FiledRequest",
    "OrderRefusedError",
    "OrderReplayConflictError",
    "WalletNotOpenError",
    "file_manual_order",
]

IDEMPOTENCY_CONSTRAINT = "uq_trade_proposals_idem"


class OrderRefusedError(HunterError):
    """422 — the request may never become a proposal (origin, purpose, geometry)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="order-refused",
            title="Unprocessable Entity",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        )


class OrderReplayConflictError(HunterError):
    """409 — the idempotency key already names a **different** order."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="idempotency-key-conflict",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class WalletNotOpenError(HunterError):
    """409 — the wallet named by the order has never been opened."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="wallet-not-open",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


@dataclass(frozen=True, slots=True)
class FiledRequest:
    """What the API can honestly tell the caller after filing an order.

    Deliberately **not** a decision: at this point the Risk Engine has not seen
    the request, and returning an approval-shaped object with empty checks is how
    an operator learns to read "filed" as "approved".
    """

    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    idempotency_key: str
    request_digest: str
    status: ProposalStatus
    decided: bool
    """``True`` when this key had already been decided — the caller should read
    the decision back, not file again."""


async def file_manual_order(
    session: AsyncSession,
    *,
    context: OrgContext,
    idempotency_key: str,
    portfolio_id: uuid.UUID,
    market_id: uuid.UUID,
    market: MarketIdentity,
    direction: TradeDirection,
    entry_ref: Decimal,
    stop: Decimal,
    assumed_costs: AssumedCosts,
    now: datetime,
    requested_notional: Decimal | None = None,
) -> FiledRequest:
    """Record one operator order as a pending request. The engine decides it.

    Idempotent by ``(organization_id, idempotency_key)``: filing the same order
    twice returns the row that already exists — decided or not — and filing a
    *different* order under the same key is a 409, never a silent overwrite.
    """
    try:
        request = ProposalRequest(
            client_key=idempotency_key,
            organization_id=context.org_id,
            portfolio_id=portfolio_id,
            market_id=market_id,
            market=market,
            direction=direction,
            entry_ref=entry_ref,
            stop=stop,
            requested_notional=requested_notional,
            assumed_costs=assumed_costs,
            actor_id=str(context.principal.user_id),
            actor_type="user",
        )
    except ValueError as exc:
        raise OrderRefusedError(str(exc)) from exc

    source = ProposalSource.MANUAL
    try:
        key = admission_key(source, idempotency_key)
    except ValueError as exc:
        raise OrderRefusedError(str(exc)) from exc
    digest = request_digest(request, source)

    decided = await find_admitted(session, organization_id=context.org_id, idempotency_key=key)
    if decided is not None:
        _refuse_a_different_order(decided.request_digest, digest, decided.proposal_id)
        return FiledRequest(
            proposal_id=decided.proposal_id,
            portfolio_id=decided.portfolio_id,
            market_id=decided.market_id,
            idempotency_key=key,
            request_digest=digest,
            status=decided.status,
            decided=True,
        )
    pending = await find_pending(session, organization_id=context.org_id, idempotency_key=key)
    if pending is not None:
        _refuse_a_different_order(pending.request_digest, digest, pending.proposal_id)
        return FiledRequest(
            proposal_id=pending.proposal_id,
            portfolio_id=pending.portfolio_id,
            market_id=pending.market_id,
            idempotency_key=key,
            request_digest=digest,
            status=ProposalStatus.PENDING,
            decided=False,
        )

    proposal_id = uuid7()
    try:
        await session.execute(
            text(
                "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                "direction, status, idempotency_key, request_digest, source, created_at) "
                "VALUES (:id, :org, :pf, :market, :direction, 'pending', :key, :digest, "
                "'manual', :now)"
            ),
            {
                "id": proposal_id,
                "org": context.org_id,
                "pf": portfolio_id,
                "market": market_id,
                "direction": direction.value,
                "key": key,
                "digest": digest,
                "now": now,
            },
        )
    except IntegrityError as exc:
        if IDEMPOTENCY_CONSTRAINT in str(exc.orig):
            raise OrderReplayConflictError(
                f"idempotency key {idempotency_key!r} was filed concurrently; read the proposal "
                "back instead of filing it again"
            ) from exc
        raise OrderRefusedError(str(exc.orig)) from exc
    return FiledRequest(
        proposal_id=proposal_id,
        portfolio_id=portfolio_id,
        market_id=market_id,
        idempotency_key=key,
        request_digest=digest,
        status=ProposalStatus.PENDING,
        decided=False,
    )


def _refuse_a_different_order(stored: str | None, asked: str, proposal_id: uuid.UUID) -> None:
    """A reused key that names another order is a conflict, never a replay."""
    if stored is not None and stored != asked:
        raise OrderReplayConflictError(
            f"idempotency key already names proposal {proposal_id}, which is a different order "
            f"(request_digest {stored} != {asked})"
        )


def refused(exc: Exception) -> HunterError:
    """Translate a domain refusal into the problem+json it really is."""
    if isinstance(exc, IdempotencyConflict):
        return OrderReplayConflictError(str(exc))
    if isinstance(exc, OriginRefused):
        return OrderRefusedError(str(exc))
    return OrderRefusedError(str(exc))
