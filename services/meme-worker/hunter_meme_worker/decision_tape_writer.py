"""The decision tapes' write path (T4.89): a bounded in-memory buffer the
event lane offers to — O(1), no ``await``, never raises — and a background
flush (``event_gate._tape_flush_loop``) that writes it in batches.

**A decision never waits on this and never fails because of it.** The
proposal's own derived fields go into ``meme_proposals.reasons`` in the
proposal's transaction (that is the durable record); the raw tape slice is the
complement, and it is allowed to be lost — counted, never silently: a full
buffer drops the new tape (``dropped``), a failing ``INSERT`` loses its batch
(``failed``), a capture that raised is ``capture_failed``, a capture no
committed row explains is ``unlinked``, a sweep that failed is
``prune_failed`` (``last_prune_ok_at`` says when one last worked). All on the
``event_gate_tapes_*`` heartbeat fields. The buffer lives on the runtime, so a
gate restart keeps it; a process exit loses at most one flush cycle.

The retention sweep (:mod:`hunter_meme_worker.decision_tape_repo`) rides the
same loop once per UTC day — the ``lab_trail`` cadence for its own table.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Final

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.decision_tape_repo import insert_decision_tapes, prune_decision_tapes

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.decision_tape import DecisionTape

logger = get_logger(__name__)

__all__ = ["TAPE_BATCH", "TAPE_CAPACITY", "DecisionTapeWriter", "TapeRow"]

WORKER_ROLE: Final = "hunter_worker"
TAPE_CAPACITY: Final = 2000
"""Tapes held between two flushes, ceiling (~2 000 × ~12 KB ≈ 24 MB worst case)."""
TAPE_BATCH: Final = 200
PRUNE_BATCH: Final = 5000


@dataclass(frozen=True, slots=True)
class TapeRow:
    """One tape to write, with the proposals its instant inserted (committed)."""

    tape: DecisionTape
    proposal_ids: tuple[str, ...]


class DecisionTapeWriter:
    """Offer from the hot path; flush and prune from a background loop."""

    def __init__(self, *, capacity: int = TAPE_CAPACITY, batch: int = TAPE_BATCH) -> None:
        self.capacity = capacity
        self.batch = batch
        self._pending: deque[TapeRow] = deque()
        self.offered = 0
        self.written = 0
        self.dropped = 0
        self.failed = 0
        self.capture_failed = 0
        self.pruned = 0
        self.prune_failed = 0
        self.unlinked = 0
        self.last_prune_day: date | None = None
        self.last_prune_ok_at: datetime | None = None
        self._dropped_logged = 0

    @property
    def pending(self) -> int:
        return len(self._pending)

    def offer(self, tape: DecisionTape, *, proposal_ids: Sequence[str]) -> bool:
        """``False`` (and counted) when the buffer is full — never blocks."""
        self.offered += 1
        if len(self._pending) >= self.capacity:
            self.dropped += 1
            return False
        self._pending.append(TapeRow(tape, tuple(proposal_ids)))
        return True

    def record_capture_failed(self) -> None:
        self.capture_failed += 1

    def record_unlinked(self) -> None:
        self.unlinked += 1

    async def flush(self, session_factory: async_sessionmaker[AsyncSession]) -> int:
        """Write one batch; the rows inserted. Never raises (but cancels)."""
        if self.dropped > self._dropped_logged:
            logger.warning(
                "meme_decision_tape_dropped",
                dropped=self.dropped - self._dropped_logged,
                capacity=self.capacity,
            )
            self._dropped_logged = self.dropped
        if not self._pending:
            return 0
        rows = [self._pending.popleft() for _ in range(min(self.batch, len(self._pending)))]
        try:
            async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                inserted = await insert_decision_tapes(session, rows)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the tape is evidence, never a reason to stop the gate
            self.failed += len(rows)
            logger.warning(
                "meme_decision_tape_write_failed",
                rows=len(rows),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return 0
        self.written += inserted
        return inserted

    def prune_due(self, now: datetime) -> bool:
        return self.last_prune_day != now.date()

    async def maybe_prune(
        self, session_factory: async_sessionmaker[AsyncSession], now: datetime
    ) -> int:
        """Once per UTC day, in batches; never raises (but cancels). A failed
        sweep waits for the next day too — never a retry (and a log line)
        every flush cycle through an outage."""
        if not self.prune_due(now):
            return 0
        self.last_prune_day = now.date()
        total = 0
        try:
            while True:
                async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                    deleted = await prune_decision_tapes(session, now=now, batch=PRUNE_BATCH)
                total += deleted
                if deleted < PRUNE_BATCH:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.prune_failed += 1
            logger.warning(
                "meme_decision_tape_prune_failed", error_type=type(exc).__name__, error=str(exc)
            )
            return total
        self.pruned += total
        self.last_prune_ok_at = now
        if total:
            logger.info("meme_decision_tapes_pruned", rows=total)
        return total

    def heartbeat_fields(self) -> dict[str, str]:
        return {
            "event_gate_tapes_offered": str(self.offered),
            "event_gate_tapes_written": str(self.written),
            "event_gate_tapes_dropped": str(self.dropped),
            "event_gate_tapes_failed": str(self.failed),
            "event_gate_tapes_capture_failed": str(self.capture_failed),
            "event_gate_tapes_pending": str(len(self._pending)),
            "event_gate_tapes_pruned": str(self.pruned),
            "event_gate_tapes_prune_failed": str(self.prune_failed),
            "event_gate_tapes_last_prune_ok_at": (
                "" if self.last_prune_ok_at is None else self.last_prune_ok_at.isoformat()
            ),
            "event_gate_tapes_unlinked": str(self.unlinked),
        }
