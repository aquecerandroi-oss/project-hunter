"""T3.0b — a spot event and a perpetual event of the same symbol never meet.

Before this, ``BTCUSDT`` spot and ``BTCUSDT`` perpetual wrote the same
``mkt:fake:BTCUSDT:*`` keys and the last writer won, silently. Every write path
of the collector is checked here in both listings at once, and the perpetual's
key is asserted by its literal name — it is the one four shards are writing to
in production while this ships.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_core.redis import keys
from hunter_market_worker import hot_state
from hunter_market_worker import wire as msgpack
from hunter_market_worker.ingest import AcceptedEvents, TickCoalescer, flush_ticks

from . import builders

pytestmark = pytest.mark.integration

SPOT = MarketType.SPOT
PERP_TICKER_KEY = "mkt:fake:BTCUSDT:ticker"
SPOT_TICKER_KEY = "mkt:fake:spot:BTCUSDT:ticker"


async def test_ticker_writes_land_on_two_keys(redis_client: Any) -> None:
    perpetual = builders.ticker_rest("BTCUSDT", "100")
    spot = builders.ticker_rest("BTCUSDT", "200", market_type=SPOT)

    assert await hot_state.write_ticker(redis_client, perpetual, source="rest")
    assert await hot_state.write_ticker(redis_client, spot, source="rest")

    assert await redis_client.hget(PERP_TICKER_KEY, "last") == b"100"
    assert await redis_client.hget(SPOT_TICKER_KEY, "last") == b"200"
    assert keys.ticker("fake", "BTCUSDT") == PERP_TICKER_KEY


async def test_a_spot_write_does_not_gate_the_perpetuals_freshness(redis_client: Any) -> None:
    """The freshness compare is per key; a newer spot tick must not make the
    perpetual's own next tick look stale."""
    later = builders.utcnow() + timedelta(seconds=30)
    assert await hot_state.write_ticker(
        redis_client,
        builders.ticker_rest("BTCUSDT", "999", ts=later, market_type=SPOT),
        source="rest",
    )
    assert await hot_state.write_ticker(
        redis_client, builders.ticker_rest("BTCUSDT", "100"), source="rest"
    )
    assert await redis_client.hget(PERP_TICKER_KEY, "last") == b"100"


async def test_book_trades_and_candles_are_kept_apart(redis_client: Any) -> None:
    memory = hot_state.TradeMemory()
    for market_type, price in ((MarketType.PERPETUAL, "100"), (SPOT, "200")):
        update = {"market_type": market_type}
        await hot_state.write_book(
            redis_client, builders.order_book("BTCUSDT", price, "300").model_copy(update=update)
        )
        # Same ``trade_id`` on both listings: dedupe is per market, not per symbol.
        await hot_state.push_trade(
            redis_client,
            builders.trade("BTCUSDT", price, "1", trade_id="7", market_type=market_type),
            memory,
        )
        await hot_state.push_candle(
            redis_client, builders.candle("BTCUSDT").model_copy(update=update)
        )

    perp_book = msgpack.unpackb(await redis_client.get("mkt:fake:BTCUSDT:book"))
    spot_book = msgpack.unpackb(await redis_client.get("mkt:fake:spot:BTCUSDT:book"))
    assert perp_book["bids"][0][0] == "100"
    assert spot_book["bids"][0][0] == "200"

    perp_trades = await redis_client.lrange("mkt:fake:BTCUSDT:trades", 0, -1)
    spot_trades = await redis_client.lrange("mkt:fake:spot:BTCUSDT:trades", 0, -1)
    assert [msgpack.unpackb(r)["price"] for r in perp_trades] == ["100"]
    assert [msgpack.unpackb(r)["price"] for r in spot_trades] == ["200"]

    perp_candles = await redis_client.lrange("mkt:fake:BTCUSDT:candles:1m", 0, -1)
    spot_candles = await redis_client.lrange("mkt:fake:spot:BTCUSDT:candles:1m", 0, -1)
    assert msgpack.unpackb(perp_candles[0])["market_type"] == "perpetual"
    assert msgpack.unpackb(spot_candles[0])["market_type"] == "spot"


async def test_the_coalescer_flushes_one_hot_state_write_per_market(redis_client: Any) -> None:
    coalescer = TickCoalescer()
    coalescer.on_ticker(builders.ticker_ws("BTCUSDT", "100"))
    coalescer.on_ticker(builders.ticker_ws("BTCUSDT", "200", market_type=SPOT))

    assert len(coalescer.dirty_items()) == 2
    await flush_ticks(coalescer, redis_client, "test")

    assert await redis_client.hget(PERP_TICKER_KEY, "bid") == b"99.99"
    assert await redis_client.hget(SPOT_TICKER_KEY, "bid") == b"199.99"


def test_the_acceptance_gate_is_per_market_not_per_symbol() -> None:
    """Two listings quoting the same symbol at the same instant are two
    observations; one must not be dropped as a duplicate of the other."""
    accepted = AcceptedEvents()
    ts = builders.utcnow()

    assert accepted.accept(builders.ticker_ws("BTCUSDT", "100", ts=ts))
    assert accepted.accept(builders.ticker_ws("BTCUSDT", "200", ts=ts, market_type=SPOT))
    assert not accepted.accept(builders.ticker_ws("BTCUSDT", "101", ts=ts))
