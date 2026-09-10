"""Bounded concurrent dispatch of independent bars, serial per market (T3.74c).

**The measured problem.** ``run_consumer`` used to ``await handle_candle(...)``
for one closed candle, then read the next -- strictly serial, one market at a
time, even though ``market.candles.closed`` delivers roughly the whole
monitored universe (~200 perpetuals) within the same few seconds every minute
(every symbol's own 1m bar closes near :00). Measured live on the VPS
(2026-09-10 15:01Z, read-only): ``hunter-strategy-worker-1`` spiking to 92.7 %
of one core during that burst while its own consumer group had fallen behind
the stream by 303 unread entries (``XINFO GROUPS market.candles.closed``) --
the process cannot even *read* the next candle until it finishes the one it is
holding. ``notes-T3.74b.md`` §1.3 saw the same shape from the other side: one
logical bar (``bar_close = 05:45:00Z``) produced signals between 36.7 s and
185.0 s of lag -- not one slow event, a queue draining in place.

**Why concurrency, not just the T3.74b cache.** Different markets never share
a session, a slot row (:mod:`hunter_strategy_worker.slots` locks by
``(strategy_version_id, market_id, cohort)``) or a candle window -- handling
them concurrently changes nothing about *what* is decided, only *when* the
worker gets to each one. The T3.74b family cache cut candle reads 5.5x for
versions sharing a market and a bar; it does nothing for the cost of the
burst *itself*, which is one market's worth of that (now cheaper) work,
repeated ~200 times, one at a time.

**What must stay serial.** Two bars of the *same* market must still be
handled in the order they were read: a redelivery after a crash, or a
consumer restart mid-burst, could otherwise let a later bar's slot transition
run before an earlier one's, and ``slots.lock_slot``'s barrier is defined
against the bar it last saw, not against wall-clock arrival order. This module
serialises per market key (:func:`market_key`) while parallelising across
markets, bounded by a semaphore so the process never holds more DB sessions at
once than the pool has to give (``ShadowConfig.worker_concurrency``,
docstring there for the pool arithmetic).

**The feedback loop this module also guards against (T3.74d code review,
HIGH).** A bar accepted here can sit queued behind the semaphore or a busy
market lock for longer than :mod:`hunter_core.events.consume`'s own
``claim_idle_ms`` (``ShadowConfig.claim_idle_ms``, docstring there for the
arithmetic and the bound) -- at which point ``XAUTOCLAIM`` reclaims and
redelivers the *same* stream entry to this *same* consumer, which is still
holding it. Before this fix ``run_consumer`` would submit that redelivery a
second time, doubling work exactly during the burst this module exists to
absorb. :meth:`BarDispatcher.submit` now tracks every message id it has
accepted but not yet finished (queued *or* running) and refuses a repeat,
counted by name
(``hunter_shadow_bars_skipped_total{reason="already_in_flight"}``) so the
refusal is visible, not silent.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger
from hunter_strategy_worker.metrics import shadow_bars_skipped_total

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

logger = get_logger(__name__)

__all__ = ["BarDispatcher", "market_key"]


def market_key(payload: Mapping[str, object]) -> str:
    """A stable per-market identity straight off the wire payload.

    Read without decoding the candle into a domain object -- cheap on
    purpose, the same spirit as the ``market_type`` refusal at the door
    (T3.73). A payload missing a field collapses onto a shared ``"?"`` slot
    rather than raising: this key only has to serialise bars that share a
    market, and ``handle_candle`` itself already logs and drops a payload it
    cannot parse at all.
    """
    exchange = payload.get("exchange", "?")
    symbol = payload.get("symbol", "?")
    kind = payload.get("market_type", "?")
    return f"{exchange}:{symbol}:{kind}"


class BarDispatcher:
    """Runs handlers for distinct markets concurrently, one market at a time.

    ``concurrency`` bounds how many handlers may be *running* at once: the
    semaphore is acquired by the caller in :meth:`submit`, before the
    background task even exists, so a full dispatcher applies backpressure on
    the stream reader itself (the next ``XREADGROUP`` simply waits) instead of
    growing an unbounded queue of accepted-but-not-started work. A market's
    own lock is acquired *inside* the task, after the semaphore, so a burst
    that happens to repeat a market waits in line for that market specifically
    without holding the semaphore slot other, unrelated markets are waiting on.
    """

    def __init__(self, concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._in_flight: set[str] = set()

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def submit(
        self, key: str, message_id: str, handler: Callable[[], Awaitable[None]]
    ) -> None:
        """Block until a concurrency slot is free, then run ``handler`` in the
        background, serialised against any other bar already queued for the
        same ``key`` -- unless ``message_id`` is already queued or running, in
        which case this is a redelivery of a bar this dispatcher already
        accepted (T3.74d, module docstring) and is refused instead of run a
        second time.

        ``message_id`` is checked and recorded *before* the semaphore wait, so
        a message queued behind a full dispatcher (not yet running) is also
        covered, not only one whose handler already started.

        Never raises what ``handler`` raises -- the caller has already moved
        on to the next message by the time it runs. A handler that must
        report its own failure (as ``handle_candle`` does today, via
        ``ConsumerHealth``/``runtime.mark_error``) does so itself.
        """
        if message_id in self._in_flight:
            shadow_bars_skipped_total.labels(reason="already_in_flight").inc()
            logger.warning("shadow_dispatch_already_in_flight", key=key, message_id=message_id)
            return
        self._in_flight.add(message_id)
        await self._semaphore.acquire()

        async def _run() -> None:
            try:
                async with self._lock_for(key):
                    await handler()
            except Exception:
                logger.exception("shadow_dispatch_handler_failed", key=key)
            finally:
                self._semaphore.release()
                self._tasks.discard(task)
                self._in_flight.discard(message_id)

        task = asyncio.ensure_future(_run())
        self._tasks.add(task)

    async def drain(self) -> None:
        """Wait for every handler already accepted to finish.

        Called on a clean stream-ended backoff and on shutdown; the live loop
        never calls it mid-stream (that would defeat the whole point).
        """
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def cancel_all(self) -> None:
        """Cancel every in-flight handler and wait for the cancellation to
        land. Used only when the worker itself is being cancelled -- a
        background task ``ensure_future`` created is not cancelled just
        because its creator was."""
        for task in list(self._tasks):
            task.cancel()
        await self.drain()
