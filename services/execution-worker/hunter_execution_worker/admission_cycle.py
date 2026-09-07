"""The admission cycle: the engine decides what the API filed.

``0007_paper_roles`` §19.4 splits one act in two — the API files a request, the
engine decides it — and this is the second half, polled every second. It decides
**the filed row itself** (``hunter_core.admission.decide_pending``): inserting a
second proposal for the same request would leave the pending one for ever, take
a second place in the FIFO queue and show the operator two orders where there
was one (adversarial review of 2026-09-07, condition 1).

**A pending row this worker cannot read is left alone, and said out loud.**
``trade_proposals`` persists the *identity* of a request (key + digest) but not
its **geometry**: there is no column for ``entry_ref``, ``stop``,
``requested_notional`` or ``assumed_costs``. So a request filed by the API cannot
be rebuilt from the row, and this cycle refuses to invent one — it logs
``pending_request_without_geometry``, counts it, and waits for the column
(notes-T3.5.md §3, addressed to T3.1d/T3.8). Requests handed in by a caller that
*does* hold them — the operator's script today, the T3.14 bridge when it lands —
are decided normally, in their own row.

The extension point for T3.14 is :func:`decide_requests`: it takes
``ProposalRequest`` objects and the market picture, and everything about
autonomy — which signals become requests, and the ``ENABLE_PAPER_AUTONOMY``
gate — stays on the other side of it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.admission.service import AdmissionResult, admit
from hunter_core.admission.sources import ProposalRequest, admission_key, resolve_source
from hunter_core.logging import get_logger
from hunter_execution_worker.reference import MarketReference, load_market

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef
    from hunter_risk.inputs import BetaEstimate, MarketLiquidity

__all__ = ["PendingRow", "RequestInputs", "decide_requests", "pending_requests"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PendingRow:
    """A request the API filed, as the engine can see it in the table."""

    proposal_id: uuid.UUID
    market_id: uuid.UUID
    idempotency_key: str
    request_digest: str | None
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
            "SELECT id AS proposal_id, market_id, idempotency_key, request_digest, created_at "
            "FROM trade_proposals WHERE organization_id = :org AND portfolio_id = :pf "
            "AND status = 'pending' AND decided_at IS NULL ORDER BY created_at LIMIT :limit"
        ),
        {"org": wallet.organization_id, "pf": wallet.portfolio_id, "limit": limit},
    )
    return tuple(
        PendingRow(
            proposal_id=row.proposal_id,
            market_id=row.market_id,
            idempotency_key=row.idempotency_key,
            request_digest=row.request_digest,
            created_at=row.created_at,
        )
        for row in rows
    )


def report_unreadable(wallet: WalletRef, rows: Sequence[PendingRow]) -> int:
    """Say, once per cycle, which filed requests cannot be decided from the row.

    Not a refusal and not a decision: refusing would destroy an operator's order
    over a schema gap, and deciding would need numbers nobody wrote down.
    """
    for row in rows:
        logger.warning(
            "pending_request_without_geometry",
            portfolio_id=str(wallet.portfolio_id),
            proposal_id=str(row.proposal_id),
            idempotency_key=row.idempotency_key,
            reason="trade_proposals has no column for entry_ref/stop/assumed_costs",
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
