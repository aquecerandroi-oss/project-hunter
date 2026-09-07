"""The admission cycle: the engine decides what the API filed.

``0007_paper_roles`` §19.4 splits one act in two — the API files a request, the
engine decides it — and this is the second half, polled every second. It decides
**the filed row itself** (``hunter_core.admission.decide_pending``, reached
through the shared :func:`~hunter_core.admission.service.admit`): inserting a
second proposal for the same request would leave the pending one for ever, take
a second place in the FIFO queue and show the operator two orders where there
was one (adversarial review of 2026-09-07, condition 1).

**A pending row is decided when it carries its geometry, and only then.**
``0009_paper_geometry`` (DATABASE.md §21.1) gave ``trade_proposals`` a
``request_payload`` column, and the API's route (T3.8) fills it at filing time —
so a row this cycle reads now carries ``entry_ref``, ``stop``, ``target``,
``requested_notional`` and ``assumed_costs``, and :func:`rebuild_request` turns
it back into the ``ProposalRequest`` the engine can decide, exactly the request
the operator asked for (the archived payload is what a replay of it is compared
against — ``hunter_core.admission.dedupe``). A row filed **before** this column
existed has no payload and genuinely cannot be rebuilt: that is the only case
``pending_request_without_geometry`` still names (notes-T3.5.md §5.1, closed by
T3.1e).

The extension point for T3.14 is :func:`decide_requests`: it takes
``ProposalRequest`` objects and the market picture, and everything about
autonomy — which signals become requests, and the ``ENABLE_PAPER_AUTONOMY``
gate — stays on the other side of it. This module's own
:func:`rebuild_request` is the manual-request producer that feeds the very
same function.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.admission.service import AdmissionResult, admit
from hunter_core.admission.sources import ProposalRequest, admission_key, resolve_source
from hunter_core.domain.enums import TradeDirection
from hunter_core.logging import get_logger
from hunter_core.strategies.envelope import AssumedCosts
from hunter_execution_worker.config import PRODUCER
from hunter_execution_worker.reference import MarketReference, load_market

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef
    from hunter_risk.inputs import BetaEstimate, MarketLiquidity

__all__ = [
    "PendingRow",
    "RequestInputs",
    "decide_requests",
    "pending_requests",
    "readable_and_unreadable",
    "rebuild_request",
]

logger = get_logger(__name__)


def _decimal_or_none(raw: object) -> Decimal | None:
    return None if raw is None else Decimal(str(raw))


@dataclass(frozen=True, slots=True)
class PendingRow:
    """A request the API filed, as the engine can see it in the table."""

    proposal_id: uuid.UUID
    market_id: uuid.UUID
    idempotency_key: str
    request_digest: str | None
    request_payload: dict[str, Any] | None
    """The geometry the API archived (§21.1), or ``None`` for a row filed
    before ``0009_paper_geometry`` — the only shape :func:`rebuild_request`
    cannot turn into a decidable request."""

    created_at: datetime


@dataclass(frozen=True, slots=True)
class RequestInputs:
    """The market picture one admission is decided against.

    Assembled by the caller and handed in whole, exactly as ``admit`` requires:
    the price source, the beta revision and the exit-cost hypothesis are declared
    choices, and a service that fetched them would be choosing them silently
    (T3.3).
    """

    liquidity: MarketLiquidity
    beta: BetaEstimate
    prices: Mapping[uuid.UUID, Decimal]
    betas: Mapping[uuid.UUID, Decimal]
    exit_cost_rate: Decimal


async def pending_requests(
    session: AsyncSession, *, wallet: WalletRef, limit: int = 50
) -> tuple[PendingRow, ...]:
    """Every request filed for this wallet and not yet decided, oldest first."""
    rows = await session.execute(
        text(
            "SELECT id AS proposal_id, market_id, idempotency_key, request_digest, "
            "request_payload, created_at FROM trade_proposals WHERE organization_id = :org "
            "AND portfolio_id = :pf AND status = 'pending' AND decided_at IS NULL "
            "ORDER BY created_at LIMIT :limit"
        ),
        {"org": wallet.organization_id, "pf": wallet.portfolio_id, "limit": limit},
    )
    return tuple(
        PendingRow(
            proposal_id=row.proposal_id,
            market_id=row.market_id,
            idempotency_key=row.idempotency_key,
            request_digest=row.request_digest,
            request_payload=row.request_payload,
            created_at=row.created_at,
        )
        for row in rows
    )


def readable_and_unreadable(
    rows: Sequence[PendingRow],
) -> tuple[tuple[PendingRow, ...], tuple[PendingRow, ...]]:
    """Split filed requests into the ones this cycle can decide and the ones it cannot.

    A row with a ``request_payload`` can be turned back into a
    :class:`~hunter_core.admission.sources.ProposalRequest` by
    :func:`rebuild_request`; a row without one predates ``0009_paper_geometry``
    and has no geometry to rebuild from — the only case
    :func:`report_unreadable` still names.
    """
    readable = tuple(row for row in rows if row.request_payload is not None)
    unreadable = tuple(row for row in rows if row.request_payload is None)
    return readable, unreadable


def rebuild_request(
    row: PendingRow, *, wallet: WalletRef, market: MarketReference, actor_id: str = PRODUCER
) -> ProposalRequest:
    """The ``ProposalRequest`` the operator filed, read back from its own payload.

    ``client_key`` comes from the payload, not ``row.idempotency_key``: the
    column already carries the origin prefix (``manual:...``), and
    :func:`~hunter_core.admission.sources.admission_key` would prefix it a
    second time. Every geometry field round-trips exactly because
    :func:`~hunter_core.admission.sources.request_payload` wrote money as the
    canonical ``str(Decimal(...))`` and this only ever parses that same string
    back — the identity :func:`hunter_core.admission.dedupe.ensure_pending_is_the_same_request`
    checks when ``admit`` re-reads the row under the wallet's lock.

    The filer's own identity does not travel: ``trade_proposals`` has no column
    for it (the filing itself is not separately audited today — a gap of the
    current schema, not of this reconstruction), so the decision this cycle
    takes is audited as the worker's own act, ``actor_type="worker"`` — the same
    convention :mod:`hunter_execution_worker.bridge` uses for a proposal it
    submits on the wallet's behalf.
    """
    payload = row.request_payload
    if payload is None:  # pragma: no cover - callers pass only readable rows
        raise ValueError(f"proposal {row.proposal_id} has no request_payload to rebuild from")
    costs = payload.get("assumed_costs")
    if not isinstance(costs, dict):  # pragma: no cover - the CHECK requires an object
        raise ValueError(f"proposal {row.proposal_id} has no assumed_costs object in its payload")
    return ProposalRequest(
        client_key=str(payload["client_key"]),
        organization_id=wallet.organization_id,
        portfolio_id=wallet.portfolio_id,
        market_id=row.market_id,
        market=market.identity,
        direction=TradeDirection(payload["direction"]),
        entry_ref=Decimal(str(payload["entry_ref"])),
        stop=Decimal(str(payload["stop"])),
        target=_decimal_or_none(payload.get("target")),
        requested_notional=_decimal_or_none(payload.get("requested_notional")),
        assumed_costs=AssumedCosts.model_validate(costs),
        actor_id=actor_id,
        actor_type="worker",
    )


def report_unreadable(
    wallet: WalletRef, rows: Sequence[PendingRow], *, reported: set[uuid.UUID] | None = None
) -> int:
    """Name each filed request that cannot be decided from the row — **once**.

    Only a row with no ``request_payload`` reaches this any more — one filed
    before ``0009_paper_geometry`` gave the API a column to archive the
    geometry in (notes-T3.5.md §5.1, closed by T3.1e). Not a refusal and not a
    decision: refusing would destroy an operator's order over a schema gap, and
    deciding would need numbers nobody wrote down. But saying it every second is
    not saying it either: this cycle polls at 1 s, so one unreadable request
    wrote 86.400 identical WARNING lines a day and buried everything else in the
    worker's log (review of ``7ecafd2``, item 4).

    ``reported`` is the set of proposals already named, kept per process by
    :class:`hunter_execution_worker.cycles.Cycles`. A line is written on the
    **transition** — the first cycle that sees a given row — and the row is
    forgotten when it stops being pending, so a request filed, decided and filed
    again under a new id is named again. The *level* of the problem is the gauge
    ``hunter_execution_pending_requests{readable="false"}``, which is a number
    and does not decay; the log is the event. Without a set (a single-shot
    caller, a test) every row is named, which is the old behaviour of one call.
    """
    seen: set[uuid.UUID] = reported if reported is not None else set()
    current = {row.proposal_id for row in rows}
    seen.intersection_update(current)
    for row in rows:
        if row.proposal_id in seen:
            continue
        seen.add(row.proposal_id)
        logger.warning(
            "pending_request_without_geometry",
            portfolio_id=str(wallet.portfolio_id),
            proposal_id=str(row.proposal_id),
            idempotency_key=row.idempotency_key,
            reason="filed before 0009_paper_geometry; no request_payload to rebuild from",
        )
    return len(rows)


async def decide_requests(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    requests: Sequence[tuple[ProposalRequest, RequestInputs]],
    now: datetime,
    source: str = "manual",
) -> tuple[AdmissionResult, ...]:
    """Admit every request handed in, through the one shared admission service.

    The market's ``MarketSpec`` is read from ``markets`` rather than taken from
    the caller: the engine's step and floor have to be the exchange's, and a
    caller that supplied them could size an order the venue would refuse.
    """
    origin = resolve_source(source)
    results: list[AdmissionResult] = []
    for request, inputs in requests:
        market = await load_market(session, request.market_id)
        if market is None:
            logger.error(
                "admission_market_unknown",
                portfolio_id=str(wallet.portfolio_id),
                market_id=str(request.market_id),
            )
            continue
        result = await admit(
            session,
            request,
            source=origin,
            liquidity=inputs.liquidity,
            spec=market.spec,
            beta=inputs.beta,
            prices=inputs.prices,
            betas=inputs.betas,
            exit_cost_rate=inputs.exit_cost_rate,
            now=now,
        )
        logger.info(
            "request_admitted",
            portfolio_id=str(wallet.portfolio_id),
            proposal_id=str(result.proposal_id),
            approved=result.approved,
            replayed=result.replayed,
            idempotency_key=admission_key(origin, request.client_key),
        )
        results.append(result)
    return tuple(results)


def market_of(reference: MarketReference) -> uuid.UUID:
    """The market id of a reference — kept so callers never re-read the row."""
    return reference.market_id
