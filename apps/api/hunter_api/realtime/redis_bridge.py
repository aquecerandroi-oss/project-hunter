"""Bridges Redis pub/sub channels to the WebSocket fan-out.

Subscribes to a channel only when a client first wants it and unsubscribes
as soon as the last client leaves (ARCHITECTURE.md §5.2). Message delivery
to browsers goes through :class:`~hunter_api.realtime.ws_manager.ConnectionManager`
and :class:`~hunter_api.realtime.throttle.Throttle`; this class only owns the
Redis side of the bridge.

A single dispatcher task drains ``pubsub.listen()`` and routes every message
by the channel/pattern it actually carries on the message itself — never by
which caller happened to subscribe it. That matters because one shared
``PubSub`` connection interleaves messages for every subscribed channel on
one stream: a design that hands one task per channel its own closure-bound
channel name (instead of reading the message's real channel) can deliver a
message published on ``rt:org:X:risk`` mislabeled as ``rt:radar`` — a
cross-tenant leak. Routing off the message's own field avoids that.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any, Protocol

from hunter_core.logging import get_logger

logger = get_logger(__name__)

_PATTERN_CHARS = frozenset("*?[")


def _is_pattern(channel: str) -> bool:
    return any(char in channel for char in _PATTERN_CHARS)


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class PubSubLike(Protocol):
    async def subscribe(self, *channels: str) -> object: ...
    async def unsubscribe(self, *channels: str) -> object: ...
    async def psubscribe(self, *patterns: str) -> object: ...
    async def punsubscribe(self, *patterns: str) -> object: ...
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
    """One shared ``PubSub`` connection; a single dispatcher task fans its
    messages out by their own channel/pattern, torn down when unused.
    """

    def __init__(self, redis_client: RedisClientLike, on_message: OnMessage) -> None:
        self._pubsub = redis_client.pubsub()
        self._on_message = on_message
        self._channels: set[str] = set()
        self._patterns: set[str] = set()
        self._dispatcher: asyncio.Task[None] | None = None

    @property
    def active_channels(self) -> list[str]:
        return sorted(self._channels | self._patterns)

    @property
    def is_running(self) -> bool:
        """Whether the dispatcher task is alive (exists and hasn't finished)."""
        return self._dispatcher is not None and not self._dispatcher.done()

    async def ensure_subscribed(self, channel: str) -> None:
        """Subscribe to ``channel`` if not already subscribed; idempotent.

        A ``channel`` containing glob characters (``*``, ``?``, ``[``) is
        treated as a pattern and subscribed via ``PSUBSCRIBE``.
        """
        if _is_pattern(channel):
            if channel in self._patterns:
                return
            await self._pubsub.psubscribe(channel)
            self._patterns.add(channel)
        else:
            if channel in self._channels:
                return
            await self._pubsub.subscribe(channel)
            self._channels.add(channel)
        self._ensure_dispatcher_running()

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from ``channel``; a no-op if not subscribed."""
        if channel in self._patterns:
            self._patterns.discard(channel)
            await self._pubsub.punsubscribe(channel)
        elif channel in self._channels:
            self._channels.discard(channel)
            await self._pubsub.unsubscribe(channel)
        else:
            return
        if not self._channels and not self._patterns:
            await self._stop_dispatcher()

    async def close(self) -> None:
        """Unsubscribe from everything and close the underlying pub/sub connection."""
        for channel in list(self._channels | self._patterns):
            await self.unsubscribe(channel)
        await self._pubsub.aclose()

    def _ensure_dispatcher_running(self) -> None:
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.ensure_future(self._dispatch())

    async def _stop_dispatcher(self) -> None:
        task, self._dispatcher = self._dispatcher, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _dispatch(self) -> None:
        """The single consumer of ``pubsub.listen()``. A callback that raises
        is logged and skipped without breaking delivery of the next message
        or killing this task.
        """
        try:
            async for message in self._pubsub.listen():
                await self._dispatch_one(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("redis_bridge_dispatch_failed")

    async def _dispatch_one(self, message: dict[str, Any]) -> None:
        if message.get("type") not in ("message", "pmessage"):
            return
        raw_channel = message.get("channel")
        if raw_channel is None:
            return
        channel = _decode(raw_channel)
        data = message.get("data")
        if data is None:
            return
        try:
            await self._on_message(channel, data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("redis_bridge_on_message_failed", channel=channel)
