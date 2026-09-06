"""hunter_exchanges.binance.streams: channel naming, grouping, and WS payload parsing."""

from __future__ import annotations

import json
from datetime import UTC
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
    # T1.6b-A: default book cadence is now 500ms (was implicit 250ms/no suffix).
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK) == "btcusdt@depth20@500ms"
    assert streams.stream_name("BTCUSDT", StreamChannel.MARK_PRICE) == "btcusdt@markPrice@1s"


def test_channel_for_stream_name_is_the_inverse_of_stream_name() -> None:
    for channel in StreamChannel:
        name = streams.stream_name("ETHUSDT", channel)
        assert streams.channel_for_stream_name(name) is channel


def test_channel_for_unknown_stream_name_is_none() -> None:
    assert streams.channel_for_stream_name("ethusdt@nonsense") is None


# ---- T1.6b-A: configurable book cadence (A5) ---------------------------------


@pytest.fixture(autouse=True)
def _restore_default_book_cadence() -> Any:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    """``set_book_cadence_ms`` is process-wide state — every test that changes
    it must leave the default (500ms) in place for every other test."""
    yield
    streams.set_book_cadence_ms(streams.DEFAULT_BOOK_CADENCE_MS)


def test_default_book_cadence_is_500ms() -> None:
    assert streams.DEFAULT_BOOK_CADENCE_MS == 500


def test_set_book_cadence_ms_250_produces_no_suffix() -> None:
    streams.set_book_cadence_ms(250)
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK) == "btcusdt@depth20"


def test_set_book_cadence_ms_none_produces_no_suffix() -> None:
    streams.set_book_cadence_ms(None)
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK) == "btcusdt@depth20"


def test_set_book_cadence_ms_100_produces_the_100ms_suffix() -> None:
    streams.set_book_cadence_ms(100)
    assert streams.stream_name("BTCUSDT", StreamChannel.BOOK) == "btcusdt@depth20@100ms"


@pytest.mark.parametrize("suffix", ["depth20", "depth20@100ms", "depth20@250ms", "depth20@500ms"])
def test_channel_for_stream_name_resolves_every_book_cadence_suffix(suffix: str) -> None:
    """The reverse map must route every cadence variant to BOOK regardless of
    which one is currently active — a connection opened before a cadence
    change can still be receiving frames named after the old one."""
    assert streams.channel_for_stream_name(f"btcusdt@{suffix}") is StreamChannel.BOOK


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
    """Fully filled order (KB-0017): ``o.X == "FILLED"`` so the executed
    quantity (``o.z``) equals the original (``o.q``), but ``price`` must
    still prefer the average fill price (``o.ap``) over the order price
    (``o.p``) — they can differ even on a full fill."""
    raw = _load("ws_force_order.json")

    liquidation = streams.parse_force_order(raw)

    assert liquidation.symbol == "BTCUSDT"
    assert liquidation.side is OrderSide.SELL
    assert liquidation.qty == Decimal("0.345")  # o.z, same as o.q here (FILLED)
    assert liquidation.price == Decimal("79215.00")  # o.ap, not o.p
    assert liquidation.notional == Decimal("0.345") * Decimal("79215.00")


def test_parse_force_order_uses_executed_qty_not_original_qty_on_partial_fill() -> None:
    """KB-0017 bug: a liquidation order for 10 BTC that only fills 1 BTC
    (``o.X == "PARTIALLY_FILLED"``) must report ``qty == o.z`` (1.000), never
    ``o.q`` (10.000) — the original parser overstated forced flow here."""
    raw = _load("ws_force_order_partial.json")

    liquidation = streams.parse_force_order(raw)

    assert liquidation.qty == Decimal("1.000")  # o.z, not o.q ("10.000")
    assert liquidation.price == Decimal("79050.00")  # o.ap
    assert liquidation.notional == Decimal("1.000") * Decimal("79050.00")


def test_parse_force_order_reports_zero_qty_when_nothing_executed_yet() -> None:
    """``o.X == "NEW"`` with ``o.z == "0"``: nothing has executed. ``qty``
    must be an explicit zero, never fall back to the original ``o.q`` — a
    liquidation order that hasn't traded yet isn't forced flow. ``o.ap`` is
    also ``"0"`` in this state (no fills to average), so ``price`` falls
    back to the order price ``o.p``."""
    raw = _load("ws_force_order_unfilled.json")

    liquidation = streams.parse_force_order(raw)

    assert liquidation.qty == Decimal("0")
    assert liquidation.price == Decimal("78500.00")  # o.p, ap is "0" (no fills)
    assert liquidation.notional == Decimal("0")


def test_parse_force_order_falls_back_to_order_price_when_ap_key_is_absent() -> None:
    """Defensive: even if ``o.ap`` were missing outright (not just ``"0"``),
    the parser must not raise — it falls back to ``o.p``."""
    raw = json.loads(json.dumps(_load("ws_force_order.json")))
    del raw["o"]["ap"]

    liquidation = streams.parse_force_order(raw)

    assert liquidation.price == Decimal("79210.50")  # o.p, no o.ap to prefer


def test_parse_force_order_missing_z_raises_malformed_message() -> None:
    raw = json.loads(json.dumps(_load("ws_force_order.json")))
    del raw["o"]["z"]

    with pytest.raises(MalformedMessage):
        streams.parse_force_order(raw)


def test_parse_force_order_identity_fields_are_unaffected_by_the_qty_price_fix() -> None:
    """``exchange``/``symbol``/``side``/``ts`` come from ``o.s``/``o.S``/``o.T``
    only — untouched by the o.q/o.z, o.p/o.ap change — so
    ``hunter_market_worker.publication.liquidation_id`` still derives those
    four components of its hash exactly as before. (It also folds ``price``
    and ``qty`` into that hash, so ids for non-``FILLED`` orders — and any
    order where ``ap != p`` — do change after this fix; see
    ``.claude/state/notes-liquidations.md``.)"""
    filled = streams.parse_force_order(_load("ws_force_order.json"))
    partial = streams.parse_force_order(_load("ws_force_order_partial.json"))

    for liquidation in (filled, partial):
        assert liquidation.exchange == "binance"
        assert liquidation.symbol == "BTCUSDT"

    assert filled.side is OrderSide.SELL
    assert partial.side is OrderSide.SELL
    assert filled.ts.tzinfo is not None
    assert partial.ts.tzinfo is not None


# ---- T1.6b-A: model_construct() correctness guarantees ----------------------
#
# A2/A6 (``t16b-profile.md``: pydantic __init__ was 20.36% self time at 200
# markets) switch every parser here from ``Model(...)`` (validated) to
# ``Model.model_construct(...)`` (no validators run at all). These tests pin
# the guarantees that used to come from pydantic's field/model validators and
# now must hold by construction in the parser itself.

_ALL_CHANNEL_PARSERS: list[tuple[str, Any]] = [
    ("ws_agg_trade.json", streams.parse_agg_trade),
    ("ws_depth20.json", streams.parse_depth20),
    ("ws_kline_1m.json", streams.parse_kline_ws),
    ("ws_mark_price.json", streams.parse_mark_price),
    ("ws_force_order.json", streams.parse_force_order),
]


@pytest.mark.parametrize(("fixture", "parser"), _ALL_CHANNEL_PARSERS)
def test_model_construct_events_have_utc_aware_ts(fixture: str, parser: Any) -> None:
    raw = _load(fixture)

    event = parser(raw)

    ts = getattr(event, "ts", None) or event.open_time  # NormalizedCandle has no `ts`
    assert ts.tzinfo is not None
    assert ts.utcoffset() == UTC.utcoffset(None)


@pytest.mark.parametrize(("fixture", "parser"), _ALL_CHANNEL_PARSERS)
def test_model_construct_events_have_a_populated_utc_aware_received_at(
    fixture: str, parser: Any
) -> None:
    raw = _load(fixture)

    event = parser(raw)

    assert event.received_at is not None
    assert event.received_at.tzinfo is not None
    assert event.received_at.utcoffset() == UTC.utcoffset(None)


def test_model_construct_book_ticker_has_utc_aware_ts_and_received_at() -> None:
    raw = _load("ws_book_ticker.json")

    ticker = streams.parse_book_ticker(raw, last=Decimal("79500"))

    assert ticker.ts.tzinfo is not None
    assert ticker.received_at.tzinfo is not None


def test_parse_force_order_still_defaults_notional_to_qty_times_price() -> None:
    """The model_validator that used to compute this default no longer runs
    under ``model_construct`` — the parser must set it explicitly."""
    raw = _load("ws_force_order.json")

    liquidation = streams.parse_force_order(raw)

    assert liquidation.notional == liquidation.qty * liquidation.price


def test_parse_depth20_rejects_a_negative_qty() -> None:
    """``BookLevel.qty``'s ``Field(ge=0)`` doesn't run under
    ``model_construct`` — the parser must check it explicitly."""
    raw = json.loads(json.dumps(_load("ws_depth20.json")))
    raw["b"][0][1] = "-1"

    with pytest.raises(MalformedMessage):
        streams.parse_depth20(raw)


def test_parse_depth20_rejects_bids_not_sorted_descending() -> None:
    raw = json.loads(json.dumps(_load("ws_depth20.json")))
    raw["b"][0], raw["b"][1] = raw["b"][1], raw["b"][0]  # swap: no longer descending

    with pytest.raises(MalformedMessage):
        streams.parse_depth20(raw)


def test_parse_depth20_rejects_asks_not_sorted_ascending() -> None:
    raw = json.loads(json.dumps(_load("ws_depth20.json")))
    raw["a"][0], raw["a"][1] = raw["a"][1], raw["a"][0]  # swap: no longer ascending

    with pytest.raises(MalformedMessage):
        streams.parse_depth20(raw)


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
