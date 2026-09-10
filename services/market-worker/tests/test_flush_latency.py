"""T3.81: a final candle reaches ``flush_batch`` within the configured batch
window, not the old fixed 1.0s floor.

No Postgres/Redis: ``flush_batch`` is monkeypatched to a stub that only
records when it was called, so this proves the *timing* of
``persist.drain_loop`` in isolation. The DB-backed proof that a flushed batch
still lands correctly (row + outbox row + ``observe_flush_lag``) is
``test_persist.py``'s existing ``testflush_batch_writes_...`` plus the new
integration case added alongside it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_market_worker import persist
from hunter_market_worker.queues import PersistItem, PersistQueues

from . import builders
from .fakes import FakeRuntime

pytestmark = pytest.mark.unit


async def _run_drain_loop_until_flushed(
    monkeypatch: pytest.MonkeyPatch, *, interval_s: float
) -> tuple[float, float]:
    """Start ``drain_loop`` over a queue with one final candle already
    pending, wait for its (stubbed) flush, and return
    ``(enqueued_at, flushed_at)`` — both ``time.monotonic()``."""
    flushed_at: list[float] = []

    async def fake_flush_batch(
        factory: Any,
        exchange_code: str,
        batch: list[PersistItem],
        *,
        producer: str | None = None,
        market_type: MarketType | None = None,
    ) -> None:
        flushed_at.append(time.monotonic())

    monkeypatch.setattr(persist, "flush_batch", fake_flush_batch)
    monkeypatch.setattr(persist, "FLUSH_INTERVAL_S", interval_s)

    queues = PersistQueues()
    runtime = FakeRuntime()
    enqueued_at = time.monotonic()
    queues.events.put_nowait(builders.candle("BTCUSDT"))

    task = asyncio.create_task(persist.drain_loop(None, "binance", queues, runtime, None, "test"))
    try:
        await asyncio.wait_for(runtime.success.wait(), timeout=5.0)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert flushed_at, "flush_batch was never called"
    return enqueued_at, flushed_at[0]


async def test_final_candle_flushes_within_the_configured_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T3.81 fix: the production default (``MARKET_CANDLE_FLUSH_MS=200`` ->
    ``FLUSH_INTERVAL_S=0.2``) no longer forces a ~1s wait for a candle that is
    the only thing in the queue -- the old hardcoded 1.0s made this assertion
    fail (it would take ~1.0-1.1s)."""
    enqueued_at, flushed_at = await _run_drain_loop_until_flushed(monkeypatch, interval_s=0.2)
    lag = flushed_at - enqueued_at
    assert lag < 0.5, f"flush took {lag:.3f}s, expected well under the old 1.0s floor"


async def test_flush_window_is_still_honoured_not_instantaneous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window is a real batching wait, not zero: shrinking it must not
    turn every single event into its own transaction by accident. A generous
    lower bound (half the configured window) is enough to prove the wait is
    still there without pinning an exact number to asyncio's scheduling
    jitter."""
    enqueued_at, flushed_at = await _run_drain_loop_until_flushed(monkeypatch, interval_s=0.3)
    lag = flushed_at - enqueued_at
    assert lag >= 0.15, f"flush took only {lag:.3f}s, expected the ~0.3s window to be honoured"
