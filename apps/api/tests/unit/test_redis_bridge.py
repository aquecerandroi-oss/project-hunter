"""``RedisBridge`` subscribes on first interest and unsubscribes when unused.

The dispatcher must route every message by the channel/pattern it actually
carries — never by which caller happened to subscribe it — so a message
published on one Redis channel can never be misdelivered as another
(ARCHITECTURE.md §5.2 requires per-org isolation on ``rt:org:{id}:*``).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_api.realtime.redis_bridge import RedisBridge

pytestmark = pytest.mark.unit


class _FakePubSub:
    """Models ``redis.asyncio.client.PubSub``: ``listen()`` blocks for the
    next message (via a queue) rather than ever finishing on its own, same
    as the real connection would.
    """

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.psubscribed: list[str] = []
        self.punsubscribed: list[str] = []
        self.closed = False
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def queue_message(self, channel: str, data: bytes) -> None:
        self._queue.put_nowait({"type": "message", "channel": channel, "data": data})

    def queue_pmessage(self, pattern: str, channel: str, data: bytes) -> None:
        self._queue.put_nowait(
            {"type": "pmessage", "pattern": pattern, "channel": channel, "data": data}
        )

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def psubscribe(self, *patterns: str) -> None:
        self.psubscribed.extend(patterns)

    async def punsubscribe(self, *patterns: str) -> None:
        self.punsubscribed.extend(patterns)

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            message = await self._queue.get()
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


async def _drain() -> None:
    """Give the background dispatcher task a couple of loop turns to run."""
    for _ in range(3):
        await asyncio.sleep(0)


async def test_ensure_subscribed_subscribes_once_and_delivers_messages() -> None:
    pubsub = _FakePubSub()
    pubsub.queue_message("rt:radar", b"payload")
    received: list[tuple[str, bytes]] = []

    async def on_message(channel: str, payload: bytes) -> None:
        received.append((channel, payload))

    bridge = RedisBridge(_FakeRedisClient(pubsub), on_message)

    await bridge.ensure_subscribed("rt:radar")
    await bridge.ensure_subscribed("rt:radar")  # idempotent: no second subscribe
    await _drain()

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


async def test_dispatcher_routes_each_message_to_its_own_channel_only() -> None:
    """The historical bug: one task per channel, each tagging every message
    it happened to receive with its own closure-bound channel. With a single
    dispatcher routing by the message's own ``channel`` field, an org-scoped
    message must never surface under an unrelated channel like ``rt:radar``.
    """
    pubsub = _FakePubSub()
    received: list[tuple[str, bytes]] = []

    async def on_message(channel: str, payload: bytes) -> None:
        received.append((channel, payload))

    bridge = RedisBridge(_FakeRedisClient(pubsub), on_message)
    await bridge.ensure_subscribed("rt:radar")
    await bridge.ensure_subscribed("rt:org:X:risk")

    pubsub.queue_message("rt:radar", b"radar-1")
    pubsub.queue_message("rt:org:X:risk", b"risk-1")
    pubsub.queue_message("rt:radar", b"radar-2")
    pubsub.queue_message("rt:org:X:risk", b"risk-2")
    await _drain()

    assert received == [
        ("rt:radar", b"radar-1"),
        ("rt:org:X:risk", b"risk-1"),
        ("rt:radar", b"radar-2"),
        ("rt:org:X:risk", b"risk-2"),
    ]
    # The org payloads must never be observed tagged as the radar channel.
    assert not any(
        channel == "rt:radar" and payload in {b"risk-1", b"risk-2"} for channel, payload in received
    )


async def test_dispatcher_starts_on_first_subscribe_and_stops_on_last_unsubscribe() -> None:
    pubsub = _FakePubSub()
    bridge = RedisBridge(_FakeRedisClient(pubsub), _noop)

    assert not bridge.is_running

    await bridge.ensure_subscribed("rt:radar")
    await _drain()
    assert bridge.is_running
    # Task identity (not just is_running) is needed below to prove the same
    # dispatcher keeps serving both channels rather than being torn down and
    # recreated in between.
    dispatcher = bridge._dispatcher  # pyright: ignore[reportPrivateUsage]
    assert dispatcher is not None

    await bridge.ensure_subscribed("rt:system")
    assert bridge._dispatcher is dispatcher  # pyright: ignore[reportPrivateUsage]  # one dispatcher serves both channels

    await bridge.unsubscribe("rt:radar")
    assert bridge._dispatcher is dispatcher  # pyright: ignore[reportPrivateUsage]  # rt:system still active

    await bridge.unsubscribe("rt:system")
    assert not bridge.is_running
    assert dispatcher.cancelled()


async def test_a_raising_callback_does_not_stop_delivery_of_the_next_message() -> None:
    pubsub = _FakePubSub()
    received: list[bytes] = []

    async def flaky_on_message(channel: str, payload: bytes) -> None:
        if payload == b"boom":
            raise RuntimeError("boom")
        received.append(payload)

    bridge = RedisBridge(_FakeRedisClient(pubsub), flaky_on_message)
    await bridge.ensure_subscribed("rt:radar")

    pubsub.queue_message("rt:radar", b"boom")
    pubsub.queue_message("rt:radar", b"ok")
    await _drain()

    assert received == [b"ok"]


async def test_pattern_subscription_uses_psubscribe_and_routes_by_real_channel() -> None:
    pubsub = _FakePubSub()
    received: list[tuple[str, bytes]] = []

    async def on_message(channel: str, payload: bytes) -> None:
        received.append((channel, payload))

    bridge = RedisBridge(_FakeRedisClient(pubsub), on_message)
    await bridge.ensure_subscribed("rt:org:*:risk")

    pubsub.queue_pmessage("rt:org:*:risk", "rt:org:X:risk", b"risk-1")
    await _drain()

    assert pubsub.psubscribed == ["rt:org:*:risk"]
    assert pubsub.subscribed == []
    assert received == [("rt:org:X:risk", b"risk-1")]
