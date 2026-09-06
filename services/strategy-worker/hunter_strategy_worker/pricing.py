"""Synthetic prices and the hypothetical R — SHADOW-LAB.md "Decisão conjunta" §3.

Every number here is built from OHLC and the experiment's **declared cost
hypothesis** (2 bps total spread, 5 bps slippage per side, 4 bps fee per side).
None of them is a quote: the hot state's ask is never read and a bid/ask is
never reconstructed, because a synthetic fill that pretends to be a real one is
exactly the kind of invented number this lab exists to avoid.

    P_entry = open  x (1 + (spread/2 + slippage) / 10000)
    P_exit  = base  x (1 - (spread/2 + slippage) / 10000)
    R_net   = ((P_exit - P_entry) - fee*P_entry - fee*P_exit - funding) / (P_entry - stop)

The fee is charged *outside* the prices (both legs) and funding is signed per
unit: positive means the long paid it. Everything runs inside
``hunter_core.strategies.numeric.CONTEXT`` so a caller's ambient ``decimal``
context cannot move a persisted number (notes-S1.md §9/§11).
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Final

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from hunter_core.strategies.envelope import AssumedCosts

_BPS: Final = Decimal("10000")
_TWO: Final = Decimal("2")

__all__ = ["cost_bps", "entry_price", "exit_price", "fee_fraction", "r_net"]


def cost_bps(costs: AssumedCosts) -> Decimal:
    """Half the total spread plus one side of slippage, in bps (2/2 + 5 = 6)."""
    with localcontext(CONTEXT):
        return costs.spread_bps / _TWO + costs.slippage_bps


def fee_fraction(costs: AssumedCosts) -> Decimal:
    """The per-side fee as a fraction (4 bps -> ``0.0004``)."""
    with localcontext(CONTEXT):
        return costs.fee_bps / _BPS


def entry_price(bar_open: Decimal, costs: AssumedCosts) -> Decimal:
    """The hypothetical long fill at ``bar_open`` — always adverse."""
    with localcontext(CONTEXT):
        return bar_open * (Decimal(1) + cost_bps(costs) / _BPS)


def exit_price(base: Decimal, costs: AssumedCosts) -> Decimal:
    """The hypothetical long exit at ``base`` — always adverse."""
    with localcontext(CONTEXT):
        return base * (Decimal(1) - cost_bps(costs) / _BPS)


def r_net(
    *,
    entry: Decimal,
    exit_: Decimal,
    stop: Decimal,
    costs: AssumedCosts,
    funding_per_unit: Decimal,
) -> Decimal:
    """Net R of one hypothetical trade. ``stop`` is the frozen initial stop.

    Raises when the initial risk is not positive: a division by zero (or by a
    negative) would produce a number with no meaning, and a "0 R" placeholder
    would be an invented result.
    """
    with localcontext(CONTEXT):
        risk = entry - stop
        if risk <= 0:
            raise ValueError(f"initial risk must be positive, got {risk}")
        fee = fee_fraction(costs)
        gross = exit_ - entry
        return (gross - fee * entry - fee * exit_ - funding_per_unit) / risk
