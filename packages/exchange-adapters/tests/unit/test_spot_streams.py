"""hunter_exchanges.binance_spot.streams: SPOT combined-stream frames.

Fixtures are full envelopes (``{"stream": ..., "data": ...}``) recorded from
the real ``wss://stream.binance.com:9443`` connection - on spot the partial
depth payload carries no symbol at all, so the stream name is part of the
message's meaning.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import OrderSide
from hunter_exchanges.base import MalformedMessage, StreamChannel
from hunter_exchanges.binance_spot import streams

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()
RECEIVED_AT = datetime(2026, 9, 6, 23, 47, 25, tzinfo=UTC)


def _envelope(name: str) -> tuple[str, dict[str, Any]]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return raw["stream"], raw["data"]


def test_stream_names_are_the_four_spot_channels() -> None:
    assert streams.stream_name("BTCUSDT", StreamChannel.TRADES) == "btcusdt@aggTrade"
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK_TICKER) == "btcusdt@bookTicker"
    assert streams.stream_name("BTCUSDT", StreamChannel.KLINE_1M) == "btcusdt@kline_1m"
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK) == "btcusdt@depth20@100ms"


@pytest.mark.parametrize("channel", [StreamChannel.MARK_PRICE, StreamChannel.LIQUIDATIONS])
def test_spot_has_no_derivatives_channels(channel: StreamChannel) -> None:
    """No funding, no open interest, no liquidations on spot - asking for one
    is a programming error, never an empty stream that looks healthy."""
    with pytest.raises(ValueError, match="spot"):
        streams.stream_name("BTCUSDT", channel)


def test_every_channel_shares_one_route_and_one_url() -> None:
    by_route = streams.split_channels_by_route(
        [StreamChannel.TRADES, StreamChannel.BOOK, StreamChannel.BOOK_TICKER]
    )

    assert list(by_route) == [streams.ROUTE_SPOT]
    assert streams.WS_BASE_URL.startswith("wss://stream.binance.com:9443")


def test_channel_and_symbol_are_recoverable_from_the_stream_name() -> None:
    assert streams.channel_for_stream_name("btcusdt@depth20@100ms") is StreamChannel.BOOK
    assert streams.symbol_for_stream_name("btcusdt@depth20@100ms") == "BTCUSDT"
    assert streams.channel_for_stream_name("btcusdt@somethingElse") is None


def test_parse_agg_trade_from_the_recorded_frame() -> None:
    stream, data = _envelope("spot_ws_agg_trade.json")

    trade = streams.parse_stream_message(stream, data, last_price=None, received_at=RECEIVED_AT)

    assert trade is not None
    assert trade.kind == "trade"
    assert trade.exchange == "binance"
    assert trade.symbol == "BTCUSDT"
    assert trade.trade_id == "4056668578"
    assert trade.price == Decimal("80482.56000000")
    assert trade.qty == Decimal("0.00627000")
    assert trade.side is OrderSide.SELL
    assert trade.ts == datetime.fromtimestamp(1788738442351 / 1000, tz=UTC)


def test_parse_kline_from_the_recorded_frame() -> None:
    stream, data = _envelope("spot_ws_kline_1m.json")

    candle = streams.parse_stream_message(stream, data, last_price=None, received_at=RECEIVED_AT)

    assert candle is not None
    assert candle.kind == "candle"
    assert candle.symbol == "BTCUSDT"
    assert candle.open_time == datetime.fromtimestamp(1788738420, tz=UTC)
    assert candle.close == Decimal("80478.84000000")
    assert candle.trade_count == 2082
    assert candle.is_final is False  # "x": false - still forming
    assert candle.event_ts == datetime.fromtimestamp(1788738444060 / 1000, tz=UTC)


def test_parse_depth20_takes_the_symbol_from_the_stream_name() -> None:
    """The recorded spot partial-depth payload has ``lastUpdateId``, ``bids``
    and ``asks`` - no symbol and no timestamp."""
    stream, data = _envelope("spot_ws_depth20.json")
    assert "s" not in data and "E" not in data and "T" not in data

    book = streams.parse_stream_message(stream, data, last_price=None, received_at=RECEIVED_AT)

    assert book is not None
    assert book.kind == "book"
    assert book.symbol == "BTCUSDT"
    assert book.sequence == 99769467122
    assert book.is_snapshot is True
    assert len(book.bids) == 20
    assert len(book.asks) == 20
    assert book.ts == RECEIVED_AT == book.received_at


def test_book_ticker_waits_for_a_traded_price_instead_of_inventing_one() -> None:
    """Spot ``bookTicker`` carries no last price (and no event time): before
    any aggTrade is seen the frame is valid but yields no ticker."""
    stream, data = _envelope("spot_ws_book_ticker.json")

    assert (
        streams.parse_stream_message(stream, data, last_price=None, received_at=RECEIVED_AT) is None
    )

    ticker = streams.parse_stream_message(
        stream, data, last_price=Decimal("80482.56"), received_at=RECEIVED_AT
    )
    assert ticker is not None
    assert ticker.kind == "ticker"
    assert ticker.symbol == "BTCUSDT"
    assert ticker.bid == Decimal("80482.56000000")
    assert ticker.ask == Decimal("80482.57000000")
    assert ticker.bid_qty == Decimal("0.00763000")
    assert ticker.last == Decimal("80482.56")
    assert ticker.ts == RECEIVED_AT == ticker.received_at


def test_a_book_ticker_missing_a_side_is_malformed_even_when_deferred() -> None:
    with pytest.raises(MalformedMessage):
        streams.parse_stream_message(
            "btcusdt@bookTicker",
            {"u": 1, "s": "BTCUSDT", "b": "1", "B": "1"},
            last_price=None,
            received_at=RECEIVED_AT,
        )


def test_an_unknown_stream_name_is_malformed() -> None:
    with pytest.raises(MalformedMessage):
        streams.parse_stream_message(
            "btcusdt@somethingElse", {}, last_price=None, received_at=RECEIVED_AT
        )


def test_a_depth_frame_with_a_crossed_book_is_malformed() -> None:
    with pytest.raises(MalformedMessage):
        streams.parse_stream_message(
            "btcusdt@depth20@100ms",
            {"lastUpdateId": 1, "bids": [["10", "1"], ["11", "1"]], "asks": [["12", "1"]]},
            last_price=None,
            received_at=RECEIVED_AT,
        )


def test_a_negative_quantity_is_malformed() -> None:
    with pytest.raises(MalformedMessage):
        streams.parse_stream_message(
            "btcusdt@depth20@100ms",
            {"lastUpdateId": 1, "bids": [["10", "-1"]], "asks": [["12", "1"]]},
            last_price=None,
            received_at=RECEIVED_AT,
        )


def test_group_symbols_respects_the_spot_connection_budget() -> None:
    groups = streams.group_symbols([f"SYM{i}USDT" for i in range(450)])

    assert [len(g) for g in groups] == [200, 200, 50]
    assert streams.MAX_STREAMS_PER_CONNECTION == 1024
    assert streams.MAX_CONTROL_MESSAGES_PER_S == 5
