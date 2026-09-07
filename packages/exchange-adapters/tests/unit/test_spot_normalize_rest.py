"""hunter_exchanges.binance_spot.normalize: SPOT REST payload -> Normalized*.

Every fixture here was recorded from the real public ``api.binance.com``
endpoints (no API key) by ``hunter_exchanges.testing.record_spot`` on
2026-09-06 - the parsers are checked against Binance's actual wire format,
never a hand-guessed shape.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import MarketStatus, MarketType, OrderSide, Timeframe
from hunter_core.domain.market import NormalizedMarket
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance_spot import normalize

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_exchange_info_keeps_only_usdt_trading_spot_pairs() -> None:
    markets = normalize.parse_exchange_info(_load("spot_exchange_info.json"))

    assert {m.symbol for m in markets} == {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
    assert all(m.market_type is MarketType.SPOT for m in markets)
    assert all(m.exchange == "binance" for m in markets)
    assert all(m.quote == "USDT" for m in markets)
    assert all(m.status is MarketStatus.ACTIVE for m in markets)
    assert all(m.contract_size is None and m.max_leverage is None for m in markets)


def test_parse_exchange_info_drops_a_halted_symbol() -> None:
    """NEOBTC in the fixture is a real ``BREAK`` (halted) pair: never monitored."""
    markets = normalize.parse_exchange_info(_load("spot_exchange_info.json"))

    assert "NEOBTC" not in {m.symbol for m in markets}


def test_parse_exchange_info_drops_a_non_usdt_quote() -> None:
    markets = normalize.parse_exchange_info(_load("spot_exchange_info.json"))

    assert "ETHBTC" not in {m.symbol for m in markets}


def test_parse_market_reads_the_market_order_filters_byte_for_byte() -> None:
    raw = _load("spot_exchange_info.json")
    btc = next(s for s in raw["symbols"] if s["symbol"] == "BTCUSDT")

    market = normalize.parse_market(btc)

    assert market.tick_size == Decimal("0.01000000")
    assert market.step_size == Decimal("0.00001000")
    assert market.min_notional == Decimal("5.00000000")
    filters = market.metadata["spot_market_filters"]
    assert filters["market_max_qty"] == "112.97976583"
    assert filters["apply_min_to_market"] is True
    assert filters["avg_price_mins"] == 5


def test_parse_market_rejects_an_entry_without_the_required_filters() -> None:
    with pytest.raises(MalformedMessage):
        normalize.parse_market({"symbol": "XXXUSDT", "status": "TRADING", "filters": []})


def test_parse_request_weight_limit_reads_the_real_spot_budget() -> None:
    """The authority for ``rest.py``'s bucket: 6000 weight / 1 min / IP."""
    capacity, period_s = normalize.parse_request_weight_limit(_load("spot_exchange_info.json"))

    assert (capacity, period_s) == (6000, 60.0)


def test_parse_ticker_24h_carries_bid_ask_and_quote_volume() -> None:
    """Unlike the USDS-M endpoint, spot ``ticker/24hr`` does carry bid/ask -
    and ``quoteVolume`` is the 24h USDT volume the 50M floor (D1) reads."""
    ticker = normalize.parse_ticker_24h(_load("spot_ticker_24hr.json"))

    assert ticker.exchange == "binance"
    assert ticker.symbol == "BTCUSDT"
    assert ticker.last == Decimal("80488.00000000")
    assert ticker.bid == Decimal("80488.00000000")
    assert ticker.ask == Decimal("80488.01000000")
    assert ticker.bid_qty == Decimal("0.15161000")
    assert ticker.quote_volume_24h == Decimal("697710005.43687120")
    assert ticker.ts == datetime.fromtimestamp(1788738439012 / 1000, tz=UTC)


def test_parse_ticker_24h_list_parses_every_row() -> None:
    tickers = [normalize.parse_ticker_24h(row) for row in _load("spot_ticker_24hr_all.json")]

    assert {t.symbol for t in tickers} == {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
    assert all(t.quote_volume_24h is not None for t in tickers)


def test_parse_depth_uses_the_receive_time_because_spot_sends_none() -> None:
    """Binance's spot ``/api/v3/depth`` payload has ``lastUpdateId`` and the
    two sides - and no timestamp at all. The book is stamped with the local
    receive time, and ``ts == received_at`` exactly, which is how a reader
    tells "no exchange clock here" from a real exchange event time.
    """
    received_at = datetime(2026, 9, 6, 23, 47, tzinfo=UTC)

    book = normalize.parse_depth(
        _load("spot_depth.json"), symbol="BTCUSDT", received_at=received_at
    )

    assert book.exchange == "binance"
    assert book.symbol == "BTCUSDT"
    assert book.ts == received_at == book.received_at
    assert book.is_snapshot is True
    assert book.sequence == 99769463659
    assert book.bids[0].price == Decimal("80488.00000000")
    assert book.best_bid is not None and book.best_ask is not None
    assert book.best_bid < book.best_ask


def test_parse_depth_100_keeps_every_level_the_walk_needs() -> None:
    book = normalize.parse_depth(
        _load("spot_depth_100.json"),
        symbol="BTCUSDT",
        received_at=datetime(2026, 9, 6, tzinfo=UTC),
    )

    assert len(book.bids) == 100
    assert len(book.asks) == 100


def test_parse_depth_rejects_a_book_out_of_price_order() -> None:
    with pytest.raises(MalformedMessage):
        normalize.parse_depth(
            {"lastUpdateId": 1, "bids": [["10", "1"], ["11", "1"]], "asks": [["12", "1"]]},
            symbol="BTCUSDT",
            received_at=datetime(2026, 9, 6, tzinfo=UTC),
        )


def test_parse_trades_maps_the_taker_side_from_is_buyer_maker() -> None:
    trades = normalize.parse_trades(_load("spot_trades.json"), symbol="BTCUSDT")

    assert len(trades) == 5
    first = trades[0]
    assert first.exchange == "binance"
    assert first.trade_id == "6659836474"
    assert first.price == Decimal("80488.00000000")
    assert first.qty == Decimal("0.00200000")
    assert first.side is OrderSide.SELL  # isBuyerMaker true -> the taker sold
    assert first.ts == datetime.fromtimestamp(1788738438602 / 1000, tz=UTC)


def test_parse_agg_trades_uses_the_aggregate_id() -> None:
    trades = normalize.parse_agg_trades(_load("spot_agg_trades.json"), symbol="BTCUSDT")

    assert trades[0].trade_id == "4056668525"
    assert trades[0].side is OrderSide.SELL
    assert all(t.symbol == "BTCUSDT" for t in trades)


def test_parse_avg_price_is_the_market_notional_reference() -> None:
    avg = normalize.parse_avg_price(_load("spot_avg_price.json"), symbol="BTCUSDT")

    assert avg.price == Decimal("80471.72575004")
    assert avg.mins == 5
    assert avg.close_time == datetime.fromtimestamp(1788738439834 / 1000, tz=UTC)


def test_parse_klines_reuses_the_shared_binance_row_parser() -> None:
    now = datetime.fromtimestamp(1788738450, tz=UTC)  # inside the last row minute

    candles = normalize.parse_klines(_load("spot_klines.json"), symbol="BTCUSDT", now=now)

    assert len(candles) == 5
    assert candles[0].timeframe is Timeframe.M1
    assert candles[0].exchange == "binance"
    assert candles[0].open == Decimal("80453.34000000")
    assert candles[0].quote_volume == Decimal("5324810.58426430")
    assert candles[0].is_final is True
    assert candles[-1].is_final is False  # still forming at `now`


def test_parse_server_time_reads_the_exchange_clock() -> None:
    assert normalize.parse_server_time(_load("spot_server_time.json")) == datetime.fromtimestamp(
        1788738437731 / 1000, tz=UTC
    )


def test_every_parser_refuses_a_float_price() -> None:
    """CLAUDE.md: money is Decimal, never float - a float in the payload is
    a malformed message, not something to coerce."""
    with pytest.raises(MalformedMessage):
        normalize.parse_trades(
            [{"id": 1, "price": 80488.0, "qty": "1", "time": 1, "isBuyerMaker": False}],
            symbol="BTCUSDT",
        )


def test_normalized_market_is_a_spot_market_not_a_perpetual_one() -> None:
    markets = normalize.parse_exchange_info(_load("spot_exchange_info.json"))
    btc: NormalizedMarket = next(m for m in markets if m.symbol == "BTCUSDT")

    assert (btc.exchange, btc.symbol, btc.market_type) == ("binance", "BTCUSDT", MarketType.SPOT)
