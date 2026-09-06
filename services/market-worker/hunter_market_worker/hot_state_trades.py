"""Redis hot state for the recent-trade ring buffer + in-memory dedupe.
Split out of ``hot_state.py`` for the 350-line budget; ``hot_state``
re-exports :class:`TradeMemory` and :func:`push_trade` so callers keep one
import."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

from hunter_core.domain.market import NormalizedTrade
from hunter_core.redis import keys
from hunter_market_worker import wire as msgpack

TRADES_MAXLEN = 2000
# A WS reconnect only ever replays a handful of recent trades, so a 50-item
# window (newest-first) covers dedupe/ordering without reading the whole
# 2000-item ring buffer on every single trade (H7).
TRADE_DEDUPE_WINDOW = 50


class TradeMemory:
    """Bounded per-(exchange, symbol) recent-trade-id window + newest ``ts``
    (B4/H7): replaces a per-trade ``LRANGE`` + msgpack-unpack of up to
    :data:`TRADE_DEDUPE_WINDOW` rows (2.48% of the worker's own CPU at 50
    markets, t16b-profile.md) with an in-memory check. Seeded from Redis
    once per symbol on first touch so a worker restart (blank memory) never
    duplicates a trade already in the ring buffer. Bounded and dropped via
    :meth:`forget` when a symbol leaves the universe (same bug class as F11
    in ``ws.py`` — an unbounded per-symbol map growing forever)."""

    def __init__(self, window: int = TRADE_DEDUPE_WINDOW) -> None:
        self._window = window
        self._ids: dict[tuple[str, str], deque[str]] = {}
        self._newest_ts: dict[tuple[str, str], datetime] = {}
        self._seeded: set[tuple[str, str]] = set()

    def forget(self, exchange: str, symbol: str) -> None:
        key = (exchange, symbol)
        self._ids.pop(key, None)
        self._newest_ts.pop(key, None)
        self._seeded.discard(key)

    async def _seed(self, redis: Any, exchange: str, symbol: str) -> None:
        key = (exchange, symbol)
        rows = await redis.lrange(keys.trades(exchange, symbol), 0, self._window - 1)
        decoded: list[dict[str, Any]] = [msgpack.unpackb(row) for row in rows]
        self._ids[key] = deque((row["trade_id"] for row in decoded), maxlen=self._window)
        if decoded:
            self._newest_ts[key] = datetime.fromisoformat(decoded[0]["ts"])
        self._seeded.add(key)

    async def accepts(self, redis: Any, trade: NormalizedTrade) -> bool:
        key = (trade.exchange, trade.symbol)
        if key not in self._seeded:
            await self._seed(redis, trade.exchange, trade.symbol)
        ids = self._ids.setdefault(key, deque(maxlen=self._window))
        if trade.trade_id in ids:
            return False
        newest = self._newest_ts.get(key)
        if newest is not None and trade.ts < newest:
            return False
        ids.appendleft(trade.trade_id)
        if newest is None or trade.ts > newest:
            self._newest_ts[key] = trade.ts
        return True


async def push_trade(redis: Any, trade: NormalizedTrade, memory: TradeMemory) -> bool:
    if not await memory.accepts(redis, trade):
        return False
    key = keys.trades(trade.exchange, trade.symbol)
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
