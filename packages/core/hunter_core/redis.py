"""Redis client factory, hot-state key builders and a distributed lock.

Key layout mirrors ARCHITECTURE.md §5.3 exactly. Everything here can be lost
without harm (ARCHITECTURE.md §5.3: "O que esta em Redis pode ser perdido.")
— nothing that matters for audit or accounting lives only in Redis.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import redis.asyncio as redis_asyncio

if TYPE_CHECKING:
    from hunter_core.settings import Settings

_RELEASE_IF_OWNER_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def create_redis(settings: Settings) -> redis_asyncio.Redis:
    """A ``redis.asyncio`` client for ``REDIS_URL``. Bytes in, bytes out —
    callers that need text decode themselves (payloads are orjson bytes).
    """
    redis_url = settings.redis_url
    if redis_url is None:
        raise ValueError("REDIS_URL is not configured")
    return redis_asyncio.from_url(redis_url.get_secret_value(), decode_responses=False)


async def check_redis(client: redis_asyncio.Redis) -> bool:
    """``PING`` — true if Redis answers, false on any error."""
    try:
        pong = await client.ping()  # type: ignore[reportUnknownMemberType]
    except Exception:
        return False
    return bool(pong)


class keys:
    """Hot-state key builders — one per row of ARCHITECTURE.md §5.3."""

    @staticmethod
    def ticker(exchange: str, symbol: str) -> str:
        return f"mkt:{exchange}:{symbol}:ticker"

    @staticmethod
    def book(exchange: str, symbol: str) -> str:
        return f"mkt:{exchange}:{symbol}:book"

    @staticmethod
    def trades(exchange: str, symbol: str) -> str:
        return f"mkt:{exchange}:{symbol}:trades"

    @staticmethod
    def candles_1m(exchange: str, symbol: str) -> str:
        return f"mkt:{exchange}:{symbol}:candles:1m"

    @staticmethod
    def derivatives(exchange: str, symbol: str) -> str:
        return f"mkt:{exchange}:{symbol}:deriv"

    @staticmethod
    def features(exchange: str, symbol: str) -> str:
        return f"feat:{exchange}:{symbol}"

    @staticmethod
    def opportunity(exchange: str, symbol: str) -> str:
        return f"opp:{exchange}:{symbol}"

    @staticmethod
    def radar_scores() -> str:
        return "radar:scores"

    @staticmethod
    def regime_current() -> str:
        return "regime:current"

    @staticmethod
    def kill_switch_system() -> str:
        return "ks:system"

    @staticmethod
    def kill_switch_org(org_id: str) -> str:
        return f"ks:org:{org_id}"

    @staticmethod
    def kill_switch_portfolio(portfolio_id: str) -> str:
        return f"ks:pf:{portfolio_id}"

    @staticmethod
    def heartbeat(role: str, instance: str) -> str:
        return f"hb:{role}:{instance}"

    @staticmethod
    def rate_limit(exchange: str, bucket: str) -> str:
        return f"rl:{exchange}:{bucket}"

    @staticmethod
    def lock(name: str) -> str:
        return f"lock:{name}"

    @staticmethod
    def processed(consumer: str) -> str:
        """``hunter:processed:{consumer}`` — idempotency SET (events.py)."""
        return f"hunter:processed:{consumer}"


@asynccontextmanager
async def acquire_lock(
    client: redis_asyncio.Redis, name: str, ttl_ms: int
) -> AsyncGenerator[bool, None]:
    """A distributed lock via ``SET NX PX``.

    Yields ``True`` if the lock was acquired, ``False`` otherwise — callers
    must check the yielded value; the body still runs either way so callers
    can decide (log and skip, wait, etc.) instead of the lock silently
    swallowing contention. Release is a Lua script that only deletes the key
    if it still holds this holder's token, so a lock that outlived its TTL
    and was re-acquired by someone else is never deleted out from under them.
    """
    token = secrets.token_hex(16)
    key = keys.lock(name)
    acquired = bool(await client.set(key, token, nx=True, px=ttl_ms))
    try:
        yield acquired
    finally:
        if acquired:
            await client.eval(_RELEASE_IF_OWNER_SCRIPT, 1, key, token)
