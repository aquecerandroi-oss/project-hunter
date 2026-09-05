"""Redis hot state for 1-minute candles (newest at index 0, ``CANDLES_MAXLEN``
deep). Split out of ``hot_state.py`` for the 350-line budget; ``hot_state``
re-exports :func:`push_candle` so callers keep one import."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.redis import keys
from hunter_market_worker import wire as msgpack

CANDLES_MAXLEN = 1500
# Fast-path window for push_candle: almost every write either updates the
# current (head) minute or opens a new one, both covered by the 16 newest
# entries. Only a write older than this window falls back to the rare full
# read-modify-rewrite (H8).
CANDLE_FAST_WINDOW = 16


def is_newer(ts: datetime, previous: bytes | str | None) -> bool:
    if previous is None:
        return True
    value = previous.decode() if isinstance(previous, bytes) else previous
    return ts > datetime.fromisoformat(value)


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
    return event_ts is None or not previous.get("ts") or is_newer(event_ts, previous["ts"])


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
