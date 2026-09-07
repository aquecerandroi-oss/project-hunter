"""WebSocket stream names and frame parsing for Binance **SPOT** combined streams.

One endpoint (``wss://stream.binance.com:9443/stream?streams=...``, a single
route - unlike USDS-M's ``/public`` + ``/market`` split), up to 1024 streams
per connection, and at most 5 *incoming* messages per second per connection,
which includes every ``SUBSCRIBE``/``UNSUBSCRIBE``/``PONG`` we send (see
:mod:`hunter_exchanges.binance_spot.throttle`).

Four channels, all confirmed against recorded frames in
``testing/fixtures/spot_ws_*.json``:

===================  =========================  ==================================
Channel              Stream                     Payload notes
===================  =========================  ==================================
``TRADES``           ``<sym>@aggTrade``         same shape as USDS-M (``E``/``T``)
``KLINE_1M``         ``<sym>@kline_1m``         same shape as USDS-M (``E``, ``k``)
``BOOK``             ``<sym>@depth20@100ms``    **no symbol, no timestamp**
``BOOK_TICKER``      ``<sym>@bookTicker``       **no timestamp, no last price**
===================  =========================  ==================================

Consequences that are honest instead of convenient:

- the symbol always comes from the *stream name* (:func:`symbol_for_stream_name`),
  which is authoritative for every channel and is the only source for
  ``depth20``;
- ``BOOK`` and ``BOOK_TICKER`` events are stamped with the receive time, and
  ``ts == received_at`` marks that they carry no exchange clock. The two
  channels that do have one (``aggTrade``, ``kline``) keep it;
- ``BOOK_TICKER`` has no last-traded price, so a ticker is only emitted once
  an ``aggTrade`` has established one (same rule as the USDS-M client);
- ``MARK_PRICE``/``LIQUIDATIONS`` do not exist on spot at all: asking for one
  raises instead of yielding a stream that would stay silent forever.

The partial-depth stream is a *snapshot* every 100 ms; ``lastUpdateId`` is
still checked for monotonicity by the client
(:class:`~hunter_exchanges.binance_spot.ws.BinanceSpotWsClient`) so a stale
or reordered frame can never overwrite a newer book.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.market import (
    BookLevel,
    NormalizedCandle,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
)
from hunter_exchanges.base import MalformedMessage, StreamChannel
from hunter_exchanges.binance.normalize import ms_to_datetime, to_decimal
from hunter_exchanges.binance.streams import parse_kline_ws as _parse_kline_ws
from hunter_exchanges.binance_spot.identity import EXCHANGE, MARKET_TYPE

__all__ = [
    "BOOK_CADENCE_MS",
    "BOOK_DEPTH",
    "MAX_CONTROL_MESSAGES_PER_S",
    "MAX_STREAMS_PER_CONNECTION",
    "MAX_SYMBOLS_PER_CONNECTION",
    "ROUTE_SPOT",
    "SPOT_CHANNELS",
    "WS_BASE_URL",
    "channel_for_stream_name",
    "group_symbols",
    "parse_stream_message",
    "split_channels_by_route",
    "stream_name",
    "symbol_for_stream_name",
]

WS_BASE_URL = "wss://stream.binance.com:9443/stream?streams="
ROUTE_SPOT = "spot"
BOOK_DEPTH = 20
BOOK_CADENCE_MS = 100
#: Binance spot: 1024 streams per connection, 300 connection attempts per 5
#: min per IP, and **5 incoming messages per second** per connection (that
#: budget covers our SUBSCRIBE/UNSUBSCRIBE/PONG frames).
MAX_STREAMS_PER_CONNECTION = 1024
MAX_CONTROL_MESSAGES_PER_S = 5
#: 200 symbols x 4 channels = 800 streams, inside the 1024 cap (same group
#: size the USDS-M client uses).
MAX_SYMBOLS_PER_CONNECTION = 200

_CHANNEL_SUFFIX: dict[StreamChannel, str] = {
    StreamChannel.TRADES: "aggTrade",
    StreamChannel.BOOK_TICKER: "bookTicker",
    StreamChannel.KLINE_1M: "kline_1m",
    StreamChannel.BOOK: f"depth{BOOK_DEPTH}@{BOOK_CADENCE_MS}ms",
}
SPOT_CHANNELS: tuple[StreamChannel, ...] = tuple(_CHANNEL_SUFFIX)
_SUFFIX_TO_CHANNEL: dict[str, StreamChannel] = {s: c for c, s in _CHANNEL_SUFFIX.items()}


def stream_name(symbol: str, channel: StreamChannel) -> str:
    """e.g. ``("BTCUSDT", StreamChannel.BOOK)`` -> ``"btcusdt@depth20@100ms"``."""
    suffix = _CHANNEL_SUFFIX.get(channel)
    if suffix is None:
        raise ValueError(
            f"binance spot has no {channel} stream (funding/OI/liquidation are USDS-M)"
        )
    return f"{symbol.lower()}@{suffix}"


def channel_for_stream_name(name: str) -> StreamChannel | None:
    """Reverse of :func:`stream_name` - ``None`` for an unknown stream."""
    _, _, suffix = name.partition("@")
    return _SUFFIX_TO_CHANNEL.get(suffix)


def symbol_for_stream_name(name: str) -> str:
    """``"btcusdt@depth20@100ms"`` -> ``"BTCUSDT"`` (authoritative on spot)."""
    symbol, _, _ = name.partition("@")
    return symbol.upper()


def route_for_channel(channel: StreamChannel) -> str:
    """Every spot channel shares one endpoint - one route, ``"spot"``."""
    if channel not in _CHANNEL_SUFFIX:
        raise ValueError(f"binance spot has no {channel} stream")
    return ROUTE_SPOT


def split_channels_by_route(channels: Sequence[StreamChannel]) -> dict[str, list[StreamChannel]]:
    """Same signature as the USDS-M splitter, one route on spot."""
    if not channels:
        return {}
    return {ROUTE_SPOT: [c for c in channels if route_for_channel(c) == ROUTE_SPOT]}


def group_symbols(
    symbols: Sequence[str], max_per_connection: int = MAX_SYMBOLS_PER_CONNECTION
) -> list[list[str]]:
    """Split ``symbols`` into connection-sized groups (empty -> one idle group)."""
    if not symbols:
        return [[]]
    return [
        list(symbols[i : i + max_per_connection])
        for i in range(0, len(symbols), max_per_connection)
    ]


def parse_agg_trade(raw: dict[str, Any], *, symbol: str) -> NormalizedTrade:
    """``<symbol>@aggTrade`` -> :class:`NormalizedTrade`; ``m`` = "buyer is
    maker", so true means the taker (aggressor) sold."""
    try:
        return NormalizedTrade.model_construct(
            exchange=EXCHANGE,
            symbol=symbol,
            market_type=MARKET_TYPE,
            ts=ms_to_datetime(raw["T"], field="T"),
            trade_id=str(raw["a"]),
            price=to_decimal(raw["p"], field="p"),
            qty=to_decimal(raw["q"], field="q"),
            side=_taker_side(raw["m"]),
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in spot aggTrade {raw!r}", exchange=EXCHANGE
        ) from exc


def _taker_side(buyer_is_maker: Any) -> Any:
    from hunter_core.domain.enums import OrderSide

    if not isinstance(buyer_is_maker, bool):
        raise MalformedMessage(
            f"expected a bool maker flag, got {buyer_is_maker!r}", exchange=EXCHANGE
        )
    return OrderSide.SELL if buyer_is_maker else OrderSide.BUY


_BOOK_TICKER_REQUIRED_FIELDS = ("b", "B", "a", "A")


def parse_book_ticker(
    raw: dict[str, Any], *, symbol: str, last: Decimal, received_at: datetime
) -> NormalizedTicker:
    """``<symbol>@bookTicker`` -> :class:`NormalizedTicker`.

    ``last`` comes from the caller's most recent ``aggTrade`` (the frame has
    none), and ``ts`` is the receive time (the frame has none either) - both
    stated rather than invented.
    """
    validate_book_ticker_fields(raw)
    return NormalizedTicker.model_construct(
        exchange=EXCHANGE,
        symbol=symbol,
        market_type=MARKET_TYPE,
        ts=received_at,
        received_at=received_at,
        last=last,
        bid=to_decimal(raw["b"], field="b"),
        ask=to_decimal(raw["a"], field="a"),
        bid_qty=to_decimal(raw["B"], field="B"),
        ask_qty=to_decimal(raw["A"], field="A"),
    )


def validate_book_ticker_fields(raw: dict[str, Any]) -> None:
    """Checked even when the ticker is deferred: garbage is not proof of life."""
    for field_name in _BOOK_TICKER_REQUIRED_FIELDS:
        if field_name not in raw:
            raise MalformedMessage(
                f"missing field {field_name!r} in spot bookTicker {raw!r}", exchange=EXCHANGE
            )


def _book_level(price_raw: Any, qty_raw: Any, *, side: str) -> BookLevel:
    qty = to_decimal(qty_raw, field=f"{side}.qty")
    if qty < 0:
        raise MalformedMessage(f"{side}.qty must be >= 0, got {qty_raw!r}", exchange=EXCHANGE)
    return BookLevel.model_construct(price=to_decimal(price_raw, field=f"{side}.price"), qty=qty)


def _ensure_sorted(levels: list[BookLevel], *, desc: bool, label: str) -> None:
    bad = any(
        (a.price < b.price) if desc else (a.price > b.price)
        for a, b in zip(levels, levels[1:], strict=False)
    )
    if bad:
        raise MalformedMessage(f"{label} price order is broken", exchange=EXCHANGE)


def parse_depth20(
    raw: dict[str, Any], *, symbol: str, received_at: datetime
) -> NormalizedOrderBook:
    """``<symbol>@depth20@100ms`` -> :class:`NormalizedOrderBook` (always a
    snapshot; ``sequence`` is ``lastUpdateId``, ``ts`` the receive time)."""
    try:
        bids = [_book_level(p, q, side="bid") for p, q in raw["bids"]]
        asks = [_book_level(p, q, side="ask") for p, q in raw["asks"]]
        _ensure_sorted(bids, desc=True, label="bids")
        _ensure_sorted(asks, desc=False, label="asks")
        if bids and asks and bids[0].price >= asks[0].price:
            raise MalformedMessage(
                f"crossed book for {symbol}: {bids[0].price} >= {asks[0].price}", exchange=EXCHANGE
            )
        return NormalizedOrderBook.model_construct(
            exchange=EXCHANGE,
            symbol=symbol,
            market_type=MARKET_TYPE,
            ts=received_at,
            received_at=received_at,
            bids=bids,
            asks=asks,
            sequence=int(raw["lastUpdateId"]),
            is_snapshot=True,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"malformed spot depth20 payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc


def parse_kline(raw: dict[str, Any]) -> NormalizedCandle:
    """``<symbol>@kline_1m`` - byte-identical to the USDS-M frame, so the
    USDS-M parser is reused rather than copied (both stamp
    ``exchange="binance"``, which is correct for spot too: same venue). The
    *market* is not shared, hence ``market_type`` (T3.0b)."""
    return _parse_kline_ws(raw, market_type=MARKET_TYPE)


def parse_stream_message(
    stream: str,
    data: dict[str, Any],
    *,
    last_price: Decimal | None,
    received_at: datetime,
) -> Any | None:
    """Dispatch one combined-stream frame by ``stream`` name.

    ``None`` for a still-deferred ``BOOK_TICKER`` (validated first
    regardless); raises :class:`MalformedMessage` for an unknown stream or a
    bad payload. The symbol always comes from ``stream``.
    """
    channel = channel_for_stream_name(stream)
    if channel is None:
        raise MalformedMessage(f"unknown spot stream name {stream!r}", exchange=EXCHANGE)
    symbol = symbol_for_stream_name(stream)
    if channel is StreamChannel.TRADES:
        return parse_agg_trade(data, symbol=symbol)
    if channel is StreamChannel.KLINE_1M:
        return parse_kline(data)
    if channel is StreamChannel.BOOK:
        return parse_depth20(data, symbol=symbol, received_at=received_at)
    validate_book_ticker_fields(data)
    if last_price is None:
        return None
    return parse_book_ticker(data, symbol=symbol, last=last_price, received_at=received_at)
