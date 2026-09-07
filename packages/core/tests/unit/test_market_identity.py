"""T3.0b — ``market_type`` in every market identity that lives outside Postgres.

``BTCUSDT`` is two different markets on Binance (the spot pair and the USDS-M
perpetual). The database already tells them apart (``UNIQUE (exchange_id,
symbol, market_type)``); Redis keys and the normalized event models did not.

Two properties are pinned here and neither may ever be relaxed:

1. **the perpetual's identity does not move.** Four shards and a live scanner
   are running against the keys below right now — every one of them has to
   come out byte for byte identical, whether ``market_type`` is omitted or
   passed explicitly as ``PERPETUAL``;
2. **spot never lands on the perpetual's key**, and a payload written before
   this change (no ``market_type`` on the wire) reads back as the perpetual it
   was.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from fnmatch import fnmatchcase
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType, OrderSide, Timeframe
from hunter_core.domain.market import (
    BookLevel,
    NormalizedCandle,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
    from_wire,
    to_wire,
)
from hunter_core.redis import keys

pytestmark = pytest.mark.unit

TS = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

# The exact strings that are in Redis today. Written out by hand, not built
# from the functions under test: a snapshot that calls the builder proves
# nothing about the bytes the running system already uses.
LEGACY_KEYS = {
    "ticker": "mkt:binance:BTCUSDT:ticker",
    "book": "mkt:binance:BTCUSDT:book",
    "trades": "mkt:binance:BTCUSDT:trades",
    "candles_1m": "mkt:binance:BTCUSDT:candles:1m",
    "derivatives": "mkt:binance:BTCUSDT:deriv",
    "features": "feat:binance:BTCUSDT",
    "opportunity": "opp:binance:BTCUSDT",
    "scanner_state": "scan:state:binance:BTCUSDT",
    "baseline_projection": "scan:baseline:binance:BTCUSDT",
}


def _built(name: str, *, market_type: MarketType | None = None) -> str:
    builder = getattr(keys, name)
    if market_type is None:
        return builder("binance", "BTCUSDT")
    return builder("binance", "BTCUSDT", market_type)


@pytest.mark.parametrize(("name", "expected"), sorted(LEGACY_KEYS.items()))
def test_perpetual_keys_are_unchanged(name: str, expected: str) -> None:
    """Omitted and explicit ``PERPETUAL`` both produce the key already in Redis."""
    assert _built(name) == expected
    assert _built(name, market_type=MarketType.PERPETUAL) == expected


@pytest.mark.parametrize(("name", "legacy"), sorted(LEGACY_KEYS.items()))
def test_spot_keys_never_collide_with_perpetual_ones(name: str, legacy: str) -> None:
    spot = _built(name, market_type=MarketType.SPOT)
    assert spot != legacy
    assert ":spot:" in spot


def test_spot_key_layout() -> None:
    """The venue segment grows a type; the symbol and the suffix do not move."""
    assert keys.ticker("binance", "BTCUSDT", MarketType.SPOT) == "mkt:binance:spot:BTCUSDT:ticker"
    assert keys.candles_1m("binance", "BTCUSDT", MarketType.SPOT) == (
        "mkt:binance:spot:BTCUSDT:candles:1m"
    )
    assert keys.features("binance", "BTCUSDT", MarketType.SPOT) == "feat:binance:spot:BTCUSDT"
    assert keys.opportunity("binance", "BTCUSDT", MarketType.SPOT) == "opp:binance:spot:BTCUSDT"
    assert keys.scanner_state("binance", "BTCUSDT", MarketType.SPOT) == (
        "scan:state:binance:spot:BTCUSDT"
    )
    assert keys.baseline_projection("binance", "BTCUSDT", MarketType.SPOT) == (
        "scan:baseline:binance:spot:BTCUSDT"
    )


def test_tape_coverage_is_per_venue_and_type() -> None:
    assert keys.tape_coverage("binance") == "mkt:binance:coverage"
    assert keys.tape_coverage("binance", MarketType.PERPETUAL) == "mkt:binance:coverage"
    assert keys.tape_coverage("binance", MarketType.SPOT) == "mkt:binance:spot:coverage"


def test_market_slug_is_discriminated() -> None:
    assert keys.market_slug("binance", "BTCUSDT") == "binance:BTCUSDT"
    assert keys.market_slug("binance", "BTCUSDT", MarketType.SPOT) == "binance:spot:BTCUSDT"


def test_market_heartbeat_keeps_the_running_shard_layout() -> None:
    assert keys.market_heartbeat("binance") == "hb:market:binance"
    assert keys.market_heartbeat("binance", 1, 4) == "hb:market:binance:1of4"
    assert keys.market_heartbeat_shard_pattern("binance") == "hb:market:binance:*of*"


def test_spot_heartbeat_is_not_matched_by_the_perpetual_shard_pattern() -> None:
    """The type goes *before* the exchange here, unlike the ``mkt:`` keys.

    Redis glob ``*`` matches ``:`` too, so ``hb:market:binance:spot:0of4``
    would be swept up by the perpetual's own ``hb:market:binance:*of*`` scan
    and counted as a missing/extra USDS-M shard by ``market_shards.py``.
    """
    solo = keys.market_heartbeat("binance", market_type=MarketType.SPOT)
    sharded = keys.market_heartbeat("binance", 0, 4, market_type=MarketType.SPOT)
    perp_pattern = keys.market_heartbeat_shard_pattern("binance")
    spot_pattern = keys.market_heartbeat_shard_pattern("binance", MarketType.SPOT)

    assert solo == "hb:market:spot:binance"
    assert sharded == "hb:market:spot:binance:0of4"
    assert spot_pattern == "hb:market:spot:binance:*of*"
    assert not fnmatchcase(sharded, perp_pattern)
    assert fnmatchcase(sharded, spot_pattern)
    assert not fnmatchcase(keys.market_heartbeat("binance", 0, 4), spot_pattern)


def _ticker(**extra: Any) -> NormalizedTicker:
    return NormalizedTicker(
        exchange="binance", symbol="BTCUSDT", ts=TS, last=Decimal("100"), **extra
    )


def _trade(**extra: Any) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="binance",
        symbol="BTCUSDT",
        ts=TS,
        trade_id="1",
        price=Decimal("100"),
        qty=Decimal("1"),
        side=OrderSide.BUY,
        **extra,
    )


def _book(**extra: Any) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        exchange="binance",
        symbol="BTCUSDT",
        ts=TS,
        bids=[BookLevel(price=Decimal("99"), qty=Decimal("1"))],
        asks=[BookLevel(price=Decimal("101"), qty=Decimal("1"))],
        is_snapshot=True,
        **extra,
    )


def _candle(**extra: Any) -> NormalizedCandle:
    return NormalizedCandle(
        exchange="binance",
        symbol="BTCUSDT",
        timeframe=Timeframe.M1,
        open_time=TS,
        close_time=datetime(2026, 9, 7, 12, 1, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("5"),
        is_final=True,
        **extra,
    )


EVENT_FACTORIES = {
    "ticker": _ticker,
    "trade": _trade,
    "book": _book,
    "candle": _candle,
}


@pytest.mark.parametrize("kind", sorted(EVENT_FACTORIES))
def test_event_defaults_to_perpetual(kind: str) -> None:
    """The USDS-M parsers build these without the field and must keep working."""
    assert EVENT_FACTORIES[kind]().market_type is MarketType.PERPETUAL


@pytest.mark.parametrize("kind", sorted(EVENT_FACTORIES))
def test_market_type_is_always_explicit_on_the_new_wire(kind: str) -> None:
    perpetual = to_wire(EVENT_FACTORIES[kind]())
    spot = to_wire(EVENT_FACTORIES[kind](market_type=MarketType.SPOT))
    assert perpetual["market_type"] == "perpetual"
    assert spot["market_type"] == "spot"


@pytest.mark.parametrize("kind", sorted(EVENT_FACTORIES))
def test_legacy_wire_without_market_type_reads_as_perpetual(kind: str) -> None:
    """What is in Redis and on the streams right now has no such field."""
    event = EVENT_FACTORIES[kind]()
    legacy = to_wire(event)
    del legacy["market_type"]

    restored = from_wire(type(event), legacy)

    assert restored.market_type is MarketType.PERPETUAL
    assert restored == event


@pytest.mark.parametrize("kind", sorted(EVENT_FACTORIES))
def test_wire_round_trip_keeps_spot(kind: str) -> None:
    event = EVENT_FACTORIES[kind](market_type=MarketType.SPOT)
    assert from_wire(type(event), to_wire(event)) == event
