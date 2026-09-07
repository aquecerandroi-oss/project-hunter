"""T3.0b — every normalized event says which listing it came from.

The USDS-M parsers keep building without the field (default ``PERPETUAL``);
the spot parsers state ``SPOT``. A spot candle that came back labelled
``perpetual`` would be written straight onto the perpetual's hot-state key,
which is exactly the collision T3.0 exists to prevent — and the REST kline
parser is *shared* between the two adapters, so it is the likeliest place for
that to happen silently.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_exchanges.binance import normalize as usdm_normalize
from hunter_exchanges.binance import streams as usdm_streams
from hunter_exchanges.binance_spot import normalize as spot_normalize
from hunter_exchanges.binance_spot import streams as spot_streams

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()
RECEIVED_AT = datetime(2026, 9, 6, 23, 47, 25, tzinfo=UTC)
NOW = datetime(2026, 9, 6, 23, 47, 25, tzinfo=UTC)


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _envelope(name: str) -> tuple[str, dict[str, Any]]:
    raw = _load(name)
    return raw["stream"], raw["data"]


# --- USDS-M: unchanged, still perpetual --------------------------------------


def test_usdm_rest_klines_are_perpetual() -> None:
    candles = usdm_normalize.parse_klines(_load("klines.json"), symbol="BTCUSDT", now=NOW)
    assert candles
    assert {c.market_type for c in candles} == {MarketType.PERPETUAL}


def test_usdm_stream_events_are_perpetual() -> None:
    events = (
        usdm_streams.parse_agg_trade(_load("ws_agg_trade.json")),
        usdm_streams.parse_book_ticker(_load("ws_book_ticker.json"), last=Decimal("100")),
        usdm_streams.parse_kline_ws(_load("ws_kline_1m.json")),
        usdm_streams.parse_depth20(_load("ws_depth20.json")),
    )
    assert {event.market_type for event in events} == {MarketType.PERPETUAL}


# --- SPOT: says so, on every event ------------------------------------------


def test_spot_rest_klines_are_spot() -> None:
    """The shared USDS-M row parser must not stamp a spot candle as a perpetual."""
    candles = spot_normalize.parse_klines(_load("spot_klines.json"), symbol="BTCUSDT", now=NOW)
    assert candles
    assert {c.market_type for c in candles} == {MarketType.SPOT}


def test_spot_rest_ticker_depth_and_trades_are_spot() -> None:
    ticker = spot_normalize.parse_ticker_24h(_load("spot_ticker_24hr.json"))
    book = spot_normalize.parse_depth(
        _load("spot_depth.json"), symbol="BTCUSDT", received_at=RECEIVED_AT
    )
    trades = spot_normalize.parse_trades(_load("spot_trades.json"), symbol="BTCUSDT")
    agg = spot_normalize.parse_agg_trades(_load("spot_agg_trades.json"), symbol="BTCUSDT")

    assert ticker.market_type is MarketType.SPOT
    assert book.market_type is MarketType.SPOT
    assert trades and {t.market_type for t in trades} == {MarketType.SPOT}
    assert agg and {t.market_type for t in agg} == {MarketType.SPOT}


@pytest.mark.parametrize(
    "name",
    ["spot_ws_agg_trade.json", "spot_ws_kline_1m.json", "spot_ws_depth20.json"],
)
def test_spot_stream_events_are_spot(name: str) -> None:
    stream, data = _envelope(name)
    event = spot_streams.parse_stream_message(
        stream, data, last_price=None, received_at=RECEIVED_AT
    )
    assert event is not None
    assert event.market_type is MarketType.SPOT


def test_spot_book_ticker_is_spot() -> None:
    stream, data = _envelope("spot_ws_book_ticker.json")
    ticker = spot_streams.parse_stream_message(
        stream, data, last_price=Decimal("100"), received_at=RECEIVED_AT
    )
    assert ticker is not None
    assert ticker.market_type is MarketType.SPOT
