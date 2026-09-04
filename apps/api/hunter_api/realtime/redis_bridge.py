"""Bridges Redis pub/sub channels to the WebSocket fan-out.

Subscribes to a channel only when a client first wants it and unsubscribes
as soon as the last client leaves (ARCHITECTURE.md §5.2). Message delivery
to browsers goes through :class:`~hunter_api.realtime.ws_manager.ConnectionManager`
and :class:`~hunter_api.realtime.throttle.Throttle`; this class only owns the
Redis side of the bridge.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

from hunter_core.logging import get_logger

logger = get_logger(__name__)


class PubSubLike(Protocol):
    async def subscribe(self, *channels: str) -> object: ...
    async def unsubscribe(self, *channels: str) -> object: ...
    def listen(self) -> AsyncIterator[dict[str, Any]]: ...
    async def aclose(self) -> None: ...


class RedisClientLike(Protocol):
    """The one method the bridge needs from a Redis client — matches
    ``redis.asyncio.Redis`` structurally, and lets tests pass a fake.
    """

    def pubsub(self) -> PubSubLike: ...


class OnMessage(Protocol):
    async def __call__(self, channel: str, payload: bytes) -> None: ...


class RedisBridge:
    """One Redis pub/sub subscription per channel, torn down when unused."""

    def __init__(self, redis_client: RedisClientLike, on_message: OnMessage) -> None:
        self._pubsub = redis_client.pubsub()
        self._on_message = on_message
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def active_channels(self) -> list[str]:
        return list(self._tasks)

    async def ensure_subscribed(self, channel: str) -> None:
        """Subscribe to ``channel`` if not already subscribed; idempotent."""
        if channel in self._tasks:
            return
        await self._pubsub.subscribe(channel)
        self._tasks[channel] = asyncio.ensure_future(self._listen(channel))

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from ``channel``; a no-op if not subscribed."""
        task = self._tasks.pop(channel, None)
        if task is None:
            return
        task.cancel()
        await self._pubsub.unsubscribe(channel)

    async def _listen(self, channel: str) -> None:
        try:
            async for message in self._pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if data is not None:
                    await self._on_message(channel, data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("redis_bridge_listen_failed", channel=channel)

    async def close(self) -> None:
        """Unsubscribe from everything and close the underlying pub/sub connection."""
        for channel in list(self._tasks):
            await self.unsubscribe(channel)
        await self._pubsub.aclose()
