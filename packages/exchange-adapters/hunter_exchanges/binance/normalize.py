"""Pure functions: raw Binance USDS-M Futures REST payloads -> ``Normalized*`` models.

Nothing here does IO. Every function takes a plain ``dict``/``list`` (already
JSON-decoded from a REST response) and returns a model from
:mod:`hunter_core.domain.market`, or raises
:class:`~hunter_exchanges.base.MalformedMessage` when a required field is
missing or cannot be parsed — callers (``rest.py``) decide what to do with
that; this module never logs or swallows anything, so it stays trivially
unit-testable against the fixtures in ``testing/fixtures/``.

WebSocket message parsing lives in :mod:`hunter_exchanges.binance.streams`
(kept separate so this module stays inside the 350-line budget); both share
the primitives below (:func:`to_decimal`, :func:`ms_to_datetime`, ...).
Every helper is defensive about a stray ``float``/``bool`` sneaking in from
a hand-built test payload — see :func:`to_decimal`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_core.domain.market import (
    BookLevel,
    NormalizedCandle,
    NormalizedMarket,
    NormalizedOrderBook,
    NormalizedTicker,
    close_time_for,
)
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance.normalize_derivatives import (
    parse_funding as parse_funding,
)
from hunter_exchanges.binance.normalize_derivatives import (
    parse_open_interest as parse_open_interest,
)
from hunter_exchanges.binance.normalize_derivatives import (
    parse_realized_funding as parse_realized_funding,
)
from hunter_exchanges.binance.parse import (
    EXCHANGE as EXCHANGE,
)
from hunter_exchanges.binance.parse import (
    ms_to_datetime as ms_to_datetime,
)
from hunter_exchanges.binance.parse import (
    require_field as require_field,
)
from hunter_exchanges.binance.parse import (
    to_decimal as to_decimal,
)
from hunter_exchanges.binance.parse import (
    to_decimal_or_none as to_decimal_or_none,
)

# exchangeInfo `status` -> our MarketStatus. Binance's futures lifecycle has
# more states than we track; only TRADING is ever monitored (M1.md Decisões),
# everything else collapses to SUSPENDED except the terminal ones.
_STATUS_MAP: dict[str, MarketStatus] = {
    "TRADING": MarketStatus.ACTIVE,
    "PENDING_TRADING": MarketStatus.SUSPENDED,
    "PRE_DELIVERING": MarketStatus.SUSPENDED,
    "SETTLING": MarketStatus.SUSPENDED,
    "PRE_SETTLE": MarketStatus.SUSPENDED,
    "BREAK": MarketStatus.SUSPENDED,
    "DELIVERING": MarketStatus.DELISTED,
    "DELIVERED": MarketStatus.DELISTED,
    "CLOSE": MarketStatus.DELISTED,
}


def _filter_entry(raw: dict[str, Any], filter_type: str) -> dict[str, Any] | None:
    for flt in raw.get("filters", []):
        if flt.get("filterType") == filter_type:
            return flt
    return None


def parse_market(raw: dict[str, Any]) -> NormalizedMarket:
    """One ``exchangeInfo.symbols[i]`` entry -> :class:`NormalizedMarket`.

    A pure, total mapping for any symbol entry — filtering by
    status/contract-type/quote-asset is :func:`parse_exchange_info`'s job.
    """
    try:
        symbol = require_field(raw, "symbol")
        status_raw = require_field(raw, "status")
        price_filter = _filter_entry(raw, "PRICE_FILTER")
        lot_filter = _filter_entry(raw, "LOT_SIZE")
        notional_filter = _filter_entry(raw, "MIN_NOTIONAL")
        if price_filter is None or lot_filter is None or notional_filter is None:
            raise MalformedMessage(
                f"{symbol}: missing PRICE_FILTER/LOT_SIZE/MIN_NOTIONAL", exchange=EXCHANGE
            )
        return NormalizedMarket(
            exchange=EXCHANGE,
            symbol=symbol,
            market_type=MarketType.PERPETUAL,
            base=require_field(raw, "baseAsset"),
            quote=require_field(raw, "quoteAsset"),
            status=_STATUS_MAP.get(status_raw, MarketStatus.SUSPENDED),
            tick_size=to_decimal(price_filter["tickSize"], field="tickSize"),
            step_size=to_decimal(lot_filter["stepSize"], field="stepSize"),
            min_notional=to_decimal(notional_filter["notional"], field="notional"),
            max_leverage=None,
            metadata={"contractType": raw.get("contractType", "")},
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in market entry {raw!r}", exchange=EXCHANGE
        ) from exc


def parse_exchange_info(raw: dict[str, Any]) -> list[NormalizedMarket]:
    """``GET /fapi/v1/exchangeInfo`` -> monitored USDT perpetuals only.

    ``docs/plans/M1.md`` T1.2: "only contractType == PERPETUAL, status ==
    TRADING, quote USDT" — a delisted symbol, a quarterly future or a
    non-USDT-margined pair never reaches :class:`NormalizedMarket` at all.
    """
    markets: list[NormalizedMarket] = []
    for entry in raw.get("symbols", []):
        if entry.get("contractType") != "PERPETUAL":
            continue
        if entry.get("status") != "TRADING":
            continue
        if entry.get("quoteAsset") != "USDT":
            continue
        markets.append(parse_market(entry))
    return markets


def parse_kline(
    raw: list[Any],
    *,
    symbol: str,
    now: datetime,
    market_type: MarketType = MarketType.PERPETUAL,
) -> NormalizedCandle:
    """One ``klines`` row (REST array-of-12 format) -> :class:`NormalizedCandle`.

    ``is_final`` is derived from ``close_time <= now`` (T1.2 brief): REST
    klines carry no "closed" flag, and the last row of a request can be the
    still-forming current candle. ``close_time`` itself is the *exclusive*
    boundary from :func:`~hunter_core.domain.market.close_time_for`
    (``open_time`` + one minute), not Binance's own inclusive ``closeTime``
    (``open_time`` + 59.999s) — matching the domain model's own alignment
    helpers instead of forwarding the exchange's off-by-one-ms convention
    (Astra review, T1.2 resume).

    The ``isinstance``/``len`` guard below is statically redundant against
    the ``list[Any]`` hint but real at the actual boundary (untyped JSON
    meets this parser) — kept, with the two lines it needs annotated instead
    of loosening the signature to ``Any`` (which would just turn the
    downstream ``raw[i]`` accesses into new "unknown argument" errors).
    """
    if not isinstance(raw, list) or len(raw) < 11:  # type: ignore[reportUnnecessaryIsInstance]
        got = len(raw) if isinstance(raw, list) else "n/a"  # type: ignore[reportUnnecessaryIsInstance]
        raise MalformedMessage(f"kline row has {got} fields, need >= 11", exchange=EXCHANGE)
    try:
        open_time = ms_to_datetime(raw[0], field="openTime")
        close_time = close_time_for(open_time, Timeframe.M1)
        return NormalizedCandle(
            exchange=EXCHANGE,
            symbol=symbol,
            market_type=market_type,
            timeframe=Timeframe.M1,
            open_time=open_time,
            close_time=close_time,
            open=to_decimal(raw[1], field="open"),
            high=to_decimal(raw[2], field="high"),
            low=to_decimal(raw[3], field="low"),
            close=to_decimal(raw[4], field="close"),
            volume=to_decimal(raw[5], field="volume"),
            quote_volume=to_decimal(raw[7], field="quoteVolume"),
            trade_count=int(raw[8]),
            taker_buy_volume=to_decimal(raw[9], field="takerBuyVolume"),
            is_final=close_time <= now,
        )
    except (TypeError, ValueError, IndexError) as exc:
        raise MalformedMessage(f"malformed kline row {raw!r}: {exc}", exchange=EXCHANGE) from exc


def parse_klines(
    raw: list[list[Any]],
    *,
    symbol: str,
    now: datetime,
    market_type: MarketType = MarketType.PERPETUAL,
) -> list[NormalizedCandle]:
    """``market_type`` because the row format is identical on ``/api/v3`` and
    this parser is shared with the spot adapter (T3.0b): the only thing that
    tells a spot candle from a perpetual one is the caller."""
    return [parse_kline(row, symbol=symbol, now=now, market_type=market_type) for row in raw]


def parse_ticker_24h(raw: dict[str, Any]) -> NormalizedTicker:
    """``GET /fapi/v1/ticker/24hr`` -> :class:`NormalizedTicker`.

    This endpoint carries no bid/ask (only the ``bookTicker`` stream does),
    so ``bid``/``ask`` stay ``None`` here.
    """
    try:
        return NormalizedTicker(
            exchange=EXCHANGE,
            symbol=require_field(raw, "symbol"),
            ts=ms_to_datetime(raw["closeTime"], field="closeTime"),
            last=to_decimal(raw["lastPrice"], field="lastPrice"),
            volume_24h=to_decimal(raw["volume"], field="volume"),
            quote_volume_24h=to_decimal(raw["quoteVolume"], field="quoteVolume"),
            high_24h=to_decimal(raw["highPrice"], field="highPrice"),
            low_24h=to_decimal(raw["lowPrice"], field="lowPrice"),
            change_24h_pct=to_decimal(raw["priceChangePercent"], field="priceChangePercent"),
        )
    except KeyError as exc:
        raise MalformedMessage(f"missing field {exc} in ticker {raw!r}", exchange=EXCHANGE) from exc


def parse_order_book(raw: dict[str, Any], *, symbol: str) -> NormalizedOrderBook:
    """``GET /fapi/v1/depth`` (REST snapshot) -> :class:`NormalizedOrderBook`."""
    try:
        ts = (
            ms_to_datetime(raw["T"], field="T")
            if "T" in raw
            else ms_to_datetime(raw["E"], field="E")
        )
        return NormalizedOrderBook(
            exchange=EXCHANGE,
            symbol=symbol,
            ts=ts,
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
            f"malformed depth payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc


def parse_server_time(raw: Any) -> datetime:
    """``GET /fapi/v1/time`` -> UTC ``datetime`` (the exchange's own clock)."""
    if not isinstance(raw, dict):
        raise MalformedMessage(f"server time payload is not an object: {raw!r}", exchange=EXCHANGE)
    payload = cast("dict[str, Any]", raw)
    return ms_to_datetime(require_field(payload, "serverTime"), field="serverTime")
