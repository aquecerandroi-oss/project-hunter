"""The market picture one manual request is decided against.

The operator's route (T3.8) names a SPOT market directly — there is no
perpetual to map from, unlike the shadow bridge (T3.14). What is assembled here
is otherwise the same picture :mod:`hunter_execution_worker.bridge_inputs`
builds for a bridge candidate, read through the same sources and refused by the
same names when a source has nothing to say: nothing here has a default that
flatters the market.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_execution_worker.admission_cycle import RequestInputs
from hunter_execution_worker.bridge_inputs import (
    liquidity_for,
    marks_for_open_positions,
    prices_with,
)
from hunter_execution_worker.bridge_universe import beta_map, current_beta, spot_pair_of

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.tape import MarkingPolicy
    from hunter_execution_worker.market_data import SpotMarketData
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["manual_request_inputs"]


async def manual_request_inputs(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    data: SpotMarketData,
    policy: MarkingPolicy,
    now: datetime,
    exit_cost_rate: Decimal,
) -> RequestInputs | str:
    """Every input :func:`hunter_core.admission.service.admit` needs, or a reason.

    ``spot_market_unknown`` when the request's own market is not a monitored
    SPOT row (T3.0c has not seen it, or it is not SPOT at all — D1);
    ``beta_unavailable`` when RISK_ENGINE.md §6's three conditions are not all
    true together right now. Everything else is
    :func:`hunter_execution_worker.bridge_inputs.liquidity_for`'s own refusal
    (``spot_price_unavailable``, ``spot_book_unavailable``).
    """
    pair = await spot_pair_of(session, market.market_id)
    if pair is None:
        return "spot_market_unknown"
    snapshot = await data.snapshot(market.identity)
    liquidity = await liquidity_for(session, spot=pair, market=market, snapshot=snapshot, now=now)
    if isinstance(liquidity, str):
        return liquidity
    beta = await current_beta(session, market_id=market.market_id, now=now)
    if beta is None:
        return "beta_unavailable"
    coverage = await marks_for_open_positions(
        session, wallet=wallet, data=data, policy=policy, now=now
    )
    if not coverage.complete:
        # A wallet whose own positions cannot all be priced live is a wallet
        # whose equity, drawdown and aggregate risk are estimates. The engine
        # would refuse anyway (``marks_complete`` -> ``portfolio_status``
        # unavailable), but refusing *here* keeps the request pending instead of
        # burning it into a rejected row over a transient tape.
        return "marks_incomplete"
    prices = prices_with(coverage.marks, market_id=market.market_id, price=liquidity.last_price)
    betas = await beta_map(session, market_ids=prices.keys(), now=now)
    return RequestInputs(
        liquidity=liquidity,
        beta=beta,
        prices=prices,
        betas={key: estimate.value for key, estimate in betas.items()},
        exit_cost_rate=exit_cost_rate,
    )
