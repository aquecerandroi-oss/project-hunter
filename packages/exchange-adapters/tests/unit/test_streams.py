"""hunter_exchanges.binance.streams: channel naming, grouping, and WS payload parsing."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import OrderSide
from hunter_exchanges.base import MalformedMessage, StreamChannel
from hunter_exchanges.binance import streams

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---- channel naming / grouping ----------------------------------------------


def test_stream_name_lowercases_symbol_and_maps_channel_suffix() -> None:
    assert streams.stream_name("BTCUSDT", StreamChannel.TRADES) == "btcusdt@aggTrade"
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK) == "btcusdt@depth20"  # no suffix
    assert streams.stream_name("BTCUSDT", StreamChannel.MARK_PRICE) == "btcusdt@markPrice@1s"


def test_channel_for_stream_name_is_the_inverse_of_stream_name() -> None:
    for channel in StreamChannel:
        name = streams.stream_name("ETHUSDT", channel)
        assert streams.channel_for_stream_name(name) is channel


def test_channel_for_unknown_stream_name_is_none() -> None:
    assert streams.channel_for_stream_name("ethusdt@nonsense") is None


def test_group_symbols_splits_at_the_connection_limit() -> None:
    symbols = [f"SYM{i}" for i in range(450)]

    groups = streams.group_symbols(symbols, max_per_connection=200)

    assert [len(g) for g in groups] == [200, 200, 50]
    assert [s for group in groups for s in group] == symbols


def test_group_symbols_of_empty_input_is_one_empty_group() -> None:
    assert streams.group_symbols([]) == [[]]


def test_combined_stream_url_joins_with_slash() -> None:
    url = streams.combined_stream_url("wss://fstream.binance.com/stream?streams=", ["a@x", "b@y"])
    assert url == "wss://fstream.binance.com/stream?streams=a@x/b@y"


def test_book_depth_is_20() -> None:
    assert streams.BOOK_DEPTH == 20


def test_route_for_channel_splits_book_from_everything_else() -> None:
    assert streams.route_for_channel(StreamChannel.BOOK) == streams.ROUTE_PUBLIC
    assert streams.route_for_channel(StreamChannel.BOOK_TICKER) == streams.ROUTE_PUBLIC
    assert streams.route_for_channel(StreamChannel.TRADES) == streams.ROUTE_MARKET
    assert streams.route_for_channel(StreamChannel.KLINE_1M) == streams.ROUTE_MARKET
    assert streams.route_for_channel(StreamChannel.MARK_PRICE) == streams.ROUTE_MARKET
    assert streams.route_for_channel(StreamChannel.LIQUIDATIONS) == streams.ROUTE_MARKET


def test_split_channels_by_route_groups_and_drops_empty_routes() -> None:
    by_route = streams.split_channels_by_route(
        [StreamChannel.TRADES, StreamChannel.BOOK, StreamChannel.KLINE_1M]
    )

    assert by_route == {
        streams.ROUTE_MARKET: [StreamChannel.TRADES, StreamChannel.KLINE_1M],
        streams.ROUTE_PUBLIC: [StreamChannel.BOOK],
    }


def test_split_channels_by_route_of_empty_input_is_empty() -> None:
    assert streams.split_channels_by_route([]) == {}


# ---- WS payload parsing, one fixture per channel ----------------------------


def test_parse_agg_trade() -> None:
    raw = _load("ws_agg_trade.json")

    trade = streams.parse_agg_trade(raw)

    assert trade.symbol == "BTCUSDT"
    assert trade.price == Decimal("79498.10")
    assert trade.qty == Decimal("0.014")
    assert trade.side is OrderSide.SELL  # m=true: buyer is maker -> taker sold


def test_parse_book_ticker_uses_the_supplied_last_price() -> None:
    raw = _load("ws_book_ticker.json")

    ticker = streams.parse_book_ticker(raw, last=Decimal("79500"))

    assert ticker.symbol == "BTCUSDT"
    assert ticker.last == Decimal("79500")
    assert ticker.bid == Decimal("79501.60")
    assert ticker.ask == Decimal("79501.70")


def test_parse_depth20() -> None:
    raw = _load("ws_depth20.json")

    book = streams.parse_depth20(raw)

    assert book.is_snapshot is True
    assert book.symbol == "BTCUSDT"
    assert book.bids[0].price == Decimal("79497.20")
    assert book.asks[0].price == Decimal("79497.30")
    assert len(book.bids) == 20
    assert len(book.asks) == 20


def test_parse_kline_ws_reads_the_closed_flag() -> None:
    raw = _load("ws_kline_1m.json")

    candle = streams.parse_kline_ws(raw)

    assert candle.is_final is True
    assert candle.open == Decimal("79497.30")
    assert candle.close == Decimal("79498.10")


def test_parse_depth20_snapshot_fully_replaces_regardless_of_sequence_order() -> None:
    """M1 decision: each ``@depth20`` snapshot *replaces* the previous one in
    full — there is no local diff-book, so a lower ``u`` arriving after a
    higher one is not an error (no merge/gap logic to violate), and each
    snapshot stands alone as a complete top-20 view."""
    raw = _load("ws_depth20.json")
    newer = streams.parse_depth20(raw)

    stale = dict(raw)
    stale["u"] = raw["u"] - 1000  # an "older" snapshot arriving late
    older = streams.parse_depth20(stale)

    assert newer.sequence is not None
    assert older.sequence == newer.sequence - 1000
    assert older.is_snapshot is True and newer.is_snapshot is True
    assert len(older.bids) == len(newer.bids) == 20  # both stand alone, full top-20


def test_parse_depth20_result_contains_only_the_current_payloads_levels() -> None:
    """F14: a genuinely *different* second snapshot (the worst bid dropped,
    a mid-book ask repriced) must parse to exactly and only that payload's
    own levels — proving :func:`parse_depth20` is stateless (no accidental
    carryover/merge from a previous call), not just that varying ``u``
    alone leaves the (identical) level list unchanged."""
    raw = _load("ws_depth20.json")
    first = streams.parse_depth20(raw)

    changed = json.loads(json.dumps(raw))  # deep copy: never mutate the fixture
    removed_level = changed["b"].pop()  # drop the worst bid: now 19 levels
    changed["a"][-1][0] = "999999.00"  # reprice the worst ask to something impossible in `raw`
    changed["u"] = raw["u"] + 1
    second = streams.parse_depth20(changed)

    assert len(second.bids) == 19  # the removed level is gone, not merged back in
    assert second.asks[-1].price == Decimal("999999.00")
    assert all(level.price != Decimal("999999.00") for level in first.asks)  # `first` untouched
    removed_price = Decimal(removed_level[0])
    assert removed_price not in {level.price for level in second.bids}
    assert removed_price in {level.price for level in first.bids}  # only in the OLD snapshot


def test_parse_kline_ws_sets_event_ts_from_the_top_level_push_time() -> None:
    """T1.2b: ``E`` (frame push time) -> ``event_ts``, distinct from
    ``open_time``/``close_time`` (the kline's own boundaries)."""
    raw = _load("ws_kline_1m.json")

    candle = streams.parse_kline_ws(raw)

    assert candle.event_ts is not None
    assert candle.event_ts.timestamp() * 1000 == pytest.approx(raw["E"])
    assert candle.event_ts != candle.open_time


def test_parse_kline_ws_without_e_leaves_event_ts_none() -> None:
    raw = _load("ws_kline_1m.json")
    del raw["E"]

    candle = streams.parse_kline_ws(raw)

    assert candle.event_ts is None


def test_parse_kline_ws_open_candle_is_not_final() -> None:
    raw = _load("ws_kline_1m.json")
    raw["k"]["x"] = False

    candle = streams.parse_kline_ws(raw)

    assert candle.is_final is False


def test_duplicate_kline_ws_message_parses_identically_both_times() -> None:
    """Same guarantee as the REST parser's duplicate-candle test: parsing the
    same ``kline_1m`` push twice is pure — de-duplication is the caller's job
    (Redis `mkt:*:candles:1m` open->final precedence, T1.3)."""
    raw = _load("ws_kline_1m.json")

    first = streams.parse_kline_ws(raw)
    second = streams.parse_kline_ws(raw)

    assert first.model_dump(exclude={"received_at"}) == second.model_dump(exclude={"received_at"})


def test_parse_mark_price() -> None:
    raw = _load("ws_mark_price.json")

    funding = streams.parse_mark_price(raw)

    assert funding.symbol == "BTCUSDT"
    assert funding.funding_rate == Decimal("0.00000649")
    assert funding.mark_price == Decimal("79497.24142754")
    assert funding.next_funding_time is not None
    assert funding.funding_kind == "estimated"  # a live mark reading, never settled


def test_parse_mark_price_labels_the_estimated_settle_price_in_metadata() -> None:
    raw = _load("ws_mark_price.json")

    funding = streams.parse_mark_price(raw)

    assert funding.metadata["estimated_settle_price"] == raw["P"]


def test_parse_force_order() -> None:
    raw = _load("ws_force_order.json")

    liquidation = streams.parse_force_order(raw)

    assert liquidation.symbol == "BTCUSDT"
    assert liquidation.side is OrderSide.SELL
    assert liquidation.qty == Decimal("0.345")
    assert liquidation.price == Decimal("79210.50")
    assert liquidation.notional == Decimal("0.345") * Decimal("79210.50")


# ---- malformed messages ------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "parser"),
    [
        ("ws_agg_trade.json", streams.parse_agg_trade),
        ("ws_depth20.json", streams.parse_depth20),
        ("ws_kline_1m.json", streams.parse_kline_ws),
        ("ws_mark_price.json", streams.parse_mark_price),
        ("ws_force_order.json", streams.parse_force_order),
    ],
)
def test_malformed_ws_message_raises_malformed_message(fixture: str, parser: Any) -> None:
    raw = _load(fixture)
    # Corrupt every fixture the same way: drop the symbol field wherever it lives.
    if "s" in raw:
        del raw["s"]
    elif "o" in raw and "s" in raw["o"]:
        del raw["o"]["s"]

    with pytest.raises(MalformedMessage):
        parser(raw)


def test_parse_stream_message_dispatches_by_channel() -> None:
    raw = _load("ws_agg_trade.json")

    event = streams.parse_stream_message("btcusdt@aggTrade", raw, last_price=None)

    assert event is not None
    assert event.kind == "trade"


def test_parse_stream_message_returns_none_for_book_ticker_without_a_known_last_price() -> None:
    raw = _load("ws_book_ticker.json")

    event = streams.parse_stream_message("btcusdt@bookTicker", raw, last_price=None)

    assert event is None


def test_parse_stream_message_emits_ticker_once_a_last_price_is_known() -> None:
    raw = _load("ws_book_ticker.json")

    event = streams.parse_stream_message("btcusdt@bookTicker", raw, last_price=Decimal("79500"))

    assert event is not None
    assert event.kind == "ticker"
    assert event.last == Decimal("79500")


def test_parse_stream_message_raises_for_unknown_stream() -> None:
    with pytest.raises(MalformedMessage):
        streams.parse_stream_message("btcusdt@nonsense", {}, last_price=None)


def test_parse_stream_message_raises_for_a_malformed_deferred_book_ticker() -> None:
    """F9: a garbage bookTicker frame (missing required fields) must not be
    treated as well-formed just because it also happens to be deferred for
    want of a known last price — validated even in that branch, or a
    connection emitting nothing but garbage looks alive forever (resets the
    reconnect backoff, never increments malformed_count)."""
    with pytest.raises(MalformedMessage):
        streams.parse_stream_message("btcusdt@bookTicker", {}, last_price=None)


def test_parse_stream_message_raises_for_a_deferred_book_ticker_missing_one_field() -> None:
    raw = _load("ws_book_ticker.json")
    del raw["b"]  # best bid missing

    with pytest.raises(MalformedMessage):
        streams.parse_stream_message("btcusdt@bookTicker", raw, last_price=None)


def test_full_group_on_either_route_never_exceeds_the_1024_stream_limit() -> None:
    """F12: ``MAX_SYMBOLS_PER_CONNECTION`` (200) x every channel routed to
    one connection must never exceed Binance's documented
    ``MAX_STREAMS_PER_CONNECTION`` (1024) — safe today only because 200 x 4
    market channels = 800; adding a 5th/6th market channel later must fail
    a test here first, not silently overflow in production."""
    for route in (streams.ROUTE_PUBLIC, streams.ROUTE_MARKET):
        channels = [c for c in StreamChannel if streams.route_for_channel(c) == route]
        stream_count = streams.MAX_SYMBOLS_PER_CONNECTION * len(channels)
        assert stream_count <= streams.MAX_STREAMS_PER_CONNECTION


def test_parse_stream_message_accepts_a_valid_deferred_book_ticker() -> None:
    """A well-formed deferred bookTicker (all required fields present, just
    no known last price yet) still counts as proof of life — only ``None``
    is returned, never raised."""
    raw = _load("ws_book_ticker.json")

    event = streams.parse_stream_message("btcusdt@bookTicker", raw, last_price=None)

    assert event is None
