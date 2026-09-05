"""Redis hot-state contracts — exact field names and TTLs, ARCHITECTURE.md §5.3."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_core.redis import keys
from hunter_market_worker import hot_state
from hunter_market_worker import wire as msgpack

from . import builders

pytestmark = pytest.mark.integration


async def test_write_ticker_fields_and_ttl(redis_client: Any) -> None:
    ticker = builders.ticker("BTCUSDT", "50000")
    await hot_state.write_ticker(redis_client, ticker)

    key = keys.ticker(builders.EXCHANGE, "BTCUSDT")
    raw = await redis_client.hgetall(key)
    fields = {k.decode(): v.decode() for k, v in raw.items()}
    for name in ("last", "bid", "ask", "volume_24h", "quote_volume_24h", "ts"):
        assert name in fields
    assert fields["last"] == "50000"
    assert Decimal(fields["bid"]) == ticker.bid
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= hot_state.TICKER_TTL_S


async def test_write_ticker_omits_unknown_optional_fields(redis_client: Any) -> None:
    ticker = builders.ticker("ETHUSDT", "3000", bid=None, ask=None, high_24h=None, low_24h=None)
    await hot_state.write_ticker(redis_client, ticker)
    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "ETHUSDT"))
    fields = {k.decode() for k in raw}
    assert "bid" not in fields
    assert "ask" not in fields


async def test_write_book_msgpack_shape_and_ttl(redis_client: Any) -> None:
    book = builders.order_book("BTCUSDT", "50000", "50001")
    await hot_state.write_book(redis_client, book, depth=25)

    key = keys.book(builders.EXCHANGE, "BTCUSDT")
    raw = await redis_client.get(key)
    decoded = msgpack.unpackb(raw)
    assert decoded["bids"] == [["50000", "5"]]
    assert decoded["asks"] == [["50001", "2"]]
    assert "ts" in decoded
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= hot_state.BOOK_TTL_S


async def test_push_trade_ring_buffer_newest_at_head(redis_client: Any) -> None:
    key = keys.trades(builders.EXCHANGE, "BTCUSDT")
    for i in range(3):
        await hot_state.push_trade(
            redis_client, builders.trade("BTCUSDT", "100", "1", trade_id=str(i))
        )

    raw = await redis_client.lrange(key, 0, -1)
    decoded = [msgpack.unpackb(r) for r in raw]
    assert [d["trade_id"] for d in decoded] == ["2", "1", "0"]
    assert decoded[0]["side"] == "buy"


async def test_push_trade_reads_only_a_bounded_window(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H7: every trade must not LRANGE the entire (up to 2000-item) list —
    only a bounded window is needed to dedupe/order against a WS replay."""
    calls: list[tuple[int, int]] = []
    original_lrange = redis_client.lrange

    async def spy_lrange(key: str, start: int, end: int) -> Any:
        calls.append((start, end))
        return await original_lrange(key, start, end)

    monkeypatch.setattr(redis_client, "lrange", spy_lrange)

    for i in range(3):
        await hot_state.push_trade(
            redis_client, builders.trade("BTCUSDT", "100", "1", trade_id=str(i))
        )
    assert calls, "push_trade must call lrange"
    for start, end in calls:
        assert start == 0
        assert 0 <= end < hot_state.TRADES_MAXLEN

    # A duplicate inside the bounded window is still rejected.
    assert not await hot_state.push_trade(
        redis_client, builders.trade("BTCUSDT", "100", "1", trade_id="1")
    )


async def test_push_trade_trims_to_maxlen(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hot_state, "TRADES_MAXLEN", 5)
    key = keys.trades(builders.EXCHANGE, "ETHUSDT")
    for i in range(10):
        await hot_state.push_trade(
            redis_client, builders.trade("ETHUSDT", "100", "1", trade_id=str(i))
        )
    assert await redis_client.llen(key) == 5
    raw = await redis_client.lrange(key, 0, -1)
    newest = msgpack.unpackb(raw[0])
    assert newest["trade_id"] == "9"


async def test_push_candle_wire_format(redis_client: Any) -> None:
    candle = builders.candle("BTCUSDT")
    await hot_state.push_candle(redis_client, candle)
    raw = await redis_client.lrange(keys.candles_1m(builders.EXCHANGE, "BTCUSDT"), 0, -1)
    decoded = msgpack.unpackb(raw[0])
    assert decoded["open"] == "100"
    assert decoded["is_final"] is True


async def test_write_ticker_drops_stale_optional_field_under_fresh_ts(
    redis_client: Any,
) -> None:
    """H4: a field the exchange stops sending must disappear, not sit stale
    next to a fresh ``ts`` (fake-by-omission)."""
    from datetime import timedelta

    key = keys.ticker(builders.EXCHANGE, "BTCUSDT")
    with_volume = builders.ticker("BTCUSDT", "100")
    await hot_state.write_ticker(redis_client, with_volume)
    assert await redis_client.hget(key, "volume_24h") == b"1000"

    without_volume = builders.ticker(
        "BTCUSDT",
        "101",
        ts=with_volume.ts + timedelta(seconds=1),
        volume_24h=None,
    )
    await hot_state.write_ticker(redis_client, without_volume)
    fields = {k.decode() for k in await redis_client.hgetall(key)}
    assert "volume_24h" not in fields
    assert await redis_client.hget(key, "last") == b"101"


async def test_open_interest_write_does_not_delete_mark_price(redis_client: Any) -> None:
    """H4: a writer must never delete a field it does not own — the deriv
    hash is shared by funding/mark/OI writers."""
    key = keys.derivatives(builders.EXCHANGE, "BTCUSDT")
    await hot_state.write_funding(redis_client, builders.funding("BTCUSDT"))
    assert await redis_client.hget(key, "mark_price") == b"100"

    from datetime import timedelta

    oi = builders.open_interest(
        "BTCUSDT", ts=builders.funding("BTCUSDT").ts + timedelta(seconds=20)
    )
    await hot_state.write_open_interest(redis_client, oi)
    assert await redis_client.hget(key, "mark_price") == b"100"


async def test_write_funding_then_open_interest_share_the_hash(redis_client: Any) -> None:
    key = keys.derivatives(builders.EXCHANGE, "BTCUSDT")
    await hot_state.write_funding(redis_client, builders.funding("BTCUSDT", "0.0001"))
    await hot_state.write_open_interest(redis_client, builders.open_interest("BTCUSDT", "1234"))

    raw = await redis_client.hgetall(key)
    fields = {k.decode(): v.decode() for k, v in raw.items()}
    assert fields["funding_rate"] == "0.0001"
    assert fields["open_interest"] == "1234"
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= hot_state.DERIV_TTL_S
