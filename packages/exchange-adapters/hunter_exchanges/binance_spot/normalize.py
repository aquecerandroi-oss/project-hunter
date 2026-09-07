"""Pure functions: raw Binance **SPOT** REST payloads -> ``Normalized*`` models.

Sibling of :mod:`hunter_exchanges.binance.normalize` (USDS-M Futures), which
this module reuses wherever the wire format is genuinely identical
(:func:`~hunter_exchanges.binance.normalize.to_decimal`,
:func:`~hunter_exchanges.binance.normalize.ms_to_datetime`, the kline row
parser, the server clock) and never where it only looks identical. The real
differences on ``/api/v3``, all confirmed against recorded responses in
``testing/fixtures/spot_*.json``:

- ``exchangeInfo.symbols[i]`` has no ``contractType``; the spot lifecycle is
  ``TRADING``/``BREAK``/``HALT``/``PENDING_TRADING``/``END_OF_DAY``, and the
  notional filter is ``NOTIONAL`` (with ``applyMinToMarket``) rather than
  ``MIN_NOTIONAL``;
- ``ticker/24hr`` *does* carry bid/ask (the USDS-M one does not);
- ``depth`` carries ``lastUpdateId`` and the two sides and **no timestamp at
  all** - so the book is stamped with the local receive time, with ``ts ==
  received_at`` exactly, and never with an invented exchange clock;
- ``trades``/``aggTrades`` rows carry no symbol.

Nothing here does IO; a bad payload raises
:class:`~hunter_exchanges.base.MalformedMessage`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import MarketStatus, OrderSide
from hunter_core.domain.market import (
    BookLevel,
    NormalizedMarket,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
)
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance.normalize import (
    ms_to_datetime,
    require_field,
    to_decimal,
)
from hunter_exchanges.binance.normalize import (
    parse_klines as parse_klines,  # identical 12-field row format on /api/v3
)
from hunter_exchanges.binance.normalize import (
    parse_server_time as parse_server_time,
)
from hunter_exchanges.binance_spot.filters import SpotMarketFilters, parse_filters
from hunter_exchanges.binance_spot.identity import EXCHANGE, MARKET_TYPE

__all__ = [
    "AvgPrice",
    "parse_agg_trades",
    "parse_avg_price",
    "parse_depth",
    "parse_exchange_info",
    "parse_klines",
    "parse_market",
    "parse_request_weight_limit",
    "parse_server_time",
    "parse_ticker_24h",
    "parse_trades",
]

# Spot symbol lifecycle -> our MarketStatus. Only TRADING is ever monitored;
# BREAK/HALT/AUCTION_MATCH/PENDING_TRADING are halts (the symbol comes back),
# END_OF_DAY/DELISTED are terminal.
_STATUS_MAP: dict[str, MarketStatus] = {
    "TRADING": MarketStatus.ACTIVE,
    "PENDING_TRADING": MarketStatus.SUSPENDED,
    "BREAK": MarketStatus.SUSPENDED,
    "HALT": MarketStatus.SUSPENDED,
    "AUCTION_MATCH": MarketStatus.SUSPENDED,
    "END_OF_DAY": MarketStatus.DELISTED,
    "DELISTED": MarketStatus.DELISTED,
}


@dataclass(frozen=True)
class AvgPrice:
    """``GET /api/v3/avgPrice`` - the reference price the ``NOTIONAL`` filter
    uses for a MARKET order (never the last trade; see ``filters.py``)."""

    symbol: str
    price: Decimal
    mins: int
    close_time: datetime | None = None


def parse_market(raw: dict[str, Any]) -> NormalizedMarket:
    """One ``exchangeInfo.symbols[i]`` entry -> :class:`NormalizedMarket`.

    Total for any entry; the status/quote filtering is
    :func:`parse_exchange_info`'s job. ``metadata['spot_market_filters']``
    carries the MARKET-order detail that has no column of its own
    (``MARKET_LOT_SIZE``, ``applyMinToMarket``, ``avgPriceMins``, the
    ``PERCENT_PRICE_BY_SIDE`` multipliers) - explicitly labelled, per
    ``docs/EXCHANGE_INTEGRATION.md`` §2.
    """
    symbol = require_field(raw, "symbol")
    status_raw = require_field(raw, "status")
    filters: SpotMarketFilters = parse_filters(raw)
    if filters.min_notional is None:
        raise MalformedMessage(f"{symbol}: missing NOTIONAL/MIN_NOTIONAL", exchange=EXCHANGE)
    if filters.tick_size <= 0:
        raise MalformedMessage(f"{symbol}: missing PRICE_FILTER.tickSize", exchange=EXCHANGE)
    return NormalizedMarket(
        exchange=EXCHANGE,
        symbol=symbol,
        market_type=MARKET_TYPE,
        base=require_field(raw, "baseAsset"),
        quote=require_field(raw, "quoteAsset"),
        status=_STATUS_MAP.get(status_raw, MarketStatus.SUSPENDED),
        tick_size=filters.tick_size,
        step_size=filters.step_size,
        min_notional=filters.min_notional,
        contract_size=None,  # a spot pair trades the base asset itself
        max_leverage=None,  # long-only, no leverage (docs/plans/M3.md D1)
        metadata={"spot_market_filters": filters.to_metadata()},
    )


def parse_exchange_info(raw: dict[str, Any]) -> list[NormalizedMarket]:
    """``GET /api/v3/exchangeInfo`` -> monitored USDT spot pairs only.

    ``status == TRADING``, ``quoteAsset == USDT`` and spot trading actually
    allowed on the pair - a halted symbol (``BREAK``), a non-USDT quote or a
    margin-only listing never reaches a :class:`NormalizedMarket`.
    """
    markets: list[NormalizedMarket] = []
    for entry in raw.get("symbols", []):
        if entry.get("status") != "TRADING":
            continue
        if entry.get("quoteAsset") != "USDT":
            continue
        if entry.get("isSpotTradingAllowed") is False:
            continue
        markets.append(parse_market(entry))
    return markets


def parse_request_weight_limit(raw: dict[str, Any]) -> tuple[int, float]:
    """``exchangeInfo.rateLimits`` -> ``(capacity, period_seconds)`` for the
    ``REQUEST_WEIGHT`` bucket - the exchange's own statement of the budget
    (6000/min on spot today), so ``rest.py`` never hardcodes a number the
    exchange can change under it.
    """
    seconds = {"SECOND": 1.0, "MINUTE": 60.0, "HOUR": 3600.0, "DAY": 86400.0}
    for limit in raw.get("rateLimits", []):
        if limit.get("rateLimitType") != "REQUEST_WEIGHT":
            continue
        interval = seconds.get(str(limit.get("interval")))
        if interval is None:
            break
        return int(limit["limit"]), interval * int(limit.get("intervalNum", 1))
    raise MalformedMessage("no REQUEST_WEIGHT rate limit in exchangeInfo", exchange=EXCHANGE)


def parse_ticker_24h(raw: dict[str, Any]) -> NormalizedTicker:
    """``GET /api/v3/ticker/24hr`` -> :class:`NormalizedTicker`.

    ``quote_volume_24h`` is the 24h USDT volume the tradable-universe floor
    reads (D1: >= 50M **on spot**, measured on the execution venue itself).
    """
    try:
        return NormalizedTicker(
            exchange=EXCHANGE,
            symbol=require_field(raw, "symbol"),
            ts=ms_to_datetime(raw["closeTime"], field="closeTime"),
            last=to_decimal(raw["lastPrice"], field="lastPrice"),
            bid=to_decimal(raw["bidPrice"], field="bidPrice"),
            ask=to_decimal(raw["askPrice"], field="askPrice"),
            bid_qty=to_decimal(raw["bidQty"], field="bidQty"),
            ask_qty=to_decimal(raw["askQty"], field="askQty"),
            volume_24h=to_decimal(raw["volume"], field="volume"),
            quote_volume_24h=to_decimal(raw["quoteVolume"], field="quoteVolume"),
            high_24h=to_decimal(raw["highPrice"], field="highPrice"),
            low_24h=to_decimal(raw["lowPrice"], field="lowPrice"),
            change_24h_pct=to_decimal(raw["priceChangePercent"], field="priceChangePercent"),
        )
    except KeyError as exc:
        raise MalformedMessage(f"missing field {exc} in ticker {raw!r}", exchange=EXCHANGE) from exc


def parse_depth(raw: dict[str, Any], *, symbol: str, received_at: datetime) -> NormalizedOrderBook:
    """``GET /api/v3/depth`` -> :class:`NormalizedOrderBook`.

    The spot payload has **no timestamp**: only ``lastUpdateId`` and the two
    sides. ``ts`` is therefore the caller's own receive time and is set equal
    to ``received_at``, which is how a reader downstream can tell this book
    carries no exchange clock instead of trusting a fabricated one.
    ``sequence`` is ``lastUpdateId``, which is what makes an out-of-order or
    stale snapshot detectable at all.
    """
    try:
        return NormalizedOrderBook(
            exchange=EXCHANGE,
            symbol=symbol,
            ts=received_at,
            received_at=received_at,
            bids=[
                BookLevel(
                    price=to_decimal(p, field="bid.price"), qty=to_decimal(q, field="bid.qty")
                )
                for p, q in raw["bids"]
            ],
            asks=[
                BookLevel(
                    price=to_decimal(p, field="ask.price"), qty=to_decimal(q, field="ask.qty")
                )
                for p, q in raw["asks"]
            ],
            sequence=int(raw["lastUpdateId"]),
            is_snapshot=True,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"malformed spot depth payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc


def _trade(
    *, symbol: str, trade_id: Any, price: Any, qty: Any, ts_ms: Any, buyer_is_maker: Any
) -> NormalizedTrade:
    if not isinstance(buyer_is_maker, bool):
        raise MalformedMessage(
            f"expected a bool maker flag, got {buyer_is_maker!r}", exchange=EXCHANGE
        )
    return NormalizedTrade(
        exchange=EXCHANGE,
        symbol=symbol,
        ts=ms_to_datetime(ts_ms, field="time"),
        trade_id=str(trade_id),
        price=to_decimal(price, field="price"),
        qty=to_decimal(qty, field="qty"),
        # "buyer is maker" -> the taker (aggressor) sold.
        side=OrderSide.SELL if buyer_is_maker else OrderSide.BUY,
    )


def parse_trades(raw: list[dict[str, Any]], *, symbol: str) -> list[NormalizedTrade]:
    """``GET /api/v3/trades`` -> :class:`NormalizedTrade` list (symbol is the
    caller's: the rows do not carry it)."""
    try:
        return [
            _trade(
                symbol=symbol,
                trade_id=row["id"],
                price=row["price"],
                qty=row["qty"],
                ts_ms=row["time"],
                buyer_is_maker=row["isBuyerMaker"],
            )
            for row in raw
        ]
    except KeyError as exc:
        raise MalformedMessage(f"missing field {exc} in trades row", exchange=EXCHANGE) from exc


def parse_agg_trades(raw: list[dict[str, Any]], *, symbol: str) -> list[NormalizedTrade]:
    """``GET /api/v3/aggTrades`` -> :class:`NormalizedTrade` list."""
    try:
        return [
            _trade(
                symbol=symbol,
                trade_id=row["a"],
                price=row["p"],
                qty=row["q"],
                ts_ms=row["T"],
                buyer_is_maker=row["m"],
            )
            for row in raw
        ]
    except KeyError as exc:
        raise MalformedMessage(f"missing field {exc} in aggTrades row", exchange=EXCHANGE) from exc


def parse_avg_price(raw: dict[str, Any], *, symbol: str) -> AvgPrice:
    """``GET /api/v3/avgPrice`` -> :class:`AvgPrice`."""
    try:
        close_time = raw.get("closeTime")
        return AvgPrice(
            symbol=symbol,
            price=to_decimal(raw["price"], field="price"),
            mins=int(raw["mins"]),
            close_time=None
            if close_time is None
            else ms_to_datetime(close_time, field="closeTime"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MalformedMessage(
            f"malformed avgPrice payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc
