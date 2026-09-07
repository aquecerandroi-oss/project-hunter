"""The API's thin adapter over the shared admission service — T3.12.

The manual paper order (T3.8) has **no path of its own**: it builds a
:class:`~hunter_core.admission.sources.ProposalRequest` here and hands it to
``hunter_core.admission.admit``, which is what decides, reserves, audits and
publishes. This module adds exactly three things a request needs and the domain
service must not know about:

- the ``Idempotency-Key`` header becomes the request's ``client_key``, and the
  origin is always ``manual`` — the operator's order is not an agent's;
- the authenticated principal becomes the audit actor, and the organization of
  the transaction is the organization of the request;
- domain refusals become RFC 9457 problems, with the status that is *true* of
  each: a request that may never become a proposal is a 422, a reused key is a
  409, and a wallet that has not been opened is a 409 as well — none of them is
  a 500, and a *rejected* proposal is not an error at all (it is a decision,
  returned with its checks).

There is no route here: ``POST /api/v1/orgs/{org_id}/portfolios/{id}/orders`` is
T3.8's, and this is the function it calls.

**Known coupling, not yet resolved (notes-T3.12.md §2):** admission advances
``portfolio_risk_state.last_admission_seq`` and inserts into ``outbox_events``,
and the ``hunter_app`` role holds neither privilege today. Until T3.1b decides,
the route's unit of work has to be one that does — this adapter does not choose
a database role on its own, because widening one silently is exactly how tenant
isolation gets lost.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import status

from hunter_api.errors import HunterError
from hunter_core.admission.dedupe import IdempotencyConflict
from hunter_core.admission.inputs import MarketMismatch
from hunter_core.admission.service import admit
from hunter_core.admission.sources import OriginRefused, ProposalRequest
from hunter_core.domain.enums import ProposalSource
from hunter_core.portfolio.state import WalletNotOpen
from hunter_core.risk.scopes import RiskStateMissing

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.auth.rbac import OrgContext
    from hunter_core.admission.service import AdmissionResult
    from hunter_core.domain.enums import TradeDirection
    from hunter_core.strategies.envelope import AssumedCosts
    from hunter_risk.inputs import BetaEstimate, MarketIdentity, MarketLiquidity, MarketSpec

__all__ = [
    "AdmissionInputs",
    "OrderRefusedError",
    "OrderReplayConflictError",
    "WalletNotOpenError",
    "admit_manual_order",
]


class OrderRefusedError(HunterError):
    """422 — the request may never become a proposal (origin, purpose, market)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="order-refused",
            title="Unprocessable Entity",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        )


class OrderReplayConflictError(HunterError):
    """409 — the idempotency key already answered a **different** order."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="idempotency-key-conflict",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class WalletNotOpenError(HunterError):
    """409 — the wallet named by the order has never been opened.

    Both halves of "not open" map here: no anchor (``WalletNotOpen``) and no
    lock row (``RiskStateMissing``, raised earlier, while the lock order is
    being acquired). Leaving the second one untranslated would answer a wallet
    that was never opened with a 500 (Astra, diff review, finding 7).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="wallet-not-open",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


@dataclass(frozen=True, slots=True)
class AdmissionInputs:
    """The market picture the Risk Engine is handed, assembled by the caller.

    Grouped rather than spread over the signature because they travel together
    and are decided together: the price source, the beta revision and the exit
    cost hypothesis are the caller's declared choices (T3.3), and a route that
    picked them implicitly would be choosing them for the whole system.
    """

    liquidity: MarketLiquidity
    spec: MarketSpec
    beta: BetaEstimate
    prices: Mapping[uuid.UUID, Decimal]
    betas: Mapping[uuid.UUID, Decimal]
    exit_cost_rate: Decimal


async def admit_manual_order(
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
    inputs: AdmissionInputs,
    now: datetime,
    requested_notional: Decimal | None = None,
) -> AdmissionResult:
    """Submit one operator order through the shared admission service.

    Returns the decision — approved *or* rejected. A rejection is a 200 with the
    checks that produced it (the Explanation Panel needs the whole picture); only
    a request that could never be a proposal raises.
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

    try:
        return await admit(
            session,
            request,
            source=ProposalSource.MANUAL,
            liquidity=inputs.liquidity,
            spec=inputs.spec,
            beta=inputs.beta,
            prices=inputs.prices,
            betas=inputs.betas,
            exit_cost_rate=inputs.exit_cost_rate,
            now=now,
        )
    except IdempotencyConflict as exc:
        raise OrderReplayConflictError(str(exc)) from exc
    except (OriginRefused, MarketMismatch) as exc:
        raise OrderRefusedError(str(exc)) from exc
    except (WalletNotOpen, RiskStateMissing) as exc:
        raise WalletNotOpenError(str(exc)) from exc
