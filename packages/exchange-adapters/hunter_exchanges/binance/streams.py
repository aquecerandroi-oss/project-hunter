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
decides what happens next (log + count, never propagate).
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
#: F12: Binance's documented per-connection cap — 200 x 4 market channels =
#: 800 is safe only by coincidence; a 5th/6th channel would silently
#: overshoot this without an explicit assertion (``subscriptions.py``).
MAX_STREAMS_PER_CONNECTION = 1024

#: Depth of every ``@depth20`` partial-book snapshot (M1 joint decision,
#: ``.claude/state/dialogue-M1.md`` rodada 1/round 1: top 20, no local book).
BOOK_DEPTH = 20

#: The two combined-stream routes Binance documents separately (Important
#: WebSocket Change Notice): book/bid-ask on ``/public/stream``, everything
#: else on ``/market/stream``. See ``docs/plans/M1.md`` "Decisão conjunta".
ROUTE_PUBLIC = "public"
ROUTE_MARKET = "market"

_CHANNEL_SUFFIX: dict[StreamChannel, str] = {
    StreamChannel.TRADES: "aggTrade",
    StreamChannel.BOOK_TICKER: "bookTicker",
    # No cadence suffix: default (250ms) picked by the joint decision
    # ("@depth20 sem sufixo"); explicit suffixes are a different, unused contract.
    StreamChannel.BOOK: "depth20",
    StreamChannel.KLINE_1M: "kline_1m",
    StreamChannel.MARK_PRICE: "markPrice@1s",
    StreamChannel.LIQUIDATIONS: "forceOrder",
}
_SUFFIX_TO_CHANNEL = {suffix: channel for channel, suffix in _CHANNEL_SUFFIX.items()}

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
    return f"{symbol.lower()}@{_CHANNEL_SUFFIX[channel]}"


def channel_for_stream_name(name: str) -> StreamChannel | None:
    """Reverse of :func:`stream_name`'s suffix — ``None`` for an unknown stream."""
    _, _, suffix = name.partition("@")
    return _SUFFIX_TO_CHANNEL.get(suffix)


def group_symbols(
    symbols: Sequence[str], max_per_connection: int = MAX_SYMBOLS_PER_CONNECTION
) -> list[list[str]]:
    """Split ``symbols`` into groups of at most ``max_per_connection``.

    ``docs/plans/M1.md`` T1.2: "<= 200 symbols per connection, several
    connections if more". An empty input yields one empty group so a caller
    can still open a (stream-less, idle) connection deterministically rather
    than special-casing "no symbols" itself.
    """
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
    """``<symbol>@aggTrade`` -> :class:`NormalizedTrade`.

    ``m`` = "is the buyer the market maker"; when true the taker (aggressor)
    sold, so the trade's side is SELL, otherwise the taker bought.
    """
    try:
        return NormalizedTrade(
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
    """Event time for channels whose top-level ``T``/``E`` *is* the event
    time (bookTicker, depth20). Not valid for ``markPrice``/``forceOrder``,
    which parse their own ``ts``. Exposed so ``ws.py`` can timestamp a
    deferred bookTicker frame that produced no event.
    """
    return (
        ms_to_datetime(raw["T"], field="T") if "T" in raw else ms_to_datetime(raw["E"], field="E")
    )


def parse_book_ticker(raw: dict[str, Any], *, last: Decimal) -> NormalizedTicker:
    """``<symbol>@bookTicker`` -> :class:`NormalizedTicker`.

    The stream never carries a last-traded price, only best bid/ask;
    ``last`` comes from the caller (``ws.py`` tracks the most recent
    ``aggTrade`` price), never invented here (CLAUDE.md: "no fake anything").
    """
    try:
        return NormalizedTicker(
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


def parse_depth20(raw: dict[str, Any]) -> NormalizedOrderBook:
    """``<symbol>@depth20`` -> :class:`NormalizedOrderBook`.

    A partial-book snapshot (top 20, no local diff-book), so ``is_snapshot``
    is always ``True``.
    """
    try:
        return NormalizedOrderBook(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            ts=event_ts(raw),
            bids=[
                BookLevel(
                    price=to_decimal(p, field="bid.price"), qty=to_decimal(q, field="bid.qty")
                )
                for p, q in raw["b"]
            ],
            asks=[
                BookLevel(
                    price=to_decimal(p, field="ask.price"), qty=to_decimal(q, field="ask.qty")
                )
                for p, q in raw["a"]
            ],
            sequence=int(raw["u"]),
            is_snapshot=True,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"malformed depth20 payload {raw!r}: {exc}", exchange=EXCHANGE
        ) from exc


def parse_kline_ws(raw: dict[str, Any]) -> NormalizedCandle:
    """``<symbol>@kline_1m`` -> :class:`NormalizedCandle`.

    ``is_final`` comes straight from the stream's own ``k.x`` flag, unlike
    the REST parser. ``close_time`` is the domain model's own *exclusive*
    boundary (``open_time`` + one minute), not Binance's inclusive ``k.T``.
    ``event_ts`` carries the frame's top-level ``E`` (push time) so the
    worker can order same-``open_time`` partials by arrival — REST candles
    have no such frame and leave it ``None``.
    """
    try:
        k = require_field(raw, "k")
        open_time = ms_to_datetime(k["t"], field="k.t")
        return NormalizedCandle(
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
    """``<symbol>@markPrice@1s`` -> :class:`NormalizedFunding`.

    Always ``funding_kind="estimated"``: a live mark/index reading, never a
    settled rate. ``metadata`` labels the one raw field with no normalized
    column of its own (``P``, the estimated settlement price).
    """
    try:
        next_funding_time = ms_to_datetime(raw["T"], field="T") if raw.get("T") else None
        metadata: dict[str, Any] = {}
        if "P" in raw:
            metadata["estimated_settle_price"] = raw["P"]
        return NormalizedFunding(
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
    """``<symbol>@forceOrder`` -> :class:`NormalizedLiquidation`."""
    try:
        order = require_field(raw, "o")
        side_raw = order["S"]
        side = OrderSide.SELL if side_raw == "SELL" else OrderSide.BUY
        return NormalizedLiquidation(
            exchange=EXCHANGE,
            symbol=require_field(order, "s"),
            ts=ms_to_datetime(order["T"], field="o.T"),
            side=side,
            qty=to_decimal(order["q"], field="o.q"),
            price=to_decimal(order["p"], field="o.p"),
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


#: F9: required for a bookTicker frame to count as well-formed even when
#: deferred (no known ``last_price`` yet) — otherwise an empty ``data: {}``
#: is indistinguishable from a real, healthy frame ("garbage is not proof
#: of life").
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
    """Dispatch one combined-stream frame's ``data`` by its ``stream`` name.

    Returns ``None`` for an unrecognized stream suffix, or for
    ``BOOK_TICKER`` when ``last_price`` is not yet known (no trade seen yet
    on this connection). Raises :class:`MalformedMessage` for a recognized
    but malformed payload; the caller catches it, logs, and counts it. A
    deferred ``BOOK_TICKER`` is still validated first (F9): well-formed
    still counts as proof of life, malformed never does.
    """
    channel = channel_for_stream_name(stream)
    if channel is None:
        raise MalformedMessage(f"unknown stream name {stream!r}", exchange=EXCHANGE)
    if channel is StreamChannel.BOOK_TICKER:
        if last_price is None:
            _validate_book_ticker_fields(data)
            return None
        return parse_book_ticker(data, last=last_price)
    return _PARSERS[channel](data)
