"""Small factories for ``Normalized*`` fixtures — keeps the test bodies
focused on what each test actually asserts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import MarketStatus, MarketType, OrderSide, Timeframe
from hunter_core.domain.market import (
    BookLevel,
    NormalizedCandle,
    NormalizedFunding,
    NormalizedLiquidation,
    NormalizedMarket,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
    align_open_time,
    close_time_for,
)
from hunter_core.domain.types import utcnow

EXCHANGE = "fake"


def market(symbol: str, base: str, quote: str = "USDT", **overrides: object) -> NormalizedMarket:
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "market_type": MarketType.PERPETUAL,
        "base": base,
        "quote": quote,
        "status": MarketStatus.ACTIVE,
        "tick_size": Decimal("0.01"),
        "step_size": Decimal("0.001"),
        "min_notional": Decimal("5"),
        "contract_size": Decimal("1"),
        "max_leverage": 20,
        **overrides,
    }
    return NormalizedMarket.model_validate(fields)


def ticker(symbol: str, last: str, **overrides: object) -> NormalizedTicker:
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "last": Decimal(last),
        "bid": Decimal(last) - Decimal("0.01"),
        "ask": Decimal(last) + Decimal("0.01"),
        "volume_24h": Decimal("1000"),
        "quote_volume_24h": Decimal("1000000"),
        **overrides,
    }
    return NormalizedTicker.model_validate(fields)


def ticker_rest(symbol: str, last: str, **overrides: object) -> NormalizedTicker:
    """A ticker shaped like Binance's ``GET /fapi/v1/ticker/24hr`` -- no
    bid/ask, only that endpoint never carries them
    (``binance/normalize.py::parse_ticker_24h``)."""
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "last": Decimal(last),
        "volume_24h": Decimal("1000"),
        "quote_volume_24h": Decimal("1000000"),
        "high_24h": Decimal(last) + Decimal("10"),
        "low_24h": Decimal(last) - Decimal("10"),
        "change_24h_pct": Decimal("1.5"),
        **overrides,
    }
    return NormalizedTicker.model_validate(fields)


def ticker_ws(symbol: str, last: str, **overrides: object) -> NormalizedTicker:
    """A ticker shaped like Binance's ``bookTicker`` stream -- no 24h volume,
    only bid/ask/quantities (``binance/normalize.py::parse_book_ticker``)."""
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "last": Decimal(last),
        "bid": Decimal(last) - Decimal("0.01"),
        "ask": Decimal(last) + Decimal("0.01"),
        "bid_qty": Decimal("5"),
        "ask_qty": Decimal("3"),
        **overrides,
    }
    return NormalizedTicker.model_validate(fields)


def trade(
    symbol: str, price: str, qty: str, *, side: OrderSide = OrderSide.BUY, **overrides: object
) -> NormalizedTrade:
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "trade_id": overrides.pop("trade_id", "1"),
        "price": Decimal(price),
        "qty": Decimal(qty),
        "side": side,
        **overrides,
    }
    return NormalizedTrade.model_validate(fields)


def order_book(symbol: str, best_bid: str = "100", best_ask: str = "100.1") -> NormalizedOrderBook:
    return NormalizedOrderBook.model_validate(
        {
            "exchange": EXCHANGE,
            "symbol": symbol,
            "ts": utcnow(),
            "bids": [BookLevel(price=Decimal(best_bid), qty=Decimal("5"))],
            "asks": [BookLevel(price=Decimal(best_ask), qty=Decimal("2"))],
            "is_snapshot": True,
        }
    )


def candle(
    symbol: str, open_time: Any = None, *, is_final: bool = True, **overrides: object
) -> NormalizedCandle:
    open_time = open_time or align_open_time(utcnow(), Timeframe.M1)
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "timeframe": Timeframe.M1,
        "open_time": open_time,
        "close_time": close_time_for(open_time, Timeframe.M1),
        "open": Decimal("100"),
        "high": Decimal("101"),
        "low": Decimal("99"),
        "close": Decimal("100.5"),
        "volume": Decimal("10"),
        "is_final": is_final,
        **overrides,
    }
    return NormalizedCandle.model_validate(fields)


def funding(
    symbol: str, rate: str = "0.0001", next_funding_time: Any = None, **overrides: object
) -> NormalizedFunding:
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "funding_rate": Decimal(rate),
        "next_funding_time": next_funding_time,
        "mark_price": Decimal("100"),
        **overrides,
    }
    return NormalizedFunding.model_validate(fields)


def open_interest(symbol: str, value: str = "1000", **overrides: object) -> NormalizedOpenInterest:
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "open_interest": Decimal(value),
        **overrides,
    }
    return NormalizedOpenInterest.model_validate(fields)


def liquidation(
    symbol: str, price: str = "100", qty: str = "1", **overrides: object
) -> NormalizedLiquidation:
    fields = {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "ts": utcnow(),
        "side": OrderSide.SELL,
        "qty": Decimal(qty),
        "price": Decimal(price),
        **overrides,
    }
    return NormalizedLiquidation.model_validate(fields)
