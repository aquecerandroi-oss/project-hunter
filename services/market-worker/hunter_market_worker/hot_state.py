"""Redis hot state. Source times gate writes; every list has newest at index 0."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from redis.exceptions import WatchError

from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedFunding,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
    to_wire,
)
from hunter_core.redis import keys
from hunter_market_worker import wire as msgpack

TICKER_TTL_S = 30
BOOK_TTL_S = 10
DERIV_TTL_S = 600
TRADES_MAXLEN = 2000
CANDLES_MAXLEN = 1500
# A WS reconnect only ever replays a handful of recent trades, so a 50-item
# window (newest-first) covers dedupe/ordering without reading the whole
# 2000-item ring buffer on every single trade (H7).
TRADE_DEDUPE_WINDOW = 50
# Fast-path window for push_candle: almost every write either updates the
# current (head) minute or opens a new one, both covered by the 16 newest
# entries. Only a write older than this window falls back to the rare full
# read-modify-rewrite (H8).
CANDLE_FAST_WINDOW = 16

# Fields each writer owns in a shared hash. On an accepted write, owned
# fields whose value is None are HDEL'd in the same MULTI as the HSET, so an
# exchange that stops sending an optional field does not leave it stale next
# to a fresh timestamp (H4). A writer must never touch a field it does not
# own — the ticker and deriv hashes are shared by several writers.
TICKER_FIELDS = (
    "last",
    "bid",
    "ask",
    "bid_qty",
    "ask_qty",
    "volume_24h",
    "quote_volume_24h",
    "high_24h",
    "low_24h",
    "change_24h_pct",
    "ts",
)
FUNDING_FIELDS = ("funding_rate", "funding_kind", "next_funding_time", "funding_ts")
MARK_FIELDS = ("mark_price", "index_price", "mark_ts")
OI_FIELDS = ("open_interest", "open_interest_value", "oi_ts")


def _mapping(**fields: Any) -> dict[str, str]:
    return {name: str(value) for name, value in fields.items() if value is not None}


def _newer(ts: datetime, previous: bytes | str | None) -> bool:
    if previous is None:
        return True
    value = previous.decode() if isinstance(previous, bytes) else previous
    return ts > datetime.fromisoformat(value)


async def _hash(
    redis: Any,
    key: str,
    fields: dict[str, str],
    ts_field: str,
    ts: datetime,
    ttl: int,
    *,
    owned: tuple[str, ...] = (),
) -> bool:
    stale = [name for name in owned if name not in fields]
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                if not _newer(ts, await pipe.hget(key, ts_field)):
                    return False
                pipe.multi()
                if fields:
                    pipe.hset(key, mapping=fields)
                if stale:
                    pipe.hdel(key, *stale)
                pipe.expire(key, ttl)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def write_ticker(redis: Any, ticker: NormalizedTicker) -> bool:
    fields = to_wire(ticker)
    for field in ("kind", "exchange", "symbol", "received_at"):
        fields.pop(field, None)
    fields["ts"] = ticker.ts.isoformat()
    return await _hash(
        redis,
        keys.ticker(ticker.exchange, ticker.symbol),
        _mapping(**fields),
        "ts",
        ticker.ts,
        TICKER_TTL_S,
        owned=TICKER_FIELDS,
    )


async def write_book(redis: Any, book: NormalizedOrderBook, depth: int = 20) -> bool:
    if not book.is_snapshot:
        raise ValueError("market worker requires book snapshots")
    depth = 20
    key = keys.book(book.exchange, book.symbol)
    payload = {
        "ts": book.ts.isoformat(),
        "depth": depth,
        "kind": "snapshot",
        "bids": [[str(level.price), str(level.qty)] for level in book.bids[:depth]],
        "asks": [[str(level.price), str(level.qty)] for level in book.asks[:depth]],
    }
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                previous = await pipe.get(key)
                if previous and not _newer(book.ts, msgpack.unpackb(previous)["ts"]):
                    return False
                pipe.multi()
                pipe.set(key, msgpack.packb(payload, use_bin_type=True), ex=BOOK_TTL_S)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def push_trade(redis: Any, trade: NormalizedTrade) -> bool:
    key = keys.trades(trade.exchange, trade.symbol)
    rows = await redis.lrange(key, 0, TRADE_DEDUPE_WINDOW - 1)
    decoded: list[dict[str, Any]] = [msgpack.unpackb(row) for row in rows]
    if any(row["trade_id"] == trade.trade_id for row in decoded):
        return False
    if decoded and trade.ts < datetime.fromisoformat(decoded[0]["ts"]):
        return False
    payload = {
        "ts": trade.ts.isoformat(),
        "price": str(trade.price),
        "qty": str(trade.qty),
        "side": trade.side.value,
        "trade_id": trade.trade_id,
    }
    async with redis.pipeline(transaction=True) as pipe:
        pipe.lpush(key, msgpack.packb(payload, use_bin_type=True))
        pipe.ltrim(key, 0, TRADES_MAXLEN - 1)
        await pipe.execute()
    return True


def _candle_may_replace(
    value: dict[str, Any], previous: dict[str, Any], event_ts: datetime | None
) -> bool:
    """Precedence for two entries sharing the same ``open_time`` (H9):
    a final entry is never replaced; a final incoming candle always replaces
    a non-final one regardless of ``event_ts``; otherwise the newer
    ``event_ts`` wins (an older/duplicate partial is rejected)."""
    if previous["is_final"]:
        return False
    if value["is_final"]:
        return True
    return event_ts is None or not previous.get("ts") or _newer(event_ts, previous["ts"])


async def _push_candle_full_rewrite(
    redis: Any, key: str, value: dict[str, Any], event_ts: datetime | None
) -> bool:
    """Rare fallback for a write older than :data:`CANDLE_FAST_WINDOW` — full
    read-modify-rewrite, same precedence rules as the fast paths (H8)."""
    rows = await redis.lrange(key, 0, -1)
    candles: list[dict[str, Any]] = [msgpack.unpackb(row) for row in rows]
    for i, previous in enumerate(candles):
        if previous["open_time"] != value["open_time"]:
            continue
        if not _candle_may_replace(value, previous, event_ts):
            return False
        candles[i] = value
        break
    else:
        candles.append(value)
    candles.sort(key=lambda c: c["open_time"], reverse=True)
    candles = candles[:CANDLES_MAXLEN]
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        pipe.rpush(key, *[msgpack.packb(c, use_bin_type=True) for c in candles])
        pipe.ltrim(key, 0, CANDLES_MAXLEN - 1)
        await pipe.execute()
    return True


async def push_candle(
    redis: Any, candle: NormalizedCandle, *, event_ts: datetime | None = None
) -> bool:
    """Single WS writer. Missing exchange ts cannot safely order partials.

    T1.1 currently lacks candle.ts. Final candles can still be stored; partials
    require event_ts or a future normalized candle exposing the exchange ts.

    Fast paths (H8) cover the two common cases — updating an entry within the
    ``CANDLE_FAST_WINDOW`` newest entries (``LSET``), or appending a new,
    later ``open_time`` (``LPUSH`` + ``LTRIM``) — without reading or
    rewriting the whole list. Only a write older than the window falls back
    to the full read-modify-rewrite.
    """
    event_ts = event_ts or getattr(candle, "event_ts", None)
    if event_ts is None and not candle.is_final:
        return False
    key = keys.candles_1m(candle.exchange, candle.symbol)
    value = to_wire(candle)
    if event_ts is not None:
        value["ts"] = event_ts.isoformat()

    window_rows = await redis.lrange(key, 0, CANDLE_FAST_WINDOW - 1)
    window: list[dict[str, Any]] = [msgpack.unpackb(row) for row in window_rows]

    for i, previous in enumerate(window):
        if previous["open_time"] != value["open_time"]:
            continue
        if not _candle_may_replace(value, previous, event_ts):
            return False
        async with redis.pipeline(transaction=True) as pipe:
            pipe.lset(key, i, msgpack.packb(value, use_bin_type=True))
            await pipe.execute()
        return True

    head = window[0] if window else None
    if head is None or value["open_time"] > head["open_time"]:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.lpush(key, msgpack.packb(value, use_bin_type=True))
            pipe.ltrim(key, 0, CANDLES_MAXLEN - 1)
            await pipe.execute()
        return True

    return await _push_candle_full_rewrite(redis, key, value, event_ts)


async def write_funding(redis: Any, funding: NormalizedFunding, *, realized: bool = False) -> bool:
    key = keys.derivatives(funding.exchange, funding.symbol)
    fields = _mapping(
        funding_rate=funding.funding_rate,
        funding_kind="realized" if realized else "estimated",
        next_funding_time=funding.next_funding_time.isoformat()
        if funding.next_funding_time
        else None,
        funding_ts=funding.ts.isoformat(),
    )
    accepted = await _hash(
        redis, key, fields, "funding_ts", funding.ts, DERIV_TTL_S, owned=FUNDING_FIELDS
    )
    if not realized:
        mark = _mapping(
            mark_price=funding.mark_price,
            index_price=funding.index_price,
            mark_ts=funding.ts.isoformat(),
        )
        accepted = (
            await _hash(redis, key, mark, "mark_ts", funding.ts, DERIV_TTL_S, owned=MARK_FIELDS)
            or accepted
        )
    return accepted


async def write_open_interest(redis: Any, oi: NormalizedOpenInterest) -> bool:
    fields = _mapping(
        open_interest=oi.open_interest,
        open_interest_value=oi.open_interest_value,
        oi_ts=oi.ts.isoformat(),
    )
    return await _hash(
        redis,
        keys.derivatives(oi.exchange, oi.symbol),
        fields,
        "oi_ts",
        oi.ts,
        DERIV_TTL_S,
        owned=OI_FIELDS,
    )
