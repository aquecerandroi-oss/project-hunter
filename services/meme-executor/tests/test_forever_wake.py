"""T4.52a: ``forever``'s ``wake_event`` — early wake, and the timer as a
genuine fallback when nothing ever sets it.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from hunter_meme_executor.main import forever

pytestmark = pytest.mark.unit


async def test_wake_event_makes_the_next_step_run_before_the_interval_elapses() -> None:
    calls: list[float] = []
    event = asyncio.Event()
    loop = asyncio.get_running_loop()

    async def step(_ctx: None) -> None:
        calls.append(loop.time())

    task = asyncio.ensure_future(forever("t", 10.0, step, None, wake_event=event))
    await asyncio.sleep(0.01)  # first step ran
    assert len(calls) == 1
    event.set()
    await asyncio.sleep(0.05)  # woken well inside the 10s interval, not after it
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert len(calls) == 2
    assert calls[1] - calls[0] < 1.0


async def test_fallback_timer_still_fires_when_the_event_is_never_set() -> None:
    calls: list[float] = []

    async def step(_ctx: None) -> None:
        calls.append(0.0)

    event = asyncio.Event()
    task = asyncio.ensure_future(forever("t", 0.05, step, None, wake_event=event))
    await asyncio.sleep(0.25)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert len(calls) >= 3  # ~5 ticks in 0.25s at a 0.05s fallback, never zero


async def test_event_is_cleared_after_waking_so_a_stale_set_does_not_spin() -> None:
    """A pre-set event runs the very next step once (no timeout to wait out),
    then it is cleared — the loop does not spin forever on one stale ``set()``.
    """
    calls: list[float] = []
    event = asyncio.Event()
    event.set()  # already set before the loop starts

    async def step(_ctx: None) -> None:
        calls.append(0.0)

    task = asyncio.ensure_future(forever("t", 10.0, step, None, wake_event=event))
    await asyncio.sleep(0.05)
    assert len(calls) == 2  # the first tick, plus one because the event was already set
    assert not event.is_set()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
