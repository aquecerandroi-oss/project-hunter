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

**The blocking gap of ``notes-T3.5.md`` §5.1 is closed, and this is the writing
half.** ``trade_proposals`` used to store the *identity* of a request and none of
its **geometry**, so a filed row could be recognised and never decided — the
execution worker logged ``pending_request_without_geometry`` once a second for
ever. ``0009_paper_geometry`` adds ``request_payload`` (DATABASE.md §21.1) and
this module fills it: ``client_key``, ``market_id``, ``direction``,
``entry_ref``, ``stop``, ``target``, ``requested_notional`` and
``assumed_costs``, money as JSON strings.

**And it stops writing ``request_digest``.** The digest is what *proves* two
requests are the same one, and a proof written by the caller binds nobody: the
engine used to read it back with ``coalesce(request_digest, …)``, so a handler —
or an injection into one — could make a different order replay as an earlier
decision (S1 of ``.claude/state/review-T3.1c-security.md``). Since ``0009`` the
request guard **refuses** an ``INSERT`` by the application role that carries a
digest or a ``kill_switch_snapshot``, and the engine recomputes the digest from
the payload when it decides. The API still *computes* one and returns it to the
caller as the identity of what was asked; what it may no longer do is persist it
as proof. A replay of a pending row is therefore compared on the archived
payload (``hunter_core.admission.dedupe``), which is the same information one
step earlier.

**T3.68b.** The filing act itself now writes its own ``audit_logs`` row, with
the operator's real ``actor_id`` — before, only the engine's later decision
was audited, as ``hunter_worker`` (``services/admission_audit.py``, finding
2). A reused idempotency key on a *different* wallet is refused by name
before its geometry is even compared (finding 5), and a constraint violation
or a genuine replay conflict never echoes the database's own text or the
previous order's values back to the caller (finding 3).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from fastapi import status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hunter_api.errors import HunterError
from hunter_api.services.admission_audit import (
    TooManyPendingRequestsError,
    integrity_reason,
    record_filing_audit,
)
from hunter_core.admission.dedupe import IdempotencyConflict, find_admitted, find_pending
from hunter_core.admission.sources import (
    OriginRefused,
    ProposalRequest,
    admission_key,
    request_digest,
    request_payload,
)
from hunter_core.domain.enums import ProposalSource, ProposalStatus
from hunter_core.domain.types import uuid7
from hunter_core.strategies.envelope import PURPOSE_PAPER

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.auth.rbac import OrgContext
    from hunter_core.domain.enums import TradeDirection
    from hunter_core.strategies.envelope import AssumedCosts
    from hunter_risk.inputs import MarketIdentity

__all__ = [
    "FiledRequest",
    "OrderRefusedError",
    "OrderReplayConflictError",
    "TooManyPendingRequestsError",
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
    max_pending: int,
    requested_notional: Decimal | None = None,
) -> FiledRequest:
    """Record one operator order as a pending request. The engine decides it.

    Idempotent by ``(organization_id, idempotency_key)``: filing the same order
    twice returns the row that already exists — decided or not — and filing a
    *different* order under the same key is a 409, never a silent overwrite.

    ``max_pending`` (T3.68c) caps this wallet's undecided requests, checked
    inside this ``INSERT`` — never a separate ``SELECT count(*)`` first (would
    reopen the race "Unlocked" below accepts). A benign race across two truly
    concurrent connections remains (no lock available here) — accepted for
    paper, reasoning in ``notes-T3.68.md`` §T3.68c.
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
            purpose=PURPOSE_PAPER,
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
    payload = request_payload(request)

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
    pending = await find_pending(
        session, organization_id=context.org_id, idempotency_key=key, lock=False
    )
    if pending is not None:
        # T3.68b finding 5: the idempotency key is unique per
        # ``(organization_id, idempotency_key)`` — **not** per wallet — so two
        # different portfolios filing under the same key both land on this
        # branch. ``request_payload`` alone does not name the wallet
        # (§21.1: eight keys, none of them ``portfolio_id``), so two requests
        # for the same market/direction/geometry on two different wallets used
        # to compare equal and this returned the *other* wallet's
        # ``proposal_id`` — which ``services/orders.py``'s own read-back then
        # could not find under the caller's ``portfolio_id``, a 500 in place
        # of a 409. Checked first, and named, before the payload comparison
        # even runs.
        if pending.portfolio_id != portfolio_id:
            raise OrderReplayConflictError(
                "idempotency key already names a pending request on a different wallet "
                f"(reason: order_replay_conflict; proposal {pending.proposal_id})"
            )
        # Unlocked: the API only ever reads this row (it never decides), and
        # ``hunter_app`` lost ``UPDATE`` on ``trade_proposals`` in
        # ``0007_paper_roles`` — a ``FOR UPDATE`` read under this role is a
        # permission error, not a lock wait (T3.5c). The filed row carries no
        # digest since ``0009`` (the guard refuses one), so what is compared is
        # the archived geometry — the same information one step earlier, and
        # the thing that keeps a reused key naming a *different* order from
        # replaying as this one.
        _refuse_a_different_order(pending.request_payload, payload, pending.proposal_id)
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
        # Only ``CursorResult`` carries ``rowcount`` (``outbox_store.py``, same cast).
        result = cast(
            "CursorResult[Any]",
            await session.execute(
                text(
                    "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                    "direction, status, idempotency_key, request_payload, source, created_at) "
                    "SELECT :id, :org, :pf, :market, :direction, 'pending', :key, "
                    "CAST(:payload AS jsonb), 'manual', :now "
                    "WHERE (SELECT count(*) FROM trade_proposals WHERE organization_id = :org "
                    "AND portfolio_id = :pf AND source = 'manual' AND status = 'pending') < :cap"
                ),
                {
                    "id": proposal_id,
                    "org": context.org_id,
                    "pf": portfolio_id,
                    "market": market_id,
                    "direction": direction.value,
                    "key": key,
                    "payload": json.dumps(payload),
                    "now": now,
                    "cap": max_pending,
                },
            ),
        )
    except IntegrityError as exc:
        if IDEMPOTENCY_CONSTRAINT in str(exc.orig):
            raise OrderReplayConflictError(
                "idempotency key was filed concurrently (reason: order_replay_conflict); read "
                "the proposal back instead of filing it again"
            ) from exc
        raise OrderRefusedError(
            f"order could not be filed (reason: {integrity_reason(exc.orig)})"
        ) from exc
    if result.rowcount == 0:
        raise TooManyPendingRequestsError(portfolio_id=portfolio_id, max_pending=max_pending)
    await record_filing_audit(request=request, proposal_id=proposal_id, key=key, payload=payload)
    return FiledRequest(
        proposal_id=proposal_id,
        portfolio_id=portfolio_id,
        market_id=market_id,
        idempotency_key=key,
        request_digest=digest,
        status=ProposalStatus.PENDING,
        decided=False,
    )


def _refuse_a_different_order(
    stored: str | dict[str, object] | None, asked: str | dict[str, object], proposal_id: uuid.UUID
) -> None:
    """A reused key that names another order is a conflict, never a replay.

    Two shapes of the same question, because the two rows carry different proof:
    a **decided** proposal is compared on its ``request_digest`` (the engine
    stamped it), a **pending** one on its ``request_payload`` (the API archived
    it, and since ``0009_paper_geometry`` may not stamp a digest at all — §21.2).
    Dictionaries compare by value, which is what a canonical payload is for.

    T3.68b finding 3: the message names the proposal, never the values that
    disagreed — ``stored``/``asked`` can carry the previous order's price,
    stop or notional, and a 409 problem+json is client-facing.
    """
    if stored is not None and stored != asked:
        raise OrderReplayConflictError(
            f"idempotency key already names proposal {proposal_id} (reason: "
            "order_replay_conflict), which is a different order"
        )


def refused(exc: Exception) -> HunterError:
    """Translate a domain refusal into the problem+json it really is."""
    if isinstance(exc, IdempotencyConflict):
        return OrderReplayConflictError(str(exc))
    if isinstance(exc, OriginRefused):
        return OrderRefusedError(str(exc))
    return OrderRefusedError(str(exc))
