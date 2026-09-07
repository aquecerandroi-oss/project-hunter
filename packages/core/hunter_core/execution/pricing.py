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
  when no valid price exists;
- :func:`price_band_breach` — ``PERCENT_PRICE_BY_SIDE`` as **our** sanity band on
  a simulated fill (T3.0a §5: Binance applies that filter to a limit price and
  never rejects a MARKET order for it);
- :func:`eligible_for`, :func:`reference_fields` and :func:`policy_versions` —
  the declared parameters applied to one snapshot, kept next to the parameters
  themselves instead of inside the adapter's flow.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any

from pydantic import Field

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import NormalizedOrderBook, NormalizedTrade
from hunter_core.execution.adapter import (
    ExecutionModel,
    FeeCharge,
    FeeSchedule,
    Residual,
    SpotFilters,
)
from hunter_core.execution.book_walk import (
    BOOK_POLICY_VERSION,
    BookVerdict,
    BookWalk,
    eligible_book,
)
from hunter_core.execution.triggers import MARKING_POLICY_VERSION, MarkingPolicy, usable_trade
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "EXECUTION_POLICY_VERSION",
    "ExecutionPolicy",
    "apply_model_slippage",
    "eligible_for",
    "untradable_reason",
    "mark_price",
    "policy_versions",
    "price_band_breach",
    "reference_fields",
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
    now: datetime,
    policy: ExecutionPolicy,
) -> tuple[Decimal | None, str]:
    """A price to value a residual with, with its provenance — or none, with why.

    Validity is :func:`~hunter_core.execution.triggers.usable_trade` and nothing
    else. This function used to re-implement the age rule and, missing the
    ``received_at <= now`` half of it, valued a residual with a print our socket
    had not seen (review of 2026-09-07, item 10). One definition, one place.
    """
    usable, _ = usable_trade(last_trade, now=now, policy=policy.marking_policy)
    if usable is not None:
        return usable.price, f"last_spot_trade:{usable.trade_id}"
    if avg_price is not None:
        return avg_price, "exchange_avg_price"
    return None, "unavailable: no valid spot trade and no average price"


def price_band_breach(
    filters: SpotFilters,
    *,
    side: OrderSide,
    fill_price: Decimal | None,
    avg_price: Decimal | None,
) -> bool:
    """Did the simulated fill land outside ``PERCENT_PRICE_BY_SIDE``?

    Measured against the **exchange average price**, the reference Binance names
    for that filter — never against the last trade, which moves with the very
    book we are suspicious of. Without an average there is no band, and a symbol
    that publishes no multipliers gets ``(avg, avg)`` back, which is not a band
    either: treating it as one would refuse every fill that is not exactly the
    average, which is every fill.
    """
    if fill_price is None or avg_price is None or avg_price <= 0:
        return False
    low, high = filters.price_band(side, avg_price=avg_price)
    if not low < avg_price < high:
        return False
    return fill_price < low or fill_price > high


def eligible_for(
    policy: ExecutionPolicy,
    book: NormalizedOrderBook | None,
    *,
    decision_at: datetime,
    now: datetime,
    side: OrderSide,
    previous_sequence: int | None = None,
    market: tuple[str, str] | None = None,
) -> BookVerdict:
    """:func:`~hunter_core.execution.book_walk.eligible_book` under this policy."""
    return eligible_book(
        book,
        decision_at=decision_at,
        latency=policy.latency,
        now=now,
        max_age=policy.max_book_age,
        previous_sequence=previous_sequence,
        side=side,
        market=market,
    )


def reference_fields(
    usable: NormalizedTrade | None,
    avg_price: Decimal | None,
    *,
    now: datetime,
    policy: ExecutionPolicy,
) -> dict[str, Any]:
    """Which price the filters were judged against — published, not implied."""
    price, source = mark_price(usable, avg_price, now=now, policy=policy)
    return {"filter_reference_price": price, "filter_reference_source": source}


def policy_versions(policy: ExecutionPolicy, now: datetime) -> dict[str, Any]:
    """The three versioned rule sets every report carries, plus the instant."""
    return {
        "executed_at": now,
        "latency_ms": policy.latency_ms,
        "marking_policy_version": MARKING_POLICY_VERSION,
        "book_policy_version": BOOK_POLICY_VERSION,
        "execution_policy_version": policy.version,
    }


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
