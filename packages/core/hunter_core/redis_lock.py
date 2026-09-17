"""A distributed lock over Redis (``SET NX PX``), split out of ``redis.py`` by
responsibility — the key builders and the client factory there are pure
plumbing, this is the one piece of behaviour among them.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

__all__ = ["acquire_lock"]

_RELEASE_IF_OWNER_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


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
