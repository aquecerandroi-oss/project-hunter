"""The bounded queue of the durable cycle history and its counters.

Split from :mod:`hunter_meme_worker.cycle_history` (350-line budget): this is the
in-memory half (what the loops hand over, never waiting), that module is the
database half (the writer and the reader's query). Both are re-exported there.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from itertools import islice

from hunter_meme_worker.cycle_metrics import CycleMeter, CycleSample

__all__ = ["CAPACITY", "EVENT_CYCLE", "EVENT_END", "EVENT_START", "CycleHistory", "HistoryRow"]

EVENT_CYCLE = "cycle"
EVENT_START = "generation_start"
EVENT_END = "generation_end"
CAPACITY = 4096
"""About 13 hours of both loops together (5 cycles a minute); a database outage
longer than that opens a declared hole, not an ever-growing backlog."""


@dataclass(frozen=True, slots=True)
class HistoryRow:
    event: str
    data: dict[str, object]


class CycleHistory:
    """The bounded queue between the loops and the writer, and its counters."""

    def __init__(self, capacity: int = CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1 sample")
        self._queue: deque[tuple[int, HistoryRow]] = deque(maxlen=capacity)
        self._next_token = 0
        self.written_total = 0
        self.failed_total = 0
        self.dropped_total = 0
        self.abandoned_total = 0
        self.inflight: asyncio.Future[None] | None = None
        self.published: tuple[int, int, int, int] | None = None

    def add(self, row: HistoryRow) -> None:
        """Queue one row without waiting; at capacity the oldest is dropped."""
        if len(self._queue) == self._queue.maxlen:
            self.dropped_total += 1
        self._next_token += 1
        self._queue.append((self._next_token, row))

    def offer(self, sample: CycleSample) -> None:
        """The ``timed_step`` hook: one ``cycle`` row per completed cycle."""
        self.add(
            HistoryRow(
                EVENT_CYCLE,
                {
                    "loop": sample.loop,
                    "run_id": sample.run_id,
                    "seq": sample.seq,
                    "ended_at": sample.ended_at.isoformat(),
                    "duration_ms": sample.duration_ms,
                },
            )
        )

    def mark_start(self, meter: CycleMeter) -> None:
        """The generation's birth certificate — also for a loop that is switched off."""
        self.add(
            HistoryRow(
                EVENT_START,
                {
                    "loop": meter.loop,
                    "run_id": meter.run_id,
                    "started_at": meter.started_at.isoformat(),
                    "enabled": meter.enabled,
                    "nominal_ms": meter.nominal_ms,
                    "window": meter.window,
                },
            )
        )

    def mark_end(self, meter: CycleMeter, at: datetime, *, clean: bool) -> None:
        """The generation's final totals and how it ended: ``clean`` is false when a
        loop crashed. (Its absence means the ending is unproven, not that it crashed.)"""
        self.add(
            HistoryRow(
                EVENT_END,
                {
                    "loop": meter.loop,
                    "run_id": meter.run_id,
                    "ended_at": at.isoformat(),
                    "cycles_total": meter.cycles_total,
                    "overruns_total": meter.overruns_total,
                    "clean": clean,
                },
            )
        )

    @property
    def queued(self) -> int:
        return len(self._queue)

    def peek(self, limit: int) -> list[tuple[int, HistoryRow]]:
        """Up to ``limit`` oldest rows with their tokens, left in the queue."""
        return list(islice(self._queue, limit))

    def acknowledge(self, token: int) -> None:
        """Remove every row up to ``token`` (what a written batch contained)."""
        while self._queue and self._queue[0][0] <= token:
            self._queue.popleft()

    @property
    def writing(self) -> bool:
        """A write is still in flight (an abandoned one that has not ended counts)."""
        return self.inflight is not None and not self.inflight.done()

    def counters(self) -> tuple[int, int, int, int]:
        return (self.written_total, self.failed_total, self.dropped_total, self.abandoned_total)

    def fields(self) -> dict[str, str]:
        return {
            "cycle_history_written_total": str(self.written_total),
            "cycle_history_failed_total": str(self.failed_total),
            "cycle_history_dropped_total": str(self.dropped_total),
            "cycle_history_abandoned_total": str(self.abandoned_total),
            "cycle_history_queued": str(self.queued),
        }
