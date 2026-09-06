"""Reading the market-worker's 1m candle hot state (``mkt:{ex}:{sym}:candles:1m``).

Read-only, and deliberately only the **tail**. The durable series lives in
Postgres; Redis is what covers the last minute or two the persistence batch has
not flushed yet, so an evaluation triggered by a bar-close event is not blind to
the very bar that triggered it. Everything in Redis may be lost without harm
(ARCHITECTURE.md §5.3), which is why nothing here is authoritative.

Non-final entries and anything closing after the cut are dropped here rather
than at the context: a partial candle is not an observation.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import msgpack

from hunter_core.domain.market import NormalizedCandle, from_wire
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)
_codec: Any = msgpack

__all__ = ["read_tail"]


def _decode(raw: bytes) -> NormalizedCandle | None:
    value: Any = _codec.unpackb(raw, raw=False)
    if not isinstance(value, dict):
        return None
    data: dict[str, Any] = dict(cast("dict[str, Any]", value))
    data.pop("ts", None)  # market-worker's partial-ordering token, not a model field
    try:
        return from_wire(NormalizedCandle, data)
    except Exception:
        logger.warning("shadow_hot_state_candle_unreadable")
        return None


async def read_tail(
    redis: redis_asyncio.Redis, *, exchange: str, symbol: str, count: int, cut: datetime
) -> list[NormalizedCandle]:
    """The newest ``count`` final 1m candles that had closed by ``cut``."""
    if count <= 0:
        return []
    key = keys.candles_1m(exchange, symbol)
    rows: list[bytes] = cast("list[bytes]", await redis.lrange(key, 0, count - 1))
    candles: list[NormalizedCandle] = []
    for raw in rows:
        candle = _decode(raw)
        if candle is None or not candle.is_final or candle.close_time > cut:
            continue
        if candle.exchange != exchange or candle.symbol != symbol:
            continue
        candles.append(candle)
    candles.sort(key=lambda candle: candle.open_time)
    return candles
