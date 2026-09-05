"""Bounded event queue between WS reader tasks and :meth:`BinanceWsClient.stream`.

``docs/plans/M1.md`` T1.2b: several reader tasks (one per connection) feed a
single queue the consumer (the market-worker) drains from. Left unbounded, a
slow/blocked consumer lets that queue grow without limit (Astra review,
T1.2 resume, finding 5). On overflow the oldest already-queued entry that is
*not* a final kline is dropped, and the drop is counted on the connection it
came from (:attr:`~hunter_exchanges.base.ConnectionState.dropped_events`) —
a final kline is never the eviction victim. When every already-queued entry
*and* the incoming one are final klines (none may be dropped), :meth:`put`
applies real backpressure instead: it awaits until :meth:`get` frees a slot,
so the queue's size never exceeds ``maxsize`` either way (Astra review,
T1.2b resume finding 4: an unconditional "let it grow" here reproduces the
exact unbounded-memory failure the bound exists to prevent).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable

from hunter_core.domain.market import NormalizedCandle, NormalizedEvent
from hunter_exchanges.base import ConnectionState

DEFAULT_MAXSIZE = 10_000


def _is_final_kline(event: NormalizedEvent) -> bool:
    return isinstance(event, NormalizedCandle) and event.is_final


class BoundedEventQueue:
    """FIFO of ``(connection_key, event)`` pairs capped at ``maxsize``."""

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._items: deque[tuple[str, NormalizedEvent]] = deque()
        self._not_empty = asyncio.Event()
        self._has_room = asyncio.Event()
        self._has_room.set()

    async def put(
        self, key: str, event: NormalizedEvent, states: dict[str, ConnectionState]
    ) -> None:
        while len(self._items) >= self._maxsize:
            if self._evict_one(states):
                break
            if not _is_final_kline(event):
                # Queue saturated with only finals; the incoming event is
                # the one dropped (never a final kline, and never a queued
                # final either).
                if key in states:
                    states[key].dropped_events += 1
                return
            # Both the queue and the incoming event are final klines: never
            # drop either. Wait for the consumer to free a slot instead of
            # growing past maxsize.
            self._has_room.clear()
            await self._has_room.wait()
        self._items.append((key, event))
        self._not_empty.set()

    def _evict_one(self, states: dict[str, ConnectionState]) -> bool:
        for index, (victim_key, victim_event) in enumerate(self._items):
            if not _is_final_kline(victim_event):
                del self._items[index]
                if victim_key in states:
                    states[victim_key].dropped_events += 1
                return True
        return False

    async def get(self) -> NormalizedEvent:
        while not self._items:
            self._not_empty.clear()
            await self._not_empty.wait()
        _, event = self._items.popleft()
        self._has_room.set()
        return event

    def __len__(self) -> int:
        return len(self._items)


class StreamConsumer:
    """Bridges N reader tasks (one per connection) into one ``AsyncIterator``.

    Owns the bounded queue and the "did any reader task die" signal
    (:meth:`on_task_done`, meant as an ``asyncio.Task.add_done_callback``);
    :meth:`consume` races the two and re-raises a reader's terminal failure
    to :meth:`~hunter_exchanges.binance.ws.BinanceWsClient.stream`'s consumer
    instead of hanging it silently (T1.2b).
    """

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        self.queue = BoundedEventQueue(maxsize)
        self._failure: BaseException | None = None
        self._failure_event = asyncio.Event()

    async def put(
        self, key: str, event: NormalizedEvent, states: dict[str, ConnectionState]
    ) -> None:
        await self.queue.put(key, event, states)

    def on_task_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None and self._failure is None:
            self._failure = exc
            self._failure_event.set()

    async def consume(
        self, on_close: Callable[[], Awaitable[None]]
    ) -> AsyncIterator[NormalizedEvent]:
        get_task: asyncio.Task[NormalizedEvent] | None = None
        fail_task: asyncio.Task[bool] | None = None
        try:
            while True:
                if get_task is None:
                    get_task = asyncio.ensure_future(self.queue.get())
                if fail_task is None:
                    fail_task = asyncio.ensure_future(self._failure_event.wait())
                done, _ = await asyncio.wait(
                    {get_task, fail_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if fail_task in done:
                    get_task.cancel()
                    assert self._failure is not None
                    raise self._failure
                if get_task in done:
                    yield get_task.result()
                    get_task = None
        finally:
            for pending in (get_task, fail_task):
                if pending is not None:
                    pending.cancel()
            for pending in (get_task, fail_task):
                if pending is not None:
                    with contextlib.suppress(asyncio.CancelledError):
                        await pending
            await on_close()
