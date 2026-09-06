"""Microstructure: spread, book imbalance, taker pressure, trade velocity.

These read the book snapshot and the trade tape, never a candle, so they carry
**no** ``_live`` suffix — that suffix means "includes the candle still forming"
(agreed with Astra, T2.2 design review, 3b). What they do carry is their own
observation timestamp and coverage in the vector's provenance: a book feature
computed from a 40-second-old snapshot is ``degraded``, and a trade window the
ring buffer cannot prove it covers is ``insufficient_coverage`` rather than a
comfortable zero.

Book features are suffixed ``_20`` (``docs/plans/M2.md`` §Universo/book): the
depth is part of the name because the same formula over 5 or 25 levels is a
different number.

``spread_pct`` is a **fraction** (T1.1c). Note that
``NormalizedTicker.spread_pct`` in ``hunter_core`` is still ×100 — this module
does not use it, and the follow-up that reconciles that helper is T1.1c's, not
T2.2's.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import Literal

from hunter_core.domain.enums import FeatureCategory, OrderSide
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.context import (
    INPUT_BOOK,
    INPUT_TRADES,
    BookSnapshot,
    MarketContext,
    SourceEntry,
    TapeTrade,
)
from hunter_indicators.features.definitions import FeatureCalculator, FeatureDefinition
from hunter_indicators.features.price import label_for
from hunter_indicators.features.quality import source_reason
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue, Reason
from hunter_indicators.features.windows import trades_between

BOOK_DEPTH = 20


def _quantity(levels: Sequence[tuple[Decimal, Decimal]], depth: int) -> Decimal:
    with localcontext(CONTEXT):
        return sum((qty for _, qty in levels[:depth]), start=Decimal(0))


def usable_book(entry: SourceEntry[BookSnapshot]) -> tuple[BookSnapshot | None, Reason | None]:
    """The snapshot, or why no book feature may be computed from it.

    A snapshot whose best ask is at or below its best bid is not a tighter
    market, it is a quote no exchange published (a torn merge of two updates, a
    stale side, a bad decode). ``decode_book`` already refuses a snapshot with
    one unparsable level for the same reason: corruption must look like an
    **absent** book, never like a different one, because a "spread" of -1 % or
    an imbalance measured over a torn side would be a number about the bug.

    It takes the whole entry, not the value, so the loader's own verdict reaches
    the feature: a book the decoder refused as ``crossed`` says
    ``corrupt_input`` here too, instead of arriving as "Redis had no book"
    (Astra, fix-pass review, must-fix 2).
    """
    book = entry.value
    if book is None:
        return None, source_reason(entry.reason)
    if not book.bids or not book.asks:
        return None, Reason.MISSING_INPUT
    if book.asks[0][0] <= book.bids[0][0]:
        return None, Reason.CORRUPT_INPUT
    return book, None


@dataclass(frozen=True, slots=True)
class SpreadPct:
    """``(ask - bid) / mid`` from the top of the book, as a fraction."""

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key="spread_pct",
            version=1,
            category=FeatureCategory.MICROSTRUCTURE,
            inputs=(INPUT_BOOK,),
            params={"unit": "fraction"},
            description="best ask minus best bid over the mid price, as a fraction",
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        book, refusal = usable_book(ctx.book)
        if book is None:
            return FeatureValue.unavailable(
                definition.key, refusal or Reason.MISSING_INPUT, inputs=definition.inputs
            )
        bid, ask = book.bids[0][0], book.asks[0][0]
        with localcontext(CONTEXT):
            mid = (bid + ask) / 2
            if mid <= 0:
                return FeatureValue.unavailable(
                    definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
                )
            value = (ask - bid) / mid
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class BookImbalance:
    """``(bid_qty - ask_qty) / (bid_qty + ask_qty)`` over the top ``depth`` levels."""

    depth: int = BOOK_DEPTH

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"orderbook_imbalance_{self.depth}",
            version=1,
            category=FeatureCategory.MICROSTRUCTURE,
            inputs=(INPUT_BOOK,),
            params={"depth": self.depth},
            description=(
                f"bid quantity minus ask quantity over their sum, top {self.depth} levels; "
                "+1 is all bid, -1 is all ask"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        book, refusal = usable_book(ctx.book)
        if book is None:
            return FeatureValue.unavailable(
                definition.key, refusal or Reason.MISSING_INPUT, inputs=definition.inputs
            )
        if len(book.bids) < self.depth or len(book.asks) < self.depth:
            # 7 bids against 20 asks is a ratio of level counts, not of pressure
            # at depth 20: the key promises `depth` levels a side (cross review,
            # must-fix 2). A thin book is a fact, and it is reported as one.
            return FeatureValue.unavailable(
                definition.key, Reason.INSUFFICIENT_SAMPLE, inputs=definition.inputs
            )
        bid_qty = _quantity(book.bids, self.depth)
        ask_qty = _quantity(book.asks, self.depth)
        with localcontext(CONTEXT):  # the sum rounds under the ambient context otherwise
            total = bid_qty + ask_qty
        if total <= 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = (bid_qty - ask_qty) / total
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def _side_volume(trades: Sequence[TapeTrade], side: OrderSide) -> Decimal:
    with localcontext(CONTEXT):
        return sum((t.qty for t in trades if t.side is side), start=Decimal(0))


@dataclass(frozen=True, slots=True)
class TakerPressure:
    """Taker volume of one side over the total traded volume in the window.

    ``side`` is the **aggressor**: the Binance adapter maps ``isBuyerMaker`` to
    ``SELL`` (``hunter_exchanges/binance/streams.py:152``), so ``BUY`` here means
    a buyer lifting the offer.
    """

    side: Literal["buy", "sell"]
    window_minutes: int = 5

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"{self.side}_pressure_{label_for(self.window_minutes)}",
            version=1,
            category=FeatureCategory.MICROSTRUCTURE,
            inputs=(INPUT_TRADES,),
            params={"window_minutes": self.window_minutes, "side": self.side},
            description=(
                f"taker {self.side} volume over total traded volume in the last "
                f"{self.window_minutes} minutes"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        start = ctx.as_of - timedelta(minutes=self.window_minutes)
        window = trades_between(ctx.trades, start, ctx.as_of)
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.MISSING_INPUT, inputs=definition.inputs
            )
        buys = _side_volume(window.trades, OrderSide.BUY)
        sells = _side_volume(window.trades, OrderSide.SELL)
        with localcontext(CONTEXT):  # the sum rounds under the ambient context otherwise
            total = buys + sells
        if total <= 0:
            # nothing traded: the ratio is undefined, not 0.5 and not 0
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = (buys if self.side == "buy" else sells) / total
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class TradeVelocity:
    """Trades per second over the window — a rate, not a count."""

    window_seconds: int = 60

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"trade_velocity_{label_for(self.window_seconds // 60)}",
            version=1,
            category=FeatureCategory.MICROSTRUCTURE,
            inputs=(INPUT_TRADES,),
            params={"window_seconds": self.window_seconds},
            description=f"trades per second over the last {self.window_seconds} seconds",
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        start = ctx.as_of - timedelta(seconds=self.window_seconds)
        window = trades_between(ctx.trades, start, ctx.as_of)
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.MISSING_INPUT, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = Decimal(len(window.trades)) / Decimal(self.window_seconds)
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def micro_calculators() -> tuple[FeatureCalculator, ...]:
    """The frozen v1 microstructure set, ordered by key."""
    calculators: list[FeatureCalculator] = [
        SpreadPct(),
        BookImbalance(depth=BOOK_DEPTH),
        TakerPressure(side="buy", window_minutes=5),
        TakerPressure(side="sell", window_minutes=5),
        TradeVelocity(window_seconds=60),
    ]
    return tuple(sorted(calculators, key=lambda c: c.definition.key))


__all__ = [
    "BOOK_DEPTH",
    "BookImbalance",
    "SpreadPct",
    "TakerPressure",
    "TradeVelocity",
    "micro_calculators",
    "usable_book",
]
