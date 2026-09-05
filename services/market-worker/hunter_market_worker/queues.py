"""Bounded persistence buffering with explicit recoverable/irrecoverable losses."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import orjson
from prometheus_client import Counter

from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedFunding,
    NormalizedLiquidation,
    NormalizedOpenInterest,
    to_wire,
)
from hunter_core.logging import get_logger
from hunter_core.observability import market_persistence_loss_reports_dropped_total, registry

logger = get_logger(__name__)

losses_total = Counter(
    "market_persistence_drops_total",
    "Dropped queued market events.",
    ["kind", "reason"],
    registry=registry,
)


class RealizedFunding(NormalizedFunding):
    """Verified settlement from REST, with funding_time carried in ts."""


@dataclass
class Snapshot:
    symbol: str
    values: dict[str, Any]
    kind: str = "snapshot"


@dataclass
class OpenInterestSample:
    """One REST open-interest reading plus the bucket of the polling round it
    belongs to (D8).

    ``main.py`` always passes ``queues``, so this wrapper is the production
    path: without it ``upsert_open_interest`` re-derives the 5-minute bucket
    from each reading's own ``ts`` and a round of 200 markets that straddles a
    boundary splits across two buckets, with the split moving every cycle. The
    WS path (``ingest.py``) has no round and keeps enqueueing the bare
    ``NormalizedOpenInterest``.
    """

    reading: NormalizedOpenInterest
    bucket_ts: datetime
    kind: str = "open_interest"

    @property
    def symbol(self) -> str:
        return self.reading.symbol


PersistItem = (
    NormalizedCandle
    | NormalizedFunding
    | NormalizedLiquidation
    | NormalizedOpenInterest
    | OpenInterestSample
    | Snapshot
)


def item_bytes(item: PersistItem) -> int:
    if isinstance(item, Snapshot):
        payload: Any = item.values
    elif isinstance(item, OpenInterestSample):
        payload = to_wire(item.reading)
    else:
        payload = to_wire(item)
    return len(orjson.dumps(payload, default=str))


@dataclass
class Pending:
    item: PersistItem
    size: int
    at: float


@dataclass
class Loss:
    item: PersistItem
    reason: str


class BoundedEvents:
    def __init__(self, owner: PersistQueues) -> None:
        self.owner = owner
        self.items: deque[Pending] = deque()
        self.bytes = 0
        self.last_taken_at = owner.clock()
        self.available = asyncio.Event()

    def qsize(self) -> int:
        return len(self.items)

    def empty(self) -> bool:
        return not self.items

    def put_nowait(self, item: PersistItem) -> None:
        now = self.owner.clock()
        while self.items and now - self.items[0].at > self.owner.max_age:
            self.owner.drop(self.get_nowait(), "age")
        if isinstance(item, Snapshot):
            for previous in list(self.items):
                if isinstance(previous.item, Snapshot) and previous.item.symbol == item.symbol:
                    self.items.remove(previous)
                    self.bytes -= previous.size
                    self.owner.drop(previous.item, "replaced")
                    break
        size = item_bytes(item)
        if len(self.items) >= self.owner.max_items or self.bytes + size > self.owner.max_bytes:
            self.owner.drop(item, "capacity")
            return
        if not self.items and not self.owner.in_flight:
            self.owner.pending_since = now
        self.items.append(Pending(item, size, now))
        self.bytes += size
        self.available.set()

    def get_nowait(self) -> PersistItem:
        if not self.items:
            raise asyncio.QueueEmpty
        pending = self.items.popleft()
        self.last_taken_at = pending.at
        self.bytes -= pending.size
        if not self.items:
            self.available.clear()
        return pending.item

    async def get(self) -> PersistItem:
        while not self.items:
            await self.available.wait()
        return self.get_nowait()


class PersistQueues:
    def __init__(
        self,
        *,
        max_items: int = 5000,
        max_bytes: int = 8 * 1024 * 1024,
        max_age: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_items, self.max_bytes, self.max_age = max_items, max_bytes, max_age
        self.clock = clock
        self.pending_since = self.last_flush = clock()
        self.in_flight = False
        self.losses: deque[Loss] = deque(maxlen=max_items)
        self.events = BoundedEvents(self)

    def drop(self, item: PersistItem, reason: str) -> None:
        """Record a dropped item. Never raises (D2): losing the *report* of a
        loss must never be worse than the loss itself — a full ``losses``
        deque evicts its oldest entry (``maxlen``) instead of blowing up the
        caller, which would otherwise be the ingest path itself."""
        losses_total.labels(kind=item.kind, reason=reason).inc()
        if len(self.losses) == self.losses.maxlen:
            market_persistence_loss_reports_dropped_total.inc()
            logger.warning("market_loss_report_queue_full", max_items=self.max_items)
        self.losses.append(Loss(item, reason))

    async def persistence(self) -> bool:
        pending = self.in_flight or bool(self.losses) or not self.events.empty()
        return not pending or self.clock() - max(self.last_flush, self.pending_since) < 30
