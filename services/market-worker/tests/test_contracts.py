"""Regression coverage for the binding T1.3 resume contracts."""

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.events.envelope import EventEnvelope
from hunter_core.redis import keys
from hunter_market_worker import hot_state
from hunter_market_worker import wire as msgpack
from hunter_market_worker.ingest import TickCoalescer, flush_ticks

from . import builders

pytestmark = pytest.mark.integration


async def test_components_keep_independent_source_times(redis_client: Any) -> None:
    funding = builders.funding("BTCUSDT")
    await hot_state.write_funding(redis_client, funding)
    key = keys.derivatives("fake", "BTCUSDT")
    before = await redis_client.hgetall(key)
    assert before[b"mark_ts"] == funding.ts.isoformat().encode()
    oi = builders.open_interest("BTCUSDT", ts=funding.ts + timedelta(seconds=20))
    await hot_state.write_open_interest(redis_client, oi)
    after = await redis_client.hgetall(key)
    assert after[b"mark_ts"] == before[b"mark_ts"]
    assert after[b"funding_ts"] == before[b"funding_ts"]
    assert after[b"oi_ts"] == oi.ts.isoformat().encode()
    assert after[b"funding_kind"] == b"estimated"
    assert 590 <= await redis_client.ttl(key) <= 600


async def test_duplicate_and_late_ticker_do_not_refresh(redis_client: Any) -> None:
    event = builders.ticker("BTCUSDT", "100")
    await hot_state.write_ticker(redis_client, event)
    key = keys.ticker("fake", "BTCUSDT")
    await redis_client.expire(key, 7)
    assert await hot_state.write_ticker(redis_client, event) is False
    late = event.model_copy(update={"ts": event.ts - timedelta(seconds=1), "last": Decimal("90")})
    assert await hot_state.write_ticker(redis_client, late) is False
    assert await redis_client.hget(key, "last") == b"100"
    assert await redis_client.ttl(key) <= 7


async def test_book_snapshot_and_trade_head(redis_client: Any) -> None:
    book = builders.order_book("BTCUSDT")
    await hot_state.write_book(redis_client, book, depth=20)
    value = msgpack.unpackb(await redis_client.get(keys.book("fake", "BTCUSDT")))
    assert value["kind"] == "snapshot"
    assert value["depth"] == 20
    memory = hot_state.TradeMemory()
    for i in range(3):
        await hot_state.push_trade(
            redis_client, builders.trade("BTCUSDT", "100", "1", trade_id=str(i)), memory
        )
    rows = await redis_client.lrange(keys.trades("fake", "BTCUSDT"), 0, -1)
    assert [msgpack.unpackb(r)["trade_id"] for r in rows] == ["2", "1", "0"]


async def test_coalescer_uses_source_time_and_no_idle_publication(redis_client: Any) -> None:
    coalescer = TickCoalescer()
    event = builders.trade("BTCUSDT", "100", "1", ts=builders.utcnow() - timedelta(seconds=10))
    coalescer.on_trade(event)
    await flush_ticks(coalescer, redis_client, "test")
    rows = await redis_client.xrange("market.ticks")
    assert EventEnvelope.from_bytes(rows[0][1][b"data"]).payload["ts"] == event.ts.isoformat()
    await flush_ticks(coalescer, redis_client, "test")
    assert await redis_client.xlen("market.ticks") == 1


async def test_candle_partials_late_final_and_head_preservation(redis_client: Any) -> None:
    first = builders.candle("BTCUSDT", is_final=False)
    ts = first.open_time + timedelta(seconds=10)
    assert await hot_state.push_candle(redis_client, first, event_ts=ts)
    grown = first.model_copy(update={"volume": Decimal("20")})
    assert await hot_state.push_candle(redis_client, grown, event_ts=ts + timedelta(seconds=5))
    key = keys.candles_1m("fake", "BTCUSDT")
    head_ts_before_late_write = msgpack.unpackb((await redis_client.lrange(key, 0, -1))[0])["ts"]
    assert not await hot_state.push_candle(redis_client, first, event_ts=ts)
    head_ts_after_late_write = msgpack.unpackb((await redis_client.lrange(key, 0, -1))[0])["ts"]
    assert head_ts_after_late_write == head_ts_before_late_write  # L2: late write must not refresh
    following = builders.candle("BTCUSDT", first.open_time + timedelta(minutes=1), is_final=False)
    assert await hot_state.push_candle(redis_client, following, event_ts=ts + timedelta(minutes=1))
    final = grown.model_copy(update={"is_final": True})
    assert await hot_state.push_candle(redis_client, final, event_ts=ts + timedelta(seconds=50))
    assert not await hot_state.push_candle(redis_client, grown, event_ts=ts + timedelta(minutes=2))
    rows = await redis_client.lrange(keys.candles_1m("fake", "BTCUSDT"), 0, -1)
    head, previous = [msgpack.unpackb(row) for row in rows]
    assert head["open_time"] == following.model_dump(mode="json")["open_time"]
    assert not head["is_final"]
    assert previous["is_final"] and previous["volume"] == "20"


async def test_candle_without_exchange_timestamp_cannot_order_partials(redis_client: Any) -> None:
    assert not await hot_state.push_candle(redis_client, builders.candle("BTCUSDT", is_final=False))


async def test_final_candle_with_same_event_ts_as_last_partial_replaces_it(
    redis_client: Any,
) -> None:
    """H9: a final candle carrying the same ``event_ts`` as the last partial
    of that ``open_time`` must still replace it — finality wins unconditionally."""
    partial = builders.candle("BTCUSDT", is_final=False)
    ts = partial.open_time + timedelta(seconds=10)
    assert await hot_state.push_candle(redis_client, partial, event_ts=ts)
    final = partial.model_copy(update={"is_final": True})
    assert await hot_state.push_candle(redis_client, final, event_ts=ts)
    rows = await redis_client.lrange(keys.candles_1m("fake", "BTCUSDT"), 0, -1)
    stored = msgpack.unpackb(rows[0])
    assert stored["is_final"] is True


async def test_normal_new_minute_final_does_not_issue_delete(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H8: the common streaming case (a new, later ``open_time``) must use the
    fast LPUSH/LTRIM path, never DELETE the whole list — a concurrent reader
    (the API) must never observe an empty candle list."""
    import redis.asyncio.client as redis_client_module

    commands: list[str] = []
    original_execute_command = cast(Any, redis_client_module.Pipeline).execute_command

    def spying_execute_command(self: Any, *args: Any, **kwargs: Any) -> Any:
        commands.append(args[0])
        return original_execute_command(self, *args, **kwargs)

    monkeypatch.setattr(redis_client_module.Pipeline, "execute_command", spying_execute_command)

    first = builders.candle("BTCUSDT")
    assert await hot_state.push_candle(redis_client, first)
    second = builders.candle("BTCUSDT", first.open_time + timedelta(minutes=1))
    assert await hot_state.push_candle(redis_client, second)

    assert "DEL" not in commands


async def test_new_trade_during_publication_is_kept_for_next_flush(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hunter_market_worker import coalesce

    coalescer = TickCoalescer()
    coalescer.on_trade(builders.trade("BTCUSDT", "100", "1"))
    original = coalesce.publish

    async def racing_publish(*args: Any) -> Any:
        coalescer.on_trade(builders.trade("BTCUSDT", "101", "2", trade_id="2"))
        return await original(*args)

    monkeypatch.setattr(coalesce, "publish", racing_publish)
    await flush_ticks(coalescer, redis_client, "test")
    [(_, accum)] = coalescer.dirty_items()
    assert accum.trades_count == 1 and accum.volume_delta == Decimal("2")
