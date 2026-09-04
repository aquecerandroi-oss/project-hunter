"""``RedisBridge`` subscribes on first interest and unsubscribes when unused."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_api.realtime.redis_bridge import RedisBridge

pytestmark = pytest.mark.unit


class _FakePubSub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False
        self._messages: list[dict[str, Any]] = []

    def queue_message(self, channel: str, data: bytes) -> None:
        self._messages.append({"type": "message", "channel": channel, "data": data})

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        for message in self._messages:
            yield message

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedisClient:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


async def _noop(channel: str, payload: bytes) -> None:
    return None


async def test_ensure_subscribed_subscribes_once_and_delivers_messages() -> None:
    pubsub = _FakePubSub()
    pubsub.queue_message("rt:radar", b"payload")
    received: list[tuple[str, bytes]] = []

    async def on_message(channel: str, payload: bytes) -> None:
        received.append((channel, payload))

    bridge = RedisBridge(_FakeRedisClient(pubsub), on_message)

    await bridge.ensure_subscribed("rt:radar")
    await bridge.ensure_subscribed("rt:radar")  # idempotent: no second subscribe
    await asyncio.sleep(0.01)  # let the background listen loop drain the fake messages

    assert pubsub.subscribed == ["rt:radar"]
    assert received == [("rt:radar", b"payload")]


async def test_unsubscribe_is_a_noop_when_not_subscribed() -> None:
    pubsub = _FakePubSub()
    bridge = RedisBridge(_FakeRedisClient(pubsub), _noop)

    await bridge.unsubscribe("rt:radar")

    assert pubsub.unsubscribed == []


async def test_unsubscribe_stops_tracking_the_channel() -> None:
    pubsub = _FakePubSub()
    bridge = RedisBridge(_FakeRedisClient(pubsub), _noop)
    await bridge.ensure_subscribed("rt:radar")

    await bridge.unsubscribe("rt:radar")

    assert pubsub.unsubscribed == ["rt:radar"]
    assert bridge.active_channels == []


async def test_close_unsubscribes_everything_and_closes_the_pubsub() -> None:
    pubsub = _FakePubSub()
    bridge = RedisBridge(_FakeRedisClient(pubsub), _noop)
    await bridge.ensure_subscribed("rt:radar")
    await bridge.ensure_subscribed("rt:system")

    await bridge.close()

    assert set(pubsub.unsubscribed) == {"rt:radar", "rt:system"}
    assert pubsub.closed is True
