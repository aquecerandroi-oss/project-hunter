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

``enqueued``/``evicted`` (T2.5-adapter, Astra diff review finding 1): three
monotonic counters — ``enqueued`` here, ``evicted`` here, ``delivered`` on
:class:`StreamConsumer` — let a consumer outside this package (the
market-worker's ``CoverageTracker``) tell "queue empty" from "caught up".
Plain queue length cannot: an item :meth:`get` has already popped is no
longer in the deque, but is not delivered until it is actually yielded, so
length alone reads "0" during exactly the window a naive check would miss.
``enqueued == delivered + evicted`` is the honest form (Astra review,
finding 3): an evicted item is gone for good and must not count against
"caught up" forever after the one legitimate break its eviction already
causes via ``dropped_events``. An event dropped *before* it ever entered the
queue (the incoming-item-dropped branch of :meth:`put`) increments neither
counter — it never reached ``enqueued`` on either side of the ledger, and
its loss is already reported through ``dropped_events``.
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
    """FIFO of ``(connection_key, event)`` pairs capped at ``maxsize``.

    T1.6b-A (ACHADO-1, ``.claude/state/t16b-profile.md``): the previous
    ``_evict_one`` linear-scanned the whole deque from index 0 on *every*
    ``put`` while full (``isinstance`` + attribute access per item via
    ``enumerate()``, then an indexed ``del``) — 17.8% of one core at 200
    markets, self-reinforcing because a saturated queue makes ``put``
    saturated too. ``_final_count`` tracks how many of the currently queued
    items are final klines, so the common case (the head is not final —
    finals are rare, everything else is not) evicts in O(1): one tuple
    unpack, one ``isinstance`` check, ``popleft()``. The full scan only ever
    runs in the rare case where the head *is* a queued final but a later
    item is not (never when every item is final — that path already goes
    through the backpressure branch below instead).
    """

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._items: deque[tuple[str, NormalizedEvent]] = deque()
        self._final_count = 0
        self._not_empty = asyncio.Event()
        self._has_room = asyncio.Event()
        self._has_room.set()
        self.enqueued = 0
        """Count of items that actually entered the queue (``append``
        succeeded) since this queue was created. Never counts an incoming
        event dropped before entry (that loss is ``dropped_events``, not a
        queue-progress fact)."""
        self.evicted = 0
        """Count of previously-enqueued items removed by :meth:`_evict_one`
        to make room — gone for good, and excluded from ``enqueued`` on the
        "caught up" side of the ledger together with :attr:`StreamConsumer.delivered`."""

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
        self.enqueued += 1
        if _is_final_kline(event):
            self._final_count += 1
        self._not_empty.set()

    def _evict_one(self, states: dict[str, ConnectionState]) -> bool:
        if not self._items:
            return False
        head_key, head_event = self._items[0]
        if not _is_final_kline(head_event):
            # Common case, O(1): the head is (almost always) not a final
            # kline, so evict it directly with no scan at all.
            self._items.popleft()
            self.evicted += 1
            if head_key in states:
                states[head_key].dropped_events += 1
            return True
        if self._final_count == len(self._items):
            return False  # every queued item is a final kline: cannot evict
        # Rare fallback: the head happens to be a queued final but a later
        # item is not. O(n) here, but never on the hot path above.
        for index, (victim_key, victim_event) in enumerate(self._items):
            if not _is_final_kline(victim_event):
                del self._items[index]
                self.evicted += 1
                if victim_key in states:
                    states[victim_key].dropped_events += 1
                return True
        return False  # pragma: no cover — unreachable given the count check above

    async def get(self) -> NormalizedEvent:
        while not self._items:
            self._not_empty.clear()
            await self._not_empty.wait()
        _, event = self._items.popleft()
        if _is_final_kline(event):
            self._final_count -= 1
        self._has_room.set()
        return event

    def __len__(self) -> int:
        return len(self._items)

    def progress(self) -> tuple[int, int]:
        """``(enqueued, evicted)`` since this queue was created — the two
        counters :class:`StreamConsumer` combines with its own ``delivered``
        to answer "caught up?" without trusting queue length (see module
        docstring)."""
        return self.enqueued, self.evicted


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
        self.delivered = 0
        """Count of items actually yielded from :meth:`consume` — incremented
        with no ``await`` between the increment and the ``yield`` (Astra
        review, T2.5-adapter finding 3), so it never lags an item that
        :meth:`BoundedEventQueue.get` has already popped but this generator
        has not yet handed to its caller."""

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
                    result = get_task.result()
                    self.delivered += 1
                    get_task = None
                    yield result
        finally:
            for pending in (get_task, fail_task):
                if pending is not None:
                    pending.cancel()
            for pending in (get_task, fail_task):
                if pending is not None:
                    with contextlib.suppress(asyncio.CancelledError):
                        await pending
            await on_close()
