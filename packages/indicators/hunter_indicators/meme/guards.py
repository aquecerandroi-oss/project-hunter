"""The refusal vocabulary of the paper wallet, as pure functions.

Every "no" the wallet can say has a name, and the name is decided here, away
from the mutation: :func:`refuse_buy` and :func:`refuse_sell` read a snapshot of
the wallet's state and return the first refusal or ``None``. The order of the
checks is part of the contract — a trade that breaks three caps is reported by
the most fundamental one, and ``fill_not_after_intent`` comes before any cap so
a look-ahead fill is never dressed up as a risk refusal.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves
from hunter_indicators.meme.models import PaperPosition, PaperWalletLimits

__all__ = ["BUY_REFUSALS", "SELL_REFUSALS", "refuse_buy", "refuse_sell"]

BUY_REFUSALS: Final = frozenset(
    {
        "daily_loss_cap_latched",
        "size_not_positive",
        "fill_not_after_intent",
        "curve_complete",
        "per_trade_cap",
        "balance_insufficient",
        "max_open_positions",
        "exposure_per_mint_cap",
    }
)
"""The closed vocabulary of buy refusals. A new reason is a code change and a
test, never a free-text string invented at the call site."""

SELL_REFUSALS: Final = frozenset(
    {"size_not_positive", "no_position", "tokens_exceed_position", "fill_not_after_intent"}
)
"""Sell refusals. Note what is *not* here: the daily loss latch never blocks an
exit — a kill switch that trapped a position would be a bug with a safety badge."""


def refuse_buy(
    *,
    limits: PaperWalletLimits,
    balance_sol: Decimal,
    positions: Mapping[str, PaperPosition],
    halted_reason: str | None,
    mint: str,
    sol: Decimal,
    reserves: CurveReserves,
    ts: datetime,
    intent_ts: datetime,
    priority_fee_sol: Decimal,
) -> str | None:
    """First reason this buy must not happen, or ``None``."""
    if halted_reason is not None:
        return halted_reason
    if sol <= 0 or priority_fee_sol < 0:
        return "size_not_positive"
    if ts <= intent_ts:
        return "fill_not_after_intent"
    if reserves.complete:
        return "curve_complete"
    with localcontext(CONTEXT):
        outflow = sol + priority_fee_sol
        if outflow > limits.max_sol_per_trade:
            return "per_trade_cap"
        if outflow > balance_sol:
            return "balance_insufficient"
        held = positions.get(mint)
        if held is None and len(positions) >= limits.max_open_positions:
            return "max_open_positions"
        exposure = (Decimal(0) if held is None else held.cost_basis_sol) + outflow
        if exposure > limits.max_exposure_per_mint_sol:
            return "exposure_per_mint_cap"
    return None


def refuse_sell(
    *, position: PaperPosition | None, tokens: Decimal, ts: datetime, intent_ts: datetime
) -> str | None:
    """First reason this sell must not happen, or ``None``."""
    if tokens <= 0:
        return "size_not_positive"
    if position is None:
        return "no_position"
    if tokens > position.tokens:
        return "tokens_exceed_position"
    if ts <= intent_ts:
        return "fill_not_after_intent"
    return None
