"""Universe leader election and snapshot sharing between market-worker shards.

T1.6b-C4: with ``MARKET_SHARD=i/N`` one shard per exchange holds a token-checked
Redis lock and refreshes the universe from REST (the *leader*); every other
shard *follows* its versioned snapshot, or Postgres when the snapshot is stale
or missing -- never REST. Split out of ``universe.py`` for the 350-line budget.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy import select

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.settings import Settings

logger = get_logger(__name__)

LEADER_LOCK_TTL_S = 60
"""C4: lock TTL, short relative to the 900s default refresh interval so a
dead leader's followers do not wait a full cycle to notice."""
LEADER_RENEW_INTERVAL_S = 20.0
"""Renew at 1/3 of the TTL, *during* the sleep between refreshes."""
FOLLOWER_POLL_S = 15.0
"""Follower re-check cadence -- independent of the refresh interval so a
dead leader is replaced within one lock TTL."""
SNAPSHOT_TTL_MULTIPLIER = 3
"""Snapshot TTL and follower staleness cutoff are both this x the refresh interval."""

_EXTEND_IF_OWNER_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""  # Astra: only the current token may extend -- a lost lock is never resurrected.

_SNAPSHOT_CAS_LUA = """
local current = redis.call('GET', KEYS[1])
if current then
    local ok, decoded = pcall(cjson.decode, current)
    if ok and decoded.version and tonumber(decoded.version) >= tonumber(ARGV[2]) then
        return 0
    end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
return 1
"""  # Astra: a resumed-after-pause leader publishing a stale version is rejected.


async def try_become_leader(
    redis: redis_asyncio.Redis, exchange: str, token: str, *, ttl_s: int = LEADER_LOCK_TTL_S
) -> tuple[bool, str]:
    """``SET NX EX`` with a per-run token, re-checked rather than blindly
    re-acquired when we already believe we hold it."""
    key = f"market:universe:leader:{exchange}"
    if token:
        current = await redis.get(key)
        if current is not None and current == token.encode():
            return True, token
    new_token = secrets.token_hex(16)
    acquired = bool(await redis.set(key, new_token, nx=True, ex=ttl_s))
    return (True, new_token) if acquired else (False, "")


async def extend_leader(
    redis: redis_asyncio.Redis, exchange: str, token: str, *, ttl_s: int = LEADER_LOCK_TTL_S
) -> bool:
    key = f"market:universe:leader:{exchange}"
    return bool(await redis.eval(_EXTEND_IF_OWNER_LUA, 1, key, token, ttl_s))


async def load_snapshot(redis: redis_asyncio.Redis, exchange: str) -> dict[str, Any] | None:
    raw = await redis.get(f"market:universe:{exchange}")
    if raw is None:
        return None
    try:
        return orjson.loads(raw)
    except Exception:
        logger.warning("market_universe_snapshot_corrupt", exchange=exchange)
        return None


async def write_snapshot(
    redis: redis_asyncio.Redis, exchange: str, symbols: list[str], version: int, ttl_s: float
) -> bool:
    body = {"symbols": sorted(symbols), "computed_at": utcnow().isoformat(), "version": version}
    payload, key = orjson.dumps(body), f"market:universe:{exchange}"
    accepted = bool(await redis.eval(_SNAPSHOT_CAS_LUA, 1, key, payload, version, int(ttl_s)))
    if not accepted:
        logger.warning("market_universe_snapshot_rejected", exchange=exchange, version=version)
    return accepted


async def follower_symbols(
    session_factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    exchange: str,
    settings: Settings,
) -> list[str]:
    """Leader's snapshot, else Postgres ``is_monitored`` -- never REST. A
    Postgres failure propagates so the universe stays put, not emptied."""
    data: dict[str, Any] | None = None
    try:
        data = await load_snapshot(redis, exchange)
    except Exception:
        logger.warning("market_universe_snapshot_read_failed", exchange=exchange, exc_info=True)
    if data is not None:
        computed_at = ensure_utc(datetime.fromisoformat(data["computed_at"]))
        age_s = (utcnow() - computed_at).total_seconds()
        if age_s <= SNAPSHOT_TTL_MULTIPLIER * settings.market_universe_refresh_s:
            return [str(s) for s in data["symbols"]]
        logger.warning("market_universe_snapshot_stale", exchange=exchange, age_s=age_s)
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(Market.symbol)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == exchange, Market.is_monitored.is_(True))
        )
        return sorted(rows)
