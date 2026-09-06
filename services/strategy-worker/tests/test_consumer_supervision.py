"""The decision loop survives Redis; it does not die with it.

Found in the S2 operational proof, against the real stack: ``consume()``'s
default ``block_ms`` is 5000 and ``create_redis`` sets ``socket_timeout=5.0``
(HIGH-4, ``hunter_core/redis.py``). A blocking ``XREADGROUP`` that waits its
full budget therefore races the socket read deadline and raises
``redis.exceptions.TimeoutError`` on an idle stream — which propagated out of
the async generator, out of ``run_consumer``, and killed the TaskGroup. The
container restarted (``restart: unless-stopped``), so nothing was lost, but a
worker that dies every time the stream goes quiet is not supervised, it is
supervised-by-accident.

Two fixes, both here: block for less than the socket budget, and treat any
error from the iteration as a backoff instead of a death.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_core.events.envelope import EventEnvelope
from hunter_strategy_worker import consumer as consumer_mod
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import CONSUME_BLOCK_MS, ConsumerHealth, run_consumer

pytestmark = pytest.mark.unit


class _Runtime:
    def __init__(self) -> None:
        self.instance = "test:1"
        self.errors = 0
        self.successes = 0

    def mark_error(self) -> None:
        self.errors += 1

    def mark_success(self) -> None:
        self.successes += 1


def _envelope() -> EventEnvelope:
    return EventEnvelope(type="market.candles.closed", producer="test", key="k", payload={})


class TestBlockBudget:
    def test_the_block_budget_is_under_the_client_socket_timeout(self) -> None:
        """``hunter_core.redis`` bounds every read at 5 s; a 5 s block is a
        coin flip between "the stream is quiet" and "the socket died"."""
        from hunter_core.redis import _SOCKET_TIMEOUT_S  # pyright: ignore[reportPrivateUsage]

        assert CONSUME_BLOCK_MS / 1000 < _SOCKET_TIMEOUT_S


class TestSupervision:
    async def test_a_redis_error_is_a_backoff_not_a_death(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0

        async def flaky(*_args: Any, **_kwargs: Any) -> AsyncIterator[tuple[str, EventEnvelope]]:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("Timeout reading from redis:6379")
            await asyncio.sleep(0)
            yield ("1-1", _envelope())

        async def noop_handle(*_args: Any, **_kwargs: Any) -> None:
            return None

        async def noop_ack(*_args: Any, **_kwargs: Any) -> None:
            return None

        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)
            if len(sleeps) >= 2:
                raise asyncio.CancelledError

        monkeypatch.setattr(consumer_mod, "consume", flaky)
        monkeypatch.setattr(consumer_mod, "handle_candle", noop_handle)
        monkeypatch.setattr(consumer_mod, "ack", noop_ack)
        monkeypatch.setattr(consumer_mod.asyncio, "sleep", fake_sleep)

        runtime, health = _Runtime(), ConsumerHealth()
        with pytest.raises(asyncio.CancelledError):
            await run_consumer(None, None, runtime, ShadowConfig(), health)  # type: ignore[arg-type]

        assert attempts >= 2, "the loop re-entered consume() instead of dying"
        assert runtime.errors == 1
        assert sleeps[0] > 0

    async def test_one_bad_message_does_not_stop_the_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handled = 0

        async def stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[tuple[str, EventEnvelope]]:
            for index in range(3):
                yield (f"{index}-0", _envelope())

        async def sometimes_failing(*_args: Any, **_kwargs: Any) -> None:
            nonlocal handled
            handled += 1
            if handled == 2:
                raise ValueError("one unreadable payload")

        async def noop_ack(*_args: Any, **_kwargs: Any) -> None:
            return None

        async def fake_sleep(_delay: float) -> None:
            raise asyncio.CancelledError

        monkeypatch.setattr(consumer_mod, "consume", stream)
        monkeypatch.setattr(consumer_mod, "handle_candle", sometimes_failing)
        monkeypatch.setattr(consumer_mod, "ack", noop_ack)
        monkeypatch.setattr(consumer_mod.asyncio, "sleep", fake_sleep)

        runtime, health = _Runtime(), ConsumerHealth()
        with pytest.raises(asyncio.CancelledError):
            await run_consumer(None, None, runtime, ShadowConfig(), health)  # type: ignore[arg-type]

        assert handled == 3, "the third message was still delivered"
        assert health.errors == 1
        assert runtime.successes == 2, "only the messages that worked were acked"
