"""Redis hot-state contracts — exact field names and TTLs, ARCHITECTURE.md §5.3."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_core.redis import keys
from hunter_market_worker import hot_state, hot_state_trades
from hunter_market_worker import wire as msgpack

from . import builders

pytestmark = pytest.mark.integration


async def test_write_ticker_fields_and_ttl(redis_client: Any) -> None:
    ticker = builders.ticker("BTCUSDT", "50000")
    await hot_state.write_ticker(redis_client, ticker, source="rest")

    key = keys.ticker(builders.EXCHANGE, "BTCUSDT")
    raw = await redis_client.hgetall(key)
    fields = {k.decode(): v.decode() for k, v in raw.items()}
    for name in ("last", "bid", "ask", "volume_24h", "quote_volume_24h", "ts"):
        assert name in fields
    assert fields["last"] == "50000"
    assert Decimal(fields["bid"]) == ticker.bid
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= hot_state.TICKER_TTL_S


async def test_write_ticker_is_a_single_redis_round_trip(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B2: ``_hash`` must do the whole compare-and-write in one round trip
    (a single ``EVALSHA``), not a ``WATCH``/``HGET``/``MULTI``/``EXEC``
    sequence — that was 10.02% of the worker's own CPU at 50 markets
    (t16b-profile.md)."""
    await hot_state.ensure_script_sha(redis_client)  # warm the per-client SHA cache first

    calls = {"direct": 0, "pipeline": 0}
    redis_cls: Any = redis_client.__class__
    original_execute_command = redis_cls.execute_command

    async def counting_execute_command(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["direct"] += 1
        return await original_execute_command(self, *args, **kwargs)

    monkeypatch.setattr(redis_cls, "execute_command", counting_execute_command)

    original_pipeline = redis_cls.pipeline

    def counting_pipeline(self: Any, *args: Any, **kwargs: Any) -> Any:
        pipe: Any = original_pipeline(self, *args, **kwargs)
        pipe_cls: Any = pipe.__class__
        original_execute = pipe_cls.execute

        async def counting_execute(pipe_self: Any, *a: Any, **kw: Any) -> Any:
            calls["pipeline"] += 1
            return await original_execute(pipe_self, *a, **kw)

        monkeypatch.setattr(pipe_cls, "execute", counting_execute)
        return pipe

    monkeypatch.setattr(redis_cls, "pipeline", counting_pipeline)

    pipeline_cls: Any = redis_client.pipeline().__class__
    original_immediate = pipeline_cls.immediate_execute_command

    async def counting_immediate(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["pipeline"] += 1
        return await original_immediate(self, *args, **kwargs)

    monkeypatch.setattr(pipeline_cls, "immediate_execute_command", counting_immediate)

    await hot_state.write_ticker(redis_client, builders.ticker("BTCUSDT", "50000"), source="rest")

    assert calls["direct"] + calls["pipeline"] == 1


async def test_hash_falls_back_to_eval_after_script_flush(redis_client: Any) -> None:
    """B2: a Redis restart flushes the script cache (T1.6 already proved
    restarts happen) — a ``NOSCRIPT`` on the cached SHA must fall back to
    ``EVAL``, never propagate and kill the worker."""
    await hot_state.write_ticker(redis_client, builders.ticker("BTCUSDT", "50000"), source="rest")
    await redis_client.script_flush()

    accepted = await hot_state.write_ticker(
        redis_client, builders.ticker("BTCUSDT", "50001", ts=builders.utcnow()), source="rest"
    )
    assert accepted
    assert await redis_client.hget(keys.ticker(builders.EXCHANGE, "BTCUSDT"), "last") == b"50001"


async def test_hash_orders_by_instant_not_string_bytes(redis_client: Any) -> None:
    """B2: the freshness compare must be numeric (epoch microseconds), not a
    lexicographic compare of the ISO string — a same-second write with a
    lexicographically-smaller-but-chronologically-later microsecond must
    still win."""
    from datetime import timedelta

    key = keys.ticker(builders.EXCHANGE, "ETHUSDT")
    t0 = builders.utcnow().replace(microsecond=500_000)
    await hot_state.write_ticker(
        redis_client, builders.ticker("ETHUSDT", "100", ts=t0), source="rest"
    )
    t1 = t0 + timedelta(microseconds=1)  # chronologically later
    accepted = await hot_state.write_ticker(
        redis_client, builders.ticker("ETHUSDT", "101", ts=t1), source="rest"
    )
    assert accepted
    assert await redis_client.hget(key, "last") == b"101"


async def test_write_ticker_rest_omits_bid_ask(redis_client: Any) -> None:
    """The REST 24h-ticker never carries bid/ask (KB-0044,
    ``binance/normalize.py::parse_ticker_24h``) -- they must never appear."""
    ticker = builders.ticker_rest("ETHUSDT", "3000")
    await hot_state.write_ticker(redis_client, ticker, source="rest")
    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "ETHUSDT"))
    fields = {k.decode() for k in raw}
    assert "bid" not in fields
    assert "ask" not in fields
    assert "volume_24h" in fields


async def test_write_ticker_ws_omits_volume_fields(redis_client: Any) -> None:
    """The WS ``bookTicker`` never carries 24h volume (KB-0044,
    ``binance/normalize.py::parse_book_ticker``) -- it must never appear."""
    ticker = builders.ticker_ws("ETHUSDT", "3000")
    await hot_state.write_ticker(redis_client, ticker, source="ws")
    raw = await redis_client.hgetall(keys.ticker(builders.EXCHANGE, "ETHUSDT"))
    fields = {k.decode() for k in raw}
    assert "volume_24h" not in fields
    assert "quote_volume_24h" not in fields
    assert "bid" in fields


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
    memory = hot_state.TradeMemory()
    for i in range(3):
        await hot_state.push_trade(
            redis_client, builders.trade("BTCUSDT", "100", "1", trade_id=str(i)), memory
        )

    raw = await redis_client.lrange(key, 0, -1)
    decoded = [msgpack.unpackb(r) for r in raw]
    assert [d["trade_id"] for d in decoded] == ["2", "1", "0"]
    assert decoded[0]["side"] == "buy"


async def test_push_trade_dedupes_in_memory_without_lrange_per_trade(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4/H7: dedupe/ordering must be a bounded in-memory check — the only
    ``LRANGE`` allowed is the one-time cold-start seed on first touch of a
    symbol, never one per trade."""
    calls: list[tuple[int, int]] = []
    original_lrange = redis_client.lrange

    async def spy_lrange(key: str, start: int, end: int) -> Any:
        calls.append((start, end))
        return await original_lrange(key, start, end)

    monkeypatch.setattr(redis_client, "lrange", spy_lrange)

    memory = hot_state.TradeMemory()
    for i in range(5):
        await hot_state.push_trade(
            redis_client, builders.trade("BTCUSDT", "100", "1", trade_id=str(i)), memory
        )
    assert len(calls) == 1, "only the cold-start seed may call LRANGE"
    start, end = calls[0]
    assert start == 0
    assert 0 <= end < hot_state.TRADES_MAXLEN

    # A duplicate inside the window is still rejected, purely in memory.
    assert not await hot_state.push_trade(
        redis_client, builders.trade("BTCUSDT", "100", "1", trade_id="1"), memory
    )
    assert len(calls) == 1, "the duplicate check must not trigger another LRANGE"


async def test_push_trade_rejects_trade_older_than_newest_known(redis_client: Any) -> None:
    memory = hot_state.TradeMemory()
    from datetime import timedelta

    t0 = builders.utcnow()
    assert await hot_state.push_trade(
        redis_client, builders.trade("BTCUSDT", "100", "1", trade_id="1", ts=t0), memory
    )
    older = builders.trade("BTCUSDT", "99", "1", trade_id="2", ts=t0 - timedelta(seconds=1))
    assert not await hot_state.push_trade(redis_client, older, memory)


async def test_trade_memory_is_bounded_and_forgotten_on_symbol_removal(
    redis_client: Any,
) -> None:
    """B4: bounded per-symbol memory, dropped when a symbol leaves the
    universe — otherwise a 15-minute universe refresh grows it forever (same
    bug class as F11 in ws.py)."""
    memory = hot_state.TradeMemory()
    for i in range(hot_state.TRADE_DEDUPE_WINDOW + 20):
        await hot_state.push_trade(
            redis_client, builders.trade("BTCUSDT", "100", "1", trade_id=str(i)), memory
        )
    key = (builders.EXCHANGE, "BTCUSDT")
    assert len(memory._ids[key]) <= hot_state.TRADE_DEDUPE_WINDOW  # pyright: ignore[reportPrivateUsage]

    memory.forget(builders.EXCHANGE, "BTCUSDT")
    assert key not in memory._ids  # pyright: ignore[reportPrivateUsage]
    assert key not in memory._newest_ts  # pyright: ignore[reportPrivateUsage]


async def test_trade_memory_cold_start_reseeds_from_redis_no_duplicate(
    redis_client: Any,
) -> None:
    """B4: a worker restart means blank in-memory state; the first touch of a
    symbol must seed from Redis so a replayed trade already in the ring
    buffer is still rejected, never duplicated."""
    warm = hot_state.TradeMemory()
    await hot_state.push_trade(
        redis_client, builders.trade("BTCUSDT", "100", "1", trade_id="1"), warm
    )
    await hot_state.push_trade(
        redis_client, builders.trade("BTCUSDT", "101", "1", trade_id="2"), warm
    )

    cold = hot_state.TradeMemory()  # simulates a fresh process, e.g. after restart
    replayed = builders.trade("BTCUSDT", "101", "1", trade_id="2")
    assert not await hot_state.push_trade(redis_client, replayed, cold)

    key = keys.trades(builders.EXCHANGE, "BTCUSDT")
    assert await redis_client.llen(key) == 2  # not duplicated


async def test_push_trade_trims_to_maxlen(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hot_state_trades, "TRADES_MAXLEN", 5)
    key = keys.trades(builders.EXCHANGE, "ETHUSDT")
    memory = hot_state.TradeMemory()
    for i in range(10):
        await hot_state.push_trade(
            redis_client, builders.trade("ETHUSDT", "100", "1", trade_id=str(i)), memory
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


async def test_write_ticker_rest_drops_stale_optional_field_under_fresh_ts(
    redis_client: Any,
) -> None:
    """H4: a REST-owned field the exchange stops sending must disappear, not
    sit stale next to a fresh ``ts`` (fake-by-omission) -- scoped to the
    fields the REST producer actually owns (KB-0044)."""
    from datetime import timedelta

    key = keys.ticker(builders.EXCHANGE, "BTCUSDT")
    with_volume = builders.ticker_rest("BTCUSDT", "100")
    await hot_state.write_ticker(redis_client, with_volume, source="rest")
    assert await redis_client.hget(key, "volume_24h") == b"1000"

    without_volume = builders.ticker_rest(
        "BTCUSDT",
        "101",
        ts=with_volume.ts + timedelta(seconds=1),
        volume_24h=None,
    )
    await hot_state.write_ticker(redis_client, without_volume, source="rest")
    fields = {k.decode() for k in await redis_client.hgetall(key)}
    assert "volume_24h" not in fields
    assert await redis_client.hget(key, "last") == b"101"


async def test_write_ticker_ws_drops_stale_optional_field_under_fresh_ts(
    redis_client: Any,
) -> None:
    """H4, WS side: a WS-owned field (``bid_qty``) the stream stops sending
    must disappear too, scoped to the fields the WS producer owns."""
    from datetime import timedelta

    key = keys.ticker(builders.EXCHANGE, "ETHUSDT")
    with_qty = builders.ticker_ws("ETHUSDT", "3000")
    await hot_state.write_ticker(redis_client, with_qty, source="ws")
    assert await redis_client.hget(key, "bid_qty") == b"5"

    without_qty = builders.ticker_ws(
        "ETHUSDT",
        "3001",
        ts=with_qty.ts + timedelta(seconds=1),
        bid_qty=None,
    )
    await hot_state.write_ticker(redis_client, without_qty, source="ws")
    fields = {k.decode() for k in await redis_client.hgetall(key)}
    assert "bid_qty" not in fields
    assert await redis_client.hget(key, "last") == b"3001"


async def test_shared_ownership_reproduces_the_kb_0044_bug(redis_client: Any) -> None:
    """Documents the exact failure mode KB-0044 measured in production
    (``market_snapshots.volume_24h``: 6 populated rows out of 55,709): if the
    REST-ticker writer and the WS-ticker writer ever go back to sharing one
    "owns every ticker field" set, an accepted write from either one wipes
    the other's fields via the owned-field ``HDEL`` in ``hot_state._hash``.
    This pins that failure down at the primitive level so nobody can
    reintroduce a single shared ``owned`` tuple for the ticker hash without
    this test failing."""
    key = keys.ticker(builders.EXCHANGE, "BTCUSDT")
    shared_owned = hot_state.TICKER_REST_FIELDS + hot_state.TICKER_WS_FIELDS

    rest_only_fields = {"last": "100", "volume_24h": "1000", "ts": builders.utcnow().isoformat()}
    await hot_state._hash(  # pyright: ignore[reportPrivateUsage]
        redis_client, key, rest_only_fields, "ts", builders.utcnow(), 30, owned=shared_owned
    )
    assert await redis_client.hget(key, "volume_24h") == b"1000"

    from datetime import timedelta

    ws_only_fields = {
        "last": "100.5",
        "bid": "100.4",
        "ask": "100.6",
        "ts": (builders.utcnow() + timedelta(milliseconds=250)).isoformat(),
    }
    await hot_state._hash(  # pyright: ignore[reportPrivateUsage]
        redis_client,
        key,
        ws_only_fields,
        "ts",
        builders.utcnow() + timedelta(milliseconds=250),
        30,
        owned=shared_owned,
    )
    # This is the bug: a shared owned-set treats "volume_24h" as missing from
    # the WS write and HDELs it, even though the WS producer never carries it.
    assert await redis_client.hget(key, "volume_24h") is None
    assert await redis_client.hget(key, "bid") == b"100.4"


async def test_rest_ticker_and_ws_ticker_coexist_in_same_hash(redis_client: Any) -> None:
    """KB-0044: the REST 24h-ticker refresh (``universe.py``, no bid/ask) and
    the WS ``bookTicker`` (``coalesce.py``, no volume) write the *same* ticker
    hash. Before the fix, both declared ``owned=TICKER_FIELDS`` (every ticker
    field), so each accepted write ``HDEL``'d the other producer's fields in
    the same MULTI -- volume_24h and bid/ask could (almost) never coexist,
    which is why ``market_snapshots.volume_24h`` had 6 populated rows out of
    55,709 (KB-0044). Field ownership must be scoped per producer."""
    from datetime import timedelta

    key = keys.ticker(builders.EXCHANGE, "BTCUSDT")
    rest = builders.ticker_rest("BTCUSDT", "100")
    await hot_state.write_ticker(redis_client, rest, source="rest")

    ws = builders.ticker_ws("BTCUSDT", "100.5", ts=rest.ts + timedelta(milliseconds=250))
    await hot_state.write_ticker(redis_client, ws, source="ws")

    fields = {k.decode(): v.decode() for k, v in (await redis_client.hgetall(key)).items()}
    # The WS write must not have deleted the REST-owned fields ...
    assert fields["volume_24h"] == "1000"
    assert fields["quote_volume_24h"] == "1000000"
    assert fields["high_24h"] == str(rest.high_24h)
    assert fields["low_24h"] == str(rest.low_24h)
    # ... and both must be present at once, not one clobbering the other.
    assert fields["bid"] == str(ws.bid)
    assert fields["ask"] == str(ws.ask)
    assert fields["last"] == "100.5"


async def test_rest_ticker_after_ws_ticker_does_not_delete_bid_ask(redis_client: Any) -> None:
    """Same bug, opposite order: a REST refresh landing after a WS
    ``bookTicker`` must not erase bid/ask."""
    from datetime import timedelta

    key = keys.ticker(builders.EXCHANGE, "ETHUSDT")
    ws = builders.ticker_ws("ETHUSDT", "3000")
    await hot_state.write_ticker(redis_client, ws, source="ws")

    rest = builders.ticker_rest("ETHUSDT", "3001", ts=ws.ts + timedelta(milliseconds=250))
    await hot_state.write_ticker(redis_client, rest, source="rest")

    fields = {k.decode(): v.decode() for k, v in (await redis_client.hgetall(key)).items()}
    assert fields["bid"] == str(ws.bid)
    assert fields["ask"] == str(ws.ask)
    assert fields["volume_24h"] == "1000"


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
