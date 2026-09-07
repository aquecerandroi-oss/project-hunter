"""Binance **SPOT** symbol filters, as they apply to a MARKET order.

``docs/plans/M3.md`` T3.0: the paper wallet executes on spot, so a simulated
fill is only honest if it obeys the same filters the exchange would enforce
on a real MARKET order. This module parses them from one
``exchangeInfo.symbols[i]`` entry and answers two questions with no IO and
no guessing:

- :meth:`SpotMarketFilters.round_qty_down` - the largest valid quantity not
  greater than the requested one (``LOT_SIZE.stepSize`` and, when the symbol
  publishes a coarser one, ``MARKET_LOT_SIZE.stepSize``). Never rounds up: a
  rounded-up quantity is either an exchange rejection or a position larger
  than the Risk Engine approved.
- :meth:`SpotMarketFilters.check_market_order` - whether that quantity
  passes ``LOT_SIZE``/``MARKET_LOT_SIZE`` and the ``NOTIONAL`` floor. For a
  MARKET order Binance evaluates the notional against the **average price of
  the last ``avgPriceMins`` minutes** (``GET /api/v3/avgPrice``), not the
  last trade; when that average is not available the check refuses
  (``avg_price_unavailable``) instead of substituting a price the filter
  never named.

``PERCENT_PRICE_BY_SIDE`` is parsed and exposed as
:meth:`SpotMarketFilters.price_band`, but it is **our own** sanity band for
a simulated fill that walked the book - Binance applies that filter to a
limit price, and never rejects a MARKET order for it. Labelled here so the
distinction cannot quietly become "the exchange said so".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from hunter_core.domain.enums import OrderSide
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance_spot.identity import EXCHANGE

__all__ = ["MarketOrderCheck", "SpotMarketFilters", "parse_filters"]

_ZERO = Decimal(0)


def _entry(raw: dict[str, Any], filter_type: str) -> dict[str, Any] | None:
    for flt in raw.get("filters", []):
        if flt.get("filterType") == filter_type:
            return flt
    return None


def _dec(value: Any, *, field: str) -> Decimal:
    """Binance sends every number in a filter as a JSON string; a float here
    would silently lose precision, so it is malformed, not coerced."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise MalformedMessage(
            f"expected a decimal string for {field!r}, got {value!r}", exchange=EXCHANGE
        )
    try:
        return Decimal(value)
    except ArithmeticError as exc:
        raise MalformedMessage(
            f"invalid decimal for {field!r}: {value!r}", exchange=EXCHANGE
        ) from exc


def _dec_or_none(value: Any, *, field: str) -> Decimal | None:
    return None if value is None else _dec(value, field=field)


@dataclass(frozen=True)
class MarketOrderCheck:
    """Verdict for one candidate MARKET order quantity.

    ``qty`` is always the quantity **after** step rounding (what would
    actually be sent), even when ``ok`` is false, so the caller can log the
    real refused size. ``reason`` is ``None`` only when ``ok`` is true.
    """

    ok: bool
    qty: Decimal
    notional: Decimal | None = None
    reason: str | None = None


@dataclass(frozen=True)
class SpotMarketFilters:
    """Every filter a spot MARKET order is judged by, plus the price band."""

    symbol: str
    tick_size: Decimal
    min_price: Decimal | None
    max_price: Decimal | None
    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    market_step_size: Decimal | None = None
    market_min_qty: Decimal | None = None
    market_max_qty: Decimal | None = None
    min_notional: Decimal | None = None
    apply_min_to_market: bool = False
    max_notional: Decimal | None = None
    apply_max_to_market: bool = False
    avg_price_mins: int | None = None
    bid_multiplier_up: Decimal | None = None
    bid_multiplier_down: Decimal | None = None
    ask_multiplier_up: Decimal | None = None
    ask_multiplier_down: Decimal | None = None

    @property
    def effective_step_size(self) -> Decimal:
        """The coarser of ``LOT_SIZE`` and ``MARKET_LOT_SIZE`` steps.

        ``MARKET_LOT_SIZE.stepSize == 0`` means "not enforced for market
        orders" (the common case, e.g. BTCUSDT), not "any quantity".
        """
        market = self.market_step_size or _ZERO
        return market if market > self.step_size else self.step_size

    @property
    def effective_min_qty(self) -> Decimal:
        market = self.market_min_qty or _ZERO
        return market if market > self.min_qty else self.min_qty

    @property
    def effective_max_qty(self) -> Decimal:
        market = self.market_max_qty
        if market is None or market <= _ZERO:
            return self.max_qty
        return market if market < self.max_qty else self.max_qty

    def round_qty_down(self, qty: Decimal) -> Decimal:
        """Floor ``qty`` to :attr:`effective_step_size` (never up)."""
        step = self.effective_step_size
        if step <= _ZERO:
            return qty
        return (qty / step).to_integral_value(rounding=ROUND_FLOOR) * step

    def round_price(self, price: Decimal, *, side: OrderSide) -> Decimal:
        """Snap ``price`` to ``PRICE_FILTER.tickSize`` **against** the trade:
        a buy pays the higher tick, a sell receives the lower one."""
        if self.tick_size <= _ZERO:
            return price
        rounding = ROUND_CEILING if side is OrderSide.BUY else ROUND_FLOOR
        return (price / self.tick_size).to_integral_value(rounding=rounding) * self.tick_size

    def price_band(self, side: OrderSide, *, avg_price: Decimal) -> tuple[Decimal, Decimal]:
        """``PERCENT_PRICE_BY_SIDE`` band around ``avg_price`` for ``side``.

        Our own guard for an implausible simulated fill (see the module
        docstring) - never an exchange MARKET rejection. Falls back to the
        average itself when the symbol publishes no multipliers.
        """
        if side is OrderSide.BUY:
            down, up = self.bid_multiplier_down, self.bid_multiplier_up
        else:
            down, up = self.ask_multiplier_down, self.ask_multiplier_up
        low = avg_price * down if down is not None else avg_price
        high = avg_price * up if up is not None else avg_price
        return low, high

    def _reference_price(
        self, avg_price: Decimal | None, last_price: Decimal | None
    ) -> Decimal | None:
        """What the ``NOTIONAL`` filter measures a MARKET order against.

        ``avgPriceMins == 0`` is Binance's own "use the last price" case;
        anything else means the 5-minute average from ``/api/v3/avgPrice``.
        """
        if self.avg_price_mins == 0:
            return last_price
        return avg_price

    def check_market_order(
        self,
        qty: Decimal,
        *,
        avg_price: Decimal | None = None,
        last_price: Decimal | None = None,
    ) -> MarketOrderCheck:
        """Round ``qty`` to the step and judge it against every MARKET filter."""
        rounded = self.round_qty_down(qty)
        if rounded < self.effective_min_qty:
            return MarketOrderCheck(ok=False, qty=rounded, reason="min_qty")
        if rounded > self.effective_max_qty:
            return MarketOrderCheck(ok=False, qty=rounded, reason="max_qty")
        needs_notional = (self.min_notional is not None and self.apply_min_to_market) or (
            self.max_notional is not None and self.apply_max_to_market
        )
        if not needs_notional:
            return MarketOrderCheck(ok=True, qty=rounded)
        reference = self._reference_price(avg_price, last_price)
        if reference is None:
            return MarketOrderCheck(ok=False, qty=rounded, reason="avg_price_unavailable")
        notional = rounded * reference
        if (
            self.min_notional is not None
            and self.apply_min_to_market
            and notional < self.min_notional
        ):
            return MarketOrderCheck(ok=False, qty=rounded, notional=notional, reason="min_notional")
        if (
            self.max_notional is not None
            and self.apply_max_to_market
            and notional > self.max_notional
        ):
            return MarketOrderCheck(ok=False, qty=rounded, notional=notional, reason="max_notional")
        return MarketOrderCheck(ok=True, qty=rounded, notional=notional)

    def to_metadata(self) -> dict[str, Any]:
        """The market-order-specific filters for ``NormalizedMarket.metadata``.

        ``docs/EXCHANGE_INTEGRATION.md`` §2: raw exchange detail only travels
        outside this package inside an explicitly labelled ``metadata`` key
        (``spot_market_filters``). Decimals are serialized as strings so the
        dict survives JSON/Redis without ever becoming a float.
        """

        def _s(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "market_step_size": _s(self.market_step_size),
            "market_min_qty": _s(self.market_min_qty),
            "market_max_qty": _s(self.market_max_qty),
            "apply_min_to_market": self.apply_min_to_market,
            "max_notional": _s(self.max_notional),
            "apply_max_to_market": self.apply_max_to_market,
            "avg_price_mins": self.avg_price_mins,
            "bid_multiplier_up": _s(self.bid_multiplier_up),
            "bid_multiplier_down": _s(self.bid_multiplier_down),
            "ask_multiplier_up": _s(self.ask_multiplier_up),
            "ask_multiplier_down": _s(self.ask_multiplier_down),
        }


def parse_filters(raw: dict[str, Any]) -> SpotMarketFilters:
    """One ``exchangeInfo.symbols[i]`` entry -> :class:`SpotMarketFilters`."""
    symbol = str(raw.get("symbol", ""))
    lot = _entry(raw, "LOT_SIZE")
    if lot is None:
        raise MalformedMessage(f"{symbol}: missing LOT_SIZE filter", exchange=EXCHANGE)
    price = _entry(raw, "PRICE_FILTER") or {}
    market_lot = _entry(raw, "MARKET_LOT_SIZE") or {}
    notional = _entry(raw, "NOTIONAL")
    legacy_notional = _entry(raw, "MIN_NOTIONAL")
    percent = _entry(raw, "PERCENT_PRICE_BY_SIDE") or {}
    min_notional, apply_min, max_notional, apply_max, avg_mins = _notional_fields(
        notional, legacy_notional
    )
    if avg_mins is None and "avgPriceMins" in percent:
        avg_mins = int(percent["avgPriceMins"])
    return SpotMarketFilters(
        symbol=symbol,
        tick_size=_dec(price.get("tickSize", "0"), field="tickSize"),
        min_price=_dec_or_none(price.get("minPrice"), field="minPrice"),
        max_price=_dec_or_none(price.get("maxPrice"), field="maxPrice"),
        step_size=_dec(lot["stepSize"], field="stepSize"),
        min_qty=_dec(lot["minQty"], field="minQty"),
        max_qty=_dec(lot["maxQty"], field="maxQty"),
        market_step_size=_dec_or_none(market_lot.get("stepSize"), field="market.stepSize"),
        market_min_qty=_dec_or_none(market_lot.get("minQty"), field="market.minQty"),
        market_max_qty=_dec_or_none(market_lot.get("maxQty"), field="market.maxQty"),
        min_notional=min_notional,
        apply_min_to_market=apply_min,
        max_notional=max_notional,
        apply_max_to_market=apply_max,
        avg_price_mins=avg_mins,
        bid_multiplier_up=_dec_or_none(percent.get("bidMultiplierUp"), field="bidMultiplierUp"),
        bid_multiplier_down=_dec_or_none(
            percent.get("bidMultiplierDown"), field="bidMultiplierDown"
        ),
        ask_multiplier_up=_dec_or_none(percent.get("askMultiplierUp"), field="askMultiplierUp"),
        ask_multiplier_down=_dec_or_none(
            percent.get("askMultiplierDown"), field="askMultiplierDown"
        ),
    )


def _notional_fields(
    notional: dict[str, Any] | None, legacy: dict[str, Any] | None
) -> tuple[Decimal | None, bool, Decimal | None, bool, int | None]:
    """``NOTIONAL`` (current) or ``MIN_NOTIONAL`` (legacy, ``applyToMarket``)."""
    if notional is not None:
        avg_mins = notional.get("avgPriceMins")
        return (
            _dec_or_none(notional.get("minNotional"), field="minNotional"),
            bool(notional.get("applyMinToMarket", False)),
            _dec_or_none(notional.get("maxNotional"), field="maxNotional"),
            bool(notional.get("applyMaxToMarket", False)),
            None if avg_mins is None else int(avg_mins),
        )
    if legacy is not None:
        avg_mins = legacy.get("avgPriceMins")
        return (
            _dec_or_none(legacy.get("minNotional"), field="minNotional"),
            bool(legacy.get("applyToMarket", False)),
            None,
            False,
            None if avg_mins is None else int(avg_mins),
        )
    return None, False, None, False, None
