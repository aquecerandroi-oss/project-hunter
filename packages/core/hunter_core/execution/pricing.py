"""The declared simulation parameters, and the money arithmetic they govern.

Split out of :mod:`hunter_core.execution.paper` so that the adapter reads as the
*flow* of one attempt (filters → eligible book → one walk → report) while the
numbers that decide how much things cost live here, each as a pure function with
its rounding written down:

- :func:`taker_fee` — charged in the asset really received (base on a buy, quote
  on a sell) and rounded **up**: a cost rounded to the nearest is sometimes
  cheaper than reality, and this number feeds a simulated result;
- :func:`apply_model_slippage` — the declared extra adjustment, always
  **against** the trade, kept apart from what the book itself did;
- :func:`slippage_vs_plan` — positive is adverse. Nothing here corrects a fill
  back to the planned stop;
- :func:`mark_price` and :func:`residual_for` — a price to *value* a leftover
  with, never a price to fill at, and a value that is ``None`` **with a reason**
  when no valid price exists.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any

from pydantic import Field

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import NormalizedTrade
from hunter_core.execution.adapter import (
    ExecutionModel,
    FeeCharge,
    FeeSchedule,
    Residual,
    SpotFilters,
)
from hunter_core.execution.book_walk import BookWalk
from hunter_core.execution.triggers import MarkingPolicy
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "EXECUTION_POLICY_VERSION",
    "ExecutionPolicy",
    "apply_model_slippage",
    "untradable_reason",
    "mark_price",
    "residual_for",
    "slippage_vs_plan",
    "taker_fee",
]

EXECUTION_POLICY_VERSION = "paper_market_v1"
"""Only MARKET orders, one attempt, taker fees. Versioned so a result is
comparable to the rules that produced it."""

_BPS = Decimal(10_000)


class ExecutionPolicy(ExecutionModel):
    """The declared simulation parameters. Every one of them travels on the report."""

    version: str = EXECUTION_POLICY_VERSION
    latency_ms: int = Field(default=150, ge=0)
    """PIPELINE.md §8: the book used is the one **after** this delay, which
    penalises fast markets instead of flattering them."""
    max_book_age_s: Decimal = Field(default=Decimal(10), gt=0)
    extra_slippage_bps: Decimal = Field(default=Decimal(0), ge=0)
    """A declared adverse adjustment on top of the walk, published separately so
    the book's own cost is never confused with our model's."""
    base_precision: int = Field(default=8, ge=0)
    quote_precision: int = Field(default=8, ge=0)
    marking_policy: MarkingPolicy = MarkingPolicy()

    @property
    def latency(self) -> timedelta:
        return timedelta(milliseconds=self.latency_ms)

    @property
    def max_book_age(self) -> timedelta:
        return timedelta(milliseconds=int(self.max_book_age_s * 1000))

    @property
    def base_quantum(self) -> Decimal:
        return Decimal(1).scaleb(-self.base_precision)

    @property
    def quote_quantum(self) -> Decimal:
        return Decimal(1).scaleb(-self.quote_precision)


def apply_model_slippage(
    walk: BookWalk, *, side: OrderSide, policy: ExecutionPolicy
) -> tuple[Decimal, Decimal]:
    """``(gross, vwap)`` after the declared adjustment — worse, never better."""
    gross, vwap = walk.gross_quote, walk.vwap or Decimal(0)
    bps = policy.extra_slippage_bps
    if bps <= 0:
        return gross, vwap
    with localcontext(CONTEXT):
        step = bps / _BPS
        factor = Decimal(1) + step if side is OrderSide.BUY else Decimal(1) - step
        return (
            (gross * factor).quantize(policy.quote_quantum),
            (vwap * factor).quantize(policy.quote_quantum),
        )


def taker_fee(
    fees: FeeSchedule,
    *,
    asset: str,
    base_qty: Decimal,
    gross: Decimal,
    vwap: Decimal,
    policy: ExecutionPolicy,
) -> FeeCharge:
    """The taker fee in the asset it is charged in, rounded up."""
    rate = fees.taker_rate
    with localcontext(CONTEXT):
        if asset == "base":
            qty = (base_qty * rate).quantize(policy.base_quantum, rounding=ROUND_CEILING)
            equivalent = (qty * vwap).quantize(policy.quote_quantum, rounding=ROUND_CEILING)
            return FeeCharge(
                asset="base", qty=qty, rate=rate, source=fees.source, quote_equivalent=equivalent
            )
        qty = (gross * rate).quantize(policy.quote_quantum, rounding=ROUND_CEILING)
    return FeeCharge(asset="quote", qty=qty, rate=rate, source=fees.source)


def slippage_vs_plan(
    planned: Decimal | None,
    filled: Decimal,
    gross: Decimal,
    *,
    side: OrderSide,
    policy: ExecutionPolicy,
) -> dict[str, Any]:
    """What the attempt cost against what it planned. Positive is adverse."""
    if planned is None or filled <= 0:
        return {"slippage_vs_plan_quote": None, "slippage_vs_plan_bps": None}
    with localcontext(CONTEXT):
        planned_quote = planned * filled
        delta = gross - planned_quote if side is OrderSide.BUY else planned_quote - gross
        return {
            "slippage_vs_plan_quote": delta.quantize(policy.quote_quantum),
            "slippage_vs_plan_bps": (delta / planned_quote * _BPS).quantize(policy.quote_quantum),
        }


def mark_price(
    last_trade: NormalizedTrade | None,
    avg_price: Decimal | None,
    *,
    now: Any,
    policy: ExecutionPolicy,
) -> tuple[Decimal | None, str]:
    """A price to value a residual with, with its provenance — or none, with why."""
    if last_trade is not None:
        age = Decimal((now - last_trade.ts).total_seconds())
        if 0 <= age <= policy.marking_policy.max_trade_age_s:
            return last_trade.price, f"last_spot_trade:{last_trade.trade_id}"
    if avg_price is not None:
        return avg_price, "exchange_avg_price"
    return None, "unavailable: no valid spot trade and no average price"


def residual_for(
    qty: Decimal,
    reason: str,
    mark: tuple[Decimal | None, str] | Decimal | None,
    *,
    policy: ExecutionPolicy,
) -> Residual:
    """The leftover the exchange will not let us sell: quantity always, value when known."""
    price, source = mark if isinstance(mark, tuple) else (mark, "attempt_vwap")
    value = None
    if price is not None:
        with localcontext(CONTEXT):
            value = (qty * price).quantize(policy.quote_quantum)
    return Residual(
        qty=qty,
        reason="below_min_qty" if reason in ("min_qty", "below_min_qty") else reason,
        value_quote=value,
        valuation_price=price,
        valuation_source=source,
    )


def untradable_reason(qty: Decimal, filters: SpotFilters, price: Decimal | None) -> str | None:
    """Is this leftover *too small to sell*, and only that?

    A refusal for a per-order **maximum** is not dust: nine units under a cap of
    five are sellable in two attempts, and calling them a residual would retire
    the protection of a position that can still be closed (Astra, round 2).
    A missing price never proves a minimum is breached either.
    """
    rounded = filters.round_qty_down(qty)
    if rounded < filters.effective_min_qty:
        return "below_min_qty"
    verdict = filters.check_market_order(rounded, avg_price=price, last_price=price)
    if verdict.ok or verdict.reason not in ("min_qty", "min_notional"):
        return None
    return "below_min_qty" if verdict.reason == "min_qty" else "below_min_notional"
