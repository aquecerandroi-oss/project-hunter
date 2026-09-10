"""A message reclaimed by ``XAUTOCLAIM`` while still queued in the dispatcher
runs exactly once (T3.74d code review, HIGH).

**The feedback loop.** ``BarDispatcher`` (T3.74c) lets ``run_consumer`` keep
reading past a bar still queued behind the concurrency semaphore or a busy
market lock -- but ``consume()``'s own ``XAUTOCLAIM`` (``claim_idle_ms``,
``hunter_core.events.consume``) reclaims *any* message this consumer group
has held unacked past that interval, including one this same process is still
holding because it is legitimately still queued/running, not dead. Before the
T3.74d fix, that redelivery was resubmitted to the dispatcher and run a
second time -- doubling work exactly during the burst the dispatcher exists
to absorb.

This suite fakes ``consume()`` directly (same pattern as
``test_consumer_supervision.py``) rather than sleeping in real time to reach a
real ``claim_idle_ms``: the scripted redelivery of the same stream entry
*is* what a real reclaim looks like once it reaches ``run_consumer`` -- how
long the real wait took is ``hunter_core.events.consume``'s concern, already
covered there, and ``ShadowConfig.claim_idle_ms``'s docstring states the
arithmetic and the bound for sizing that interval.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_core.events.envelope import EventEnvelope
from hunter_core.observability import registry
from hunter_strategy_worker import consumer as consumer_mod
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, run_consumer

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


def _envelope(symbol: str) -> EventEnvelope:
    return EventEnvelope(
        type="market.candles.closed",
        producer="test",
        key=symbol,
        payload={"exchange": "binance", "symbol": symbol, "market_type": "perpetual"},
    )


def _skipped(reason: str) -> float:
    value = registry.get_sample_value("hunter_shadow_bars_skipped_total", {"reason": reason})
    return 0.0 if value is None else value


class TestReclaimWhileStillInFlight:
    async def test_a_message_redelivered_while_still_queued_runs_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        envelope_a = _envelope("AAA")
        handled: list[str] = []
        acked: list[str] = []
        handler_a_started = asyncio.Event()
        release_a = asyncio.Event()
        call_count = 0

        async def stream(*_a: Any, **_kw: Any) -> AsyncIterator[tuple[str, EventEnvelope]]:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                # No second real pass in this test -- the fake `sleep` below
                # stops the loop before it gets here in practice, this is just
                # a safety net against ever re-yielding the same fixture twice.
                return
            yield ("1-1", envelope_a)
            # The redelivery: XAUTOCLAIM reclaiming the SAME still-unacked
            # entry because it sat in this consumer's own pending list longer
            # than `claim_idle_ms` -- even though the bar is still queued
            # right here, not dead.
            yield ("1-1", envelope_a)

        async def fake_handle_candle(*_a: Any, payload: dict[str, Any], **_kw: Any) -> None:
            handled.append(payload["symbol"])
            handler_a_started.set()
            await release_a.wait()

        async def fake_ack(
            _redis: Any, _stream: Any, _group: Any, message_id: str, _envelope: Any
        ) -> None:
            acked.append(message_id)

        async def fake_sleep(_delay: float) -> None:
            raise asyncio.CancelledError

        monkeypatch.setattr(consumer_mod, "consume", stream)
        monkeypatch.setattr(consumer_mod, "handle_candle", fake_handle_candle)
        monkeypatch.setattr(consumer_mod, "ack", fake_ack)
        monkeypatch.setattr(consumer_mod.asyncio, "sleep", fake_sleep)

        runtime, health = _Runtime(), ConsumerHealth()
        # T3.82: disabled here -- this test is about redelivery dedup, not the
        # shadow-universe gate, which would otherwise query a real database
        # against `factory=None`.
        config = ShadowConfig(universe_min_history_days=0)
        before = _skipped("already_in_flight")

        bg_task = asyncio.ensure_future(
            run_consumer(None, None, runtime, config, health)  # type: ignore[arg-type]
        )
        await asyncio.wait_for(handler_a_started.wait(), timeout=1.0)

        # By the time the handler has started, both stream entries have
        # already been read and submitted (the loop only reaches
        # `dispatcher.drain()` -- which is what lets the handler run at all --
        # after the whole batch, redelivery included, was processed).
        assert handled == ["AAA"], "the redelivered duplicate ran its own handler a second time"
        assert _skipped("already_in_flight") == before + 1

        release_a.set()
        with pytest.raises(asyncio.CancelledError):
            await bg_task

        assert handled == ["AAA"]
        assert acked == ["1-1"], "message A must be acked exactly once"
