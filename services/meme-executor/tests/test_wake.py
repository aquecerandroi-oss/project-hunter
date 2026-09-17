"""Unit tests for ``ProposalWakeListener`` — a fake pub/sub, no Redis needed.

The integration test that a *real* publish wakes a *real* listener within
200 ms lives in ``test_wake_integration.py`` (Redis via testcontainers).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_meme_executor.wake import ProposalWakeListener

pytestmark = pytest.mark.unit


class _FakePubSub:
    """Replays a scripted sequence of ``listen()`` messages, then blocks
    forever (a real subscription never ends on its own)."""

    def __init__(self, messages: list[dict[str, Any]], *, fail_after: int | None = None) -> None:
        self._messages = messages
        self._fail_after = fail_after
        self.subscribed: list[str] = []
        self.closed = False

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        for i, message in enumerate(self._messages):
            if self._fail_after is not None and i == self._fail_after:
                raise ConnectionError("connection lost")
            yield message
        await asyncio.Event().wait()  # a live subscription blocks, it never ends

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsubs: list[_FakePubSub]) -> None:
        self._pubsubs = list(pubsubs)
        self.created: list[_FakePubSub] = []

    def pubsub(self) -> _FakePubSub:
        p = self._pubsubs.pop(0)
        self.created.append(p)
        return p


async def _run_until(
    event: asyncio.Event, task: asyncio.Task[None], timeout_s: float = 1.0
) -> None:
    await asyncio.wait_for(event.wait(), timeout=timeout_s)
    task.cancel()
    with __import__("contextlib").suppress(asyncio.CancelledError):
        await task


async def test_event_set_on_real_message() -> None:
    pubsub = _FakePubSub([{"type": "subscribe", "data": 1}, {"type": "message", "data": b"1"}])
    redis = _FakeRedis([pubsub])
    event = asyncio.Event()
    listener = ProposalWakeListener(redis, event)  # type: ignore[arg-type]
    task = asyncio.ensure_future(listener.run())
    await _run_until(event, task)
    assert pubsub.subscribed == ["meme:proposals:wake"]


async def test_subscribe_ack_alone_does_not_set_the_event() -> None:
    pubsub = _FakePubSub([{"type": "subscribe", "data": 1}])
    redis = _FakeRedis([pubsub])
    event = asyncio.Event()
    listener = ProposalWakeListener(redis, event)  # type: ignore[arg-type]
    task = asyncio.ensure_future(listener.run())
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(event.wait(), timeout=0.2)
    task.cancel()
    with __import__("contextlib").suppress(asyncio.CancelledError):
        await task


async def test_reconnects_with_backoff_after_a_dropped_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    first = _FakePubSub(
        [{"type": "message", "data": b"1"}, {"type": "message", "data": b"1"}], fail_after=1
    )
    second = _FakePubSub([{"type": "message", "data": b"1"}])
    redis = _FakeRedis([first, second])
    event = asyncio.Event()
    listener = ProposalWakeListener(redis, event)  # type: ignore[arg-type]
    task = asyncio.ensure_future(listener.run())
    # The first pubsub's message sets the event; by the time this wakes,
    # the drop + reconnect + second pubsub's own message have already run
    # too (nothing in the listener suspends until it blocks on a fresh
    # subscription with no more scripted messages).
    await asyncio.wait_for(event.wait(), timeout=1.0)
    task.cancel()
    with __import__("contextlib").suppress(asyncio.CancelledError):
        await task
    assert len(redis.created) == 2
    assert sleeps  # the reconnect slept at least once, backed off
    assert first.closed
