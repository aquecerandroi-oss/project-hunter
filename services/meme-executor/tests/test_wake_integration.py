"""Integration: a real Redis publish wakes a real ``ProposalWakeListener``
within 200 ms (testcontainers — mirrors ``conftest.py``'s pattern).

This is the Redis-pub/sub equivalent of what the brief asked as a Postgres
``LISTEN``/``NOTIFY`` proof: the radar's insert path publishes right after
commit (``hunter_meme_worker.wake.wake_publisher``); here the publish comes
from a plain client to isolate the one thing this test owns — the listener
side of the wake, not the radar's own insert/commit path (covered by
``services/meme-worker/tests/test_lab_wake.py``).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

import pytest

from hunter_core.redis import keys
from hunter_meme_executor.wake import ProposalWakeListener

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

pytestmark = [pytest.mark.integration]


async def test_a_real_publish_wakes_the_listener_within_200ms(
    redis_client: redis_asyncio.Redis,
) -> None:
    event = asyncio.Event()
    listener = ProposalWakeListener(redis_client, event)
    task = asyncio.ensure_future(listener.run())
    try:
        # Give the subscription a moment to actually register with the server
        # before publishing — a publish before SUBSCRIBE lands nobody.
        for _ in range(50):
            reached = await redis_client.publish(  # type: ignore[reportUnknownMemberType]
                keys.meme_proposals_wake(), b"0"
            )
            if reached > 0:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("listener never subscribed")
        event.clear()

        started = time.monotonic()
        subscribers = await redis_client.publish(  # type: ignore[reportUnknownMemberType]
            keys.meme_proposals_wake(), b"1"
        )
        assert subscribers >= 1
        await asyncio.wait_for(event.wait(), timeout=0.2)
        elapsed = time.monotonic() - started
        assert elapsed < 0.2, elapsed
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
