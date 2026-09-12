"""Bonding-curve arithmetic for a paper trade: cost, proceeds, impact, fees.

The curve is a constant product, ``S * T = k``, with ``S`` the *virtual* SOL
reserve and ``T`` the *virtual* token reserve, both in normalised units (SOL and
whole tokens, never lamports/subunits — the conversion belongs to the adapter).
Astra's T4.0 review states the two quotes as

    buy of ``q`` tokens costs   ``k/(T - q) - S``
    sell of ``q`` tokens yields ``S - k/(T + q)``

and this module computes the algebraically identical ``S*q/(T - q)`` and
``S*q/(T + q)``, which do not subtract two nearly equal 28-digit numbers when
the trade is small against the reserves. The identity is asserted by test, not
assumed.

Three rules this module exists to enforce:

1. **Fees are never inside the formulas.** ``buy_cost``/``sell_proceeds`` are
   pre-fee quotes. The 1,25 % of the curve (creator + protocol, confirmed on
   ``pump.fun/docs/fees`` updated 2026-05-20) is passed in as ``fee_pct`` by
   every caller; :data:`CURVE_TRADE_FEE_PCT` is documentation and a default for
   configuration, never a value a formula reads.
2. **Our own trade moves the curve.** :func:`reserves_after_buy` /
   :func:`reserves_after_sell` return the reserves a *next* quote must use, so a
   simulator can never price two trades at the same point.
3. **Unknown is not zero.** ``real_token_reserves`` and
   ``initial_real_token_reserves`` are optional; without the launch denominator
   :func:`curve_progress_pct` returns ``None`` instead of inventing a progress.

Precision: every division runs under ``hunter_core.strategies.numeric.CONTEXT``
(28 digits, ROUND_HALF_EVEN) so a frozen rule set does not change value because
some other library moved the ambient decimal context.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "CURVE_TRADE_FEE_PCT",
    "INITIAL_VIRTUAL_SOL_RESERVES",
    "INITIAL_VIRTUAL_TOKEN_RESERVES",
    "BuyQuote",
    "CurveReserves",
    "SellQuote",
    "buy_cost",
    "constant_product",
    "curve_input_from_budget",
    "curve_progress_pct",
    "fee_amount",
    "marginal_price_sol",
    "market_cap_sol",
    "quote_buy",
    "quote_sell",
    "reserves_after_buy",
    "reserves_after_sell",
    "sell_proceeds",
    "tokens_for_sol",
]

HUNDRED: Final = Decimal(100)

INITIAL_VIRTUAL_SOL_RESERVES: Final = Decimal(30)
"""SOL side of a brand-new pump.fun curve — confirmed live twice (T4.0 §2 and
the T4.1 capture ``vSolInBondingCurve = 30``). Never read by a formula here."""

INITIAL_VIRTUAL_TOKEN_RESERVES: Final = Decimal(1_073_000_000)
"""Token side of a brand-new curve (``vTokensInBondingCurve = 1073000000``)."""

CURVE_TRADE_FEE_PCT: Final = Decimal("1.25")
"""Documented total fee per curve trade, creator fee included. A **default for
configuration**; the math always takes the fee it is handed."""


@dataclass(frozen=True, slots=True)
class CurveReserves:
    """One point on one curve. Refuses to exist with a number no curve can hold."""

    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal
    real_token_reserves: Decimal | None = None
    """Tokens still purchasable from the curve; ``None`` when not observed."""
    initial_real_token_reserves: Decimal | None = None
    """The launch denominator of :func:`curve_progress_pct`; never recomputed."""
    complete: bool = False
    """The program's own flag. Completion is observed, never derived here."""

    def __post_init__(self) -> None:
        if self.virtual_sol_reserves <= 0:
            raise ValueError("virtual_sol_reserves must be positive")
        if self.virtual_token_reserves <= 0:
            raise ValueError("virtual_token_reserves must be positive")
        if self.real_token_reserves is not None and self.real_token_reserves < 0:
            raise ValueError("real_token_reserves cannot be negative")
        if self.initial_real_token_reserves is not None and self.initial_real_token_reserves <= 0:
            raise ValueError("initial_real_token_reserves must be positive when known")


def constant_product(reserves: CurveReserves) -> Decimal:
    """``k = S * T`` — the invariant every quote below preserves."""
    with localcontext(CONTEXT):
        return reserves.virtual_sol_reserves * reserves.virtual_token_reserves


def marginal_price_sol(reserves: CurveReserves) -> Decimal:
    """SOL per token for the next infinitesimal unit. Not a fill price."""
    with localcontext(CONTEXT):
        return reserves.virtual_sol_reserves / reserves.virtual_token_reserves


def market_cap_sol(reserves: CurveReserves, total_supply: Decimal) -> Decimal:
    """Marginal price times supply — always theoretical (T4-MEME-RADAR.md §4)."""
    if total_supply <= 0:
        raise ValueError("total_supply must be positive")
    with localcontext(CONTEXT):
        return marginal_price_sol(reserves) * total_supply


def curve_progress_pct(reserves: CurveReserves) -> Decimal | None:
    """``1 - real/initial`` in percent, or ``None`` when the launch value is unknown.

    The denominator is the *initial* real token reserve captured at creation
    (T4-MEME-RADAR.md §5, Astra's correction), not a SOL threshold: the ~85 SOL
    figure circulating in secondary sources is implied by one parameterisation
    and is not a criterion this code checks.
    """
    real, initial = reserves.real_token_reserves, reserves.initial_real_token_reserves
    if real is None or initial is None:
        return None
    with localcontext(CONTEXT):
        return HUNDRED * (initial - real) / initial


def _positive(amount: Decimal, what: str) -> None:
    if amount <= 0:
        raise ValueError(f"{what} must be positive")


def buy_cost(reserves: CurveReserves, tokens: Decimal) -> Decimal:
    """Pre-fee SOL the curve charges for ``tokens`` tokens."""
    _positive(tokens, "tokens")
    if tokens >= reserves.virtual_token_reserves:
        raise ValueError("a buy cannot take the whole virtual token reserve")
    with localcontext(CONTEXT):
        return reserves.virtual_sol_reserves * tokens / (reserves.virtual_token_reserves - tokens)


def tokens_for_sol(reserves: CurveReserves, sol: Decimal) -> Decimal:
    """Pre-fee tokens ``sol`` SOL buys — the inverse of :func:`buy_cost`."""
    _positive(sol, "sol")
    with localcontext(CONTEXT):
        return reserves.virtual_token_reserves * sol / (reserves.virtual_sol_reserves + sol)


def sell_proceeds(reserves: CurveReserves, tokens: Decimal) -> Decimal:
    """Pre-fee SOL the curve pays for ``tokens`` tokens."""
    _positive(tokens, "tokens")
    with localcontext(CONTEXT):
        return reserves.virtual_sol_reserves * tokens / (reserves.virtual_token_reserves + tokens)


def reserves_after_buy(reserves: CurveReserves, tokens: Decimal) -> CurveReserves:
    """The curve after **our** buy: our impact, not a forecast of anyone else's.

    ``complete`` is carried over untouched — a real token reserve reaching zero
    is the program's event to declare, and deriving it here would fabricate a
    graduation the data never reported.
    """
    cost = buy_cost(reserves, tokens)
    real = reserves.real_token_reserves
    if real is not None and tokens > real:
        raise ValueError("a buy cannot exceed the real token reserve for sale")
    with localcontext(CONTEXT):
        return replace(
            reserves,
            virtual_sol_reserves=reserves.virtual_sol_reserves + cost,
            virtual_token_reserves=reserves.virtual_token_reserves - tokens,
            real_token_reserves=None if real is None else real - tokens,
        )


def reserves_after_sell(reserves: CurveReserves, tokens: Decimal) -> CurveReserves:
    """The curve after **our** sell. The SOL side stays positive by construction."""
    proceeds = sell_proceeds(reserves, tokens)
    real = reserves.real_token_reserves
    with localcontext(CONTEXT):
        return replace(
            reserves,
            virtual_sol_reserves=reserves.virtual_sol_reserves - proceeds,
            virtual_token_reserves=reserves.virtual_token_reserves + tokens,
            real_token_reserves=None if real is None else real + tokens,
        )


def fee_amount(amount_sol: Decimal, fee_pct: Decimal) -> Decimal:
    """The protocol+creator cut of ``amount_sol`` at ``fee_pct`` percent."""
    if fee_pct < 0:
        raise ValueError("fee_pct cannot be negative")
    with localcontext(CONTEXT):
        return amount_sol * fee_pct / HUNDRED


def curve_input_from_budget(budget_sol: Decimal, fee_pct: Decimal) -> Decimal:
    """How much of a SOL budget reaches the curve when the fee rides on top.

    The pump program computes the curve cost first and charges the fee on it, so
    a wallet willing to part with ``B`` SOL puts ``B / (1 + f)`` into the curve.
    Declared as an assumption, not a measurement: no live buy has been executed
    by this project, and a fill that ever disagrees with this is a new version
    of the fee model, not an edit of this one.
    """
    if fee_pct < 0:
        raise ValueError("fee_pct cannot be negative")
    with localcontext(CONTEXT):
        return budget_sol / (Decimal(1) + fee_pct / HUNDRED)


@dataclass(frozen=True, slots=True)
class BuyQuote:
    """What a buy of a SOL budget would do, fees and our own impact included."""

    tokens: Decimal
    curve_cost_sol: Decimal
    fee_sol: Decimal
    total_sol: Decimal
    average_price_sol: Decimal
    """``total_sol / tokens`` — the honest price paid, fee included."""
    reserves_after: CurveReserves
    marginal_price_after_sol: Decimal


@dataclass(frozen=True, slots=True)
class SellQuote:
    """What a sell of ``tokens`` would yield now, fees and our own impact included."""

    tokens: Decimal
    curve_proceeds_sol: Decimal
    fee_sol: Decimal
    net_sol: Decimal
    average_price_sol: Decimal
    reserves_after: CurveReserves
    marginal_price_after_sol: Decimal


def quote_buy(reserves: CurveReserves, budget_sol: Decimal, fee_pct: Decimal) -> BuyQuote:
    """Price a buy of ``budget_sol`` against ``reserves`` at ``fee_pct``."""
    _positive(budget_sol, "budget_sol")
    curve_cost = curve_input_from_budget(budget_sol, fee_pct)
    tokens = tokens_for_sol(reserves, curve_cost)
    fee = fee_amount(curve_cost, fee_pct)
    after = reserves_after_buy(reserves, tokens)
    with localcontext(CONTEXT):
        total = curve_cost + fee
        return BuyQuote(
            tokens=tokens,
            curve_cost_sol=curve_cost,
            fee_sol=fee,
            total_sol=total,
            average_price_sol=total / tokens,
            reserves_after=after,
            marginal_price_after_sol=marginal_price_sol(after),
        )


def quote_sell(reserves: CurveReserves, tokens: Decimal, fee_pct: Decimal) -> SellQuote:
    """Price a sell of ``tokens`` against ``reserves`` at ``fee_pct``."""
    proceeds = sell_proceeds(reserves, tokens)
    fee = fee_amount(proceeds, fee_pct)
    after = reserves_after_sell(reserves, tokens)
    with localcontext(CONTEXT):
        net = proceeds - fee
        return SellQuote(
            tokens=tokens,
            curve_proceeds_sol=proceeds,
            fee_sol=fee,
            net_sol=net,
            average_price_sol=net / tokens,
            reserves_after=after,
            marginal_price_after_sol=marginal_price_sol(after),
        )
