"""WebSocket channel names and raw-message parsing for Binance combined streams.

``docs/EXCHANGE_INTEGRATION.md`` §4 / ``docs/plans/M1.md`` T1.2: one Binance
connection carries several symbols x several channels multiplexed as a single
"combined stream" URL; each incoming frame is ``{"stream": "<name>", "data":
{...}}``. This module owns both halves: building/grouping stream names
(:func:`stream_name`, :func:`group_symbols`, :func:`combined_stream_url`) so
``ws.py`` never hand-formats a URL, and parsing each channel's raw ``data``
into a :mod:`hunter_core.domain.market` model, dispatched by
:func:`parse_stream_message`.

Every ``parse_*`` function here is pure and raises
:class:`~hunter_exchanges.base.MalformedMessage` on a bad payload — ``ws.py``
decides what happens next (log + count, never propagate). T1.6b-A: every
parser builds its model with ``.model_construct()``, not ``Model(...)`` (no
validators run — 20.36% self time at 200 markets, ``t16b-profile.md``), so
each parser keeps their guarantees explicit instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import (
    BookLevel,
    NormalizedCandle,
    NormalizedFunding,
    NormalizedLiquidation,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
    close_time_for,
)
from hunter_exchanges.base import MalformedMessage, StreamChannel
from hunter_exchanges.binance.normalize import (
    EXCHANGE,
    ms_to_datetime,
    require_field,
    to_decimal,
    to_decimal_or_none,
)

MAX_SYMBOLS_PER_CONNECTION = 200
MAX_STREAMS_PER_CONNECTION = 1024  # F12: Binance's cap; assert_stream_budget guards it
BOOK_DEPTH = 20  # M1 decision: top 20, no local book
ROUTE_PUBLIC = "public"  # book/bid-ask (Binance's two-route WS split)
ROUTE_MARKET = "market"  # everything else

_CHANNEL_SUFFIX: dict[StreamChannel, str] = {
    StreamChannel.TRADES: "aggTrade",
    StreamChannel.BOOK_TICKER: "bookTicker",
    StreamChannel.KLINE_1M: "kline_1m",
    StreamChannel.MARK_PRICE: "markPrice@1s",
    StreamChannel.LIQUIDATIONS: "forceOrder",
}

# T1.6b-A: BOOK's suffix is a module-level cadence (set_book_cadence_ms), not
# a fixed _CHANNEL_SUFFIX entry — 500ms default halves parse_depth20's 23%
# self time at 200 markets (t16b-profile.md; was 250ms/no-suffix at M1).
DEFAULT_BOOK_CADENCE_MS = 500
_BOOK_CADENCE_SUFFIX: dict[int | None, str] = {
    None: "depth20",
    250: "depth20",
    100: "depth20@100ms",
}
_BOOK_SUFFIXES = ("depth20", "depth20@100ms", "depth20@250ms", "depth20@500ms")
_book_cadence_ms: int | None = DEFAULT_BOOK_CADENCE_MS


def set_book_cadence_ms(cadence_ms: int | None) -> None:
    """Process-wide: ``None``/``250`` -> no suffix, else ``depth20@{ms}ms``."""
    global _book_cadence_ms
    _book_cadence_ms = cadence_ms


def _book_suffix() -> str:
    return _BOOK_CADENCE_SUFFIX.get(_book_cadence_ms, f"depth20@{_book_cadence_ms}ms")


_SUFFIX_TO_CHANNEL: dict[str, StreamChannel] = {s: c for c, s in _CHANNEL_SUFFIX.items()}
_SUFFIX_TO_CHANNEL.update(dict.fromkeys(_BOOK_SUFFIXES, StreamChannel.BOOK))

_CHANNEL_ROUTE: dict[StreamChannel, str] = {
    StreamChannel.BOOK: ROUTE_PUBLIC,
    StreamChannel.BOOK_TICKER: ROUTE_PUBLIC,
    StreamChannel.TRADES: ROUTE_MARKET,
    StreamChannel.KLINE_1M: ROUTE_MARKET,
    StreamChannel.MARK_PRICE: ROUTE_MARKET,
    StreamChannel.LIQUIDATIONS: ROUTE_MARKET,
}


def route_for_channel(channel: StreamChannel) -> str:
    """``"public"`` for book/bid-ask channels, ``"market"`` for everything else."""
    return _CHANNEL_ROUTE[channel]


def split_channels_by_route(
    channels: Sequence[StreamChannel],
) -> dict[str, list[StreamChannel]]:
    """Group ``channels`` by :func:`route_for_channel`, dropping empty routes."""
    by_route: dict[str, list[StreamChannel]] = {}
    for channel in channels:
        by_route.setdefault(route_for_channel(channel), []).append(channel)
    return by_route


def stream_name(symbol: str, channel: StreamChannel) -> str:
    """e.g. ``("BTCUSDT", StreamChannel.TRADES)`` -> ``"btcusdt@aggTrade"``."""
    suffix = _book_suffix() if channel is StreamChannel.BOOK else _CHANNEL_SUFFIX[channel]
    return f"{symbol.lower()}@{suffix}"


def channel_for_stream_name(name: str) -> StreamChannel | None:
    """Reverse of :func:`stream_name`'s suffix — ``None`` for an unknown stream."""
    _, _, suffix = name.partition("@")
    return _SUFFIX_TO_CHANNEL.get(suffix)


def group_symbols(
    symbols: Sequence[str], max_per_connection: int = MAX_SYMBOLS_PER_CONNECTION
) -> list[list[str]]:
    """Split ``symbols`` into groups of at most ``max_per_connection`` (M1.md
    T1.2). Empty input -> one empty group (a deterministic idle connection)."""
    if not symbols:
        return [[]]
    return [
        list(symbols[i : i + max_per_connection])
        for i in range(0, len(symbols), max_per_connection)
    ]


def combined_stream_url(base_url: str, streams: Sequence[str]) -> str:
    """``base_url`` (e.g. ``wss://fstream.binance.com/stream?streams=``) + streams."""
    return base_url + "/".join(streams)


def parse_agg_trade(raw: dict[str, Any]) -> NormalizedTrade:
    """``<symbol>@aggTrade`` -> :class:`NormalizedTrade`. ``m`` = "buyer is
    maker"; true means the taker (aggressor) sold, else the taker bought."""
    try:
        return NormalizedTrade.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            ts=ms_to_datetime(raw["T"], field="T"),
            trade_id=str(raw["a"]),
            price=to_decimal(raw["p"], field="p"),
            qty=to_decimal(raw["q"], field="q"),
            side=OrderSide.SELL if raw["m"] else OrderSide.BUY,
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in aggTrade {raw!r}", exchange=EXCHANGE
        ) from exc


def event_ts(raw: dict[str, Any]) -> Any:
    """Event time for a channel whose top-level ``T``/``E`` *is* it (bookTicker,
    depth20); exposed so ``ws.py`` can timestamp a deferred bookTicker frame."""
    return (
        ms_to_datetime(raw["T"], field="T") if "T" in raw else ms_to_datetime(raw["E"], field="E")
    )


def parse_book_ticker(raw: dict[str, Any], *, last: Decimal) -> NormalizedTicker:
    """``<symbol>@bookTicker`` -> :class:`NormalizedTicker`. ``last`` comes
    from the caller (``ws.py`` tracks the most recent ``aggTrade`` price) —
    the stream itself carries no last-traded price, never invented here."""
    try:
        return NormalizedTicker.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            ts=event_ts(raw),
            last=last,
            bid=to_decimal(raw["b"], field="b"),
            ask=to_decimal(raw["a"], field="a"),
            bid_qty=to_decimal(raw["B"], field="B"),
            ask_qty=to_decimal(raw["A"], field="A"),
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in bookTicker {raw!r}", exchange=EXCHANGE
        ) from exc


def _book_level(price_raw: Any, qty_raw: Any, *, side: str) -> BookLevel:
    """``[price, qty]`` -> :class:`BookLevel`; ``qty >= 0`` checked explicitly
    (``BookLevel.Field(ge=0)`` doesn't run under ``model_construct``)."""
    qty = to_decimal(qty_raw, field=f"{side}.qty")
    if qty < 0:
        raise MalformedMessage(f"{side}.qty must be >= 0, got {qty_raw!r}", exchange=EXCHANGE)
    return BookLevel.model_construct(price=to_decimal(price_raw, field=f"{side}.price"), qty=qty)


def _ensure_sorted(levels: list[BookLevel], *, desc: bool, label: str) -> None:
    """Sort-order check ``model_construct`` skips (was a field_validator)."""
    bad = any(
        (a.price < b.price) if desc else (a.price > b.price)
        for a, b in zip(levels, levels[1:], strict=False)
    )
    if bad:
        raise MalformedMessage(f"{label} price order is broken", exchange=EXCHANGE)


def parse_depth20(raw: dict[str, Any]) -> NormalizedOrderBook:
    """``<symbol>@depth20`` -> :class:`NormalizedOrderBook` (top 20, always
    ``is_snapshot=True`` — no local diff-book)."""
    try:
        bids = [_book_level(p, q, side="bid") for p, q in raw["b"]]
        asks = [_book_level(p, q, side="ask") for p, q in raw["a"]]
        _ensure_sorted(bids, desc=True, label="bids")
        _ensure_sorted(asks, desc=False, label="asks")
        return NormalizedOrderBook.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            ts=event_ts(raw),
            bids=bids,
            asks=asks,
            sequence=int(raw["u"]),
            is_snapshot=True,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"malformed depth20 payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc


def parse_kline_ws(raw: dict[str, Any]) -> NormalizedCandle:
    """``<symbol>@kline_1m`` -> :class:`NormalizedCandle`. ``is_final`` is the
    stream's own ``k.x`` flag; ``event_ts`` is the frame's ``E`` (push time),
    so the worker can order same-``open_time`` partials by arrival."""
    try:
        k = require_field(raw, "k")
        open_time = ms_to_datetime(k["t"], field="k.t")
        return NormalizedCandle.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            timeframe=Timeframe.M1,
            open_time=open_time,
            close_time=close_time_for(open_time, Timeframe.M1),
            open=to_decimal(k["o"], field="k.o"),
            high=to_decimal(k["h"], field="k.h"),
            low=to_decimal(k["l"], field="k.l"),
            close=to_decimal(k["c"], field="k.c"),
            volume=to_decimal(k["v"], field="k.v"),
            quote_volume=to_decimal(k["q"], field="k.q"),
            trade_count=int(k["n"]),
            taker_buy_volume=to_decimal(k["V"], field="k.V"),
            is_final=bool(k["x"]),
            event_ts=ms_to_datetime(raw["E"], field="E") if "E" in raw else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MalformedMessage(
            f"malformed kline_1m payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc


def parse_mark_price(raw: dict[str, Any]) -> NormalizedFunding:
    """``<symbol>@markPrice@1s`` -> :class:`NormalizedFunding` (always
    ``funding_kind="estimated"``); ``metadata`` labels the unmapped ``P``."""
    try:
        next_funding_time = ms_to_datetime(raw["T"], field="T") if raw.get("T") else None
        metadata: dict[str, Any] = {}
        if "P" in raw:
            metadata["estimated_settle_price"] = raw["P"]
        return NormalizedFunding.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            ts=ms_to_datetime(raw["E"], field="E"),
            funding_rate=to_decimal(raw["r"], field="r"),
            next_funding_time=next_funding_time,
            mark_price=to_decimal(raw["p"], field="p"),
            index_price=to_decimal_or_none(raw.get("i"), field="i"),
            funding_kind="estimated",
            metadata=metadata,
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in markPrice {raw!r}", exchange=EXCHANGE
        ) from exc


def parse_force_order(raw: dict[str, Any]) -> NormalizedLiquidation:
    """``<symbol>@forceOrder`` -> :class:`NormalizedLiquidation`; ``notional``
    is set explicitly (its model_validator default skips ``model_construct``)."""
    try:
        order = require_field(raw, "o")
        side_raw = order["S"]
        side = OrderSide.SELL if side_raw == "SELL" else OrderSide.BUY
        qty = to_decimal(order["q"], field="o.q")
        price = to_decimal(order["p"], field="o.p")
        return NormalizedLiquidation.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(order, "s"),
            ts=ms_to_datetime(order["T"], field="o.T"),
            side=side,
            qty=qty,
            price=price,
            notional=qty * price,
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in forceOrder {raw!r}", exchange=EXCHANGE
        ) from exc


_PARSERS = {
    StreamChannel.TRADES: parse_agg_trade,
    StreamChannel.BOOK: parse_depth20,
    StreamChannel.KLINE_1M: parse_kline_ws,
    StreamChannel.MARK_PRICE: parse_mark_price,
    StreamChannel.LIQUIDATIONS: parse_force_order,
}


#: F9: required even for a deferred bookTicker ("garbage isn't proof of life").
_BOOK_TICKER_REQUIRED_FIELDS = ("s", "b", "a", "B", "A")


def _validate_book_ticker_fields(raw: dict[str, Any]) -> None:
    for field_name in _BOOK_TICKER_REQUIRED_FIELDS:
        if field_name not in raw:
            raise MalformedMessage(
                f"missing field {field_name!r} in bookTicker {raw!r}", exchange=EXCHANGE
            )
    if "T" not in raw and "E" not in raw:
        raise MalformedMessage(f"missing field 'T'/'E' in bookTicker {raw!r}", exchange=EXCHANGE)


def parse_stream_message(
    stream: str, data: dict[str, Any], *, last_price: Decimal | None
) -> Any | None:
    """Dispatch one combined-stream frame's ``data`` by ``stream`` name. ``None``
    for an unrecognized suffix or a still-deferred ``BOOK_TICKER`` (validated
    first regardless, F9); raises :class:`MalformedMessage` otherwise."""
    channel = channel_for_stream_name(stream)
    if channel is None:
        raise MalformedMessage(f"unknown stream name {stream!r}", exchange=EXCHANGE)
    if channel is StreamChannel.BOOK_TICKER:
        if last_price is None:
            _validate_book_ticker_fields(data)
            return None
        return parse_book_ticker(data, last=last_price)
    return _PARSERS[channel](data)
