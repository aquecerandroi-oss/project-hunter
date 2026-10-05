"""One owner for the sequence *mutation -> persistence*.

The scanner's collectors forget an episode's id **before** the commit
(``collect.py:166``, ``watchdog.py:115``). That is only safe if a batch that failed
to commit is *kept*: the old loops answered any exception with ``batch =
WriteBatch()``, so one transient error erased the ``EXPIRE``/``RESOLVE`` of a market
whose memory had already moved on, the next episode opened under a new id against a
row the database still held open, and a unique index vetoed every later batch for
good -- 14 h on 30/09 and 2.5 days from 02/10 (``obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md``).

The lane makes three things true:

- **one batch, one lock.** The evaluation cycle and the watchdog append to
  ``lane.batch`` and flush it under ``lane.lock``, which each of them holds from the
  first mutation to the end of the flush. Nothing is appended while a flush is in
  flight, and a second flush can never overtake the first;
- **a failed flush keeps everything**: rows, events (same ``event_id`` on the retry,
  which the outbox deduplicates), ACKs and post-commit callbacks stay in the batch,
  in the order they were collected -- the older work is always ahead of the newer;
- **retention is bounded, and the bound fails loud.** Past ``max_retain_s`` of
  uninterrupted failure the lane is *blocked*: ``/ready`` goes red at once, one
  CRITICAL line says what is held, and the loops stop producing new transitions
  (the batch cannot grow) while the lane keeps retrying with a back-off. Nothing is
  dropped silently; a restart is the explicit way out and rehydrates from the table.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker.persist import WriteBatch, flush_batch

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_scanner_worker.cycle_health import CycleHealth

logger = get_logger(__name__)

RETAIN_MAX_AGE_S = 60.0
"""How long a failing batch is retried before the lane blocks. A retained batch
grows by up to ~200 snapshot rows a second (the same minute is rebuilt until it
commits), so a minute bounds it to ~12 k rows -- tens of MB -- while being far
longer than a Postgres restart."""

BLOCKED_BACKOFF_S = 5.0

__all__ = ["BLOCKED_BACKOFF_S", "RETAIN_MAX_AGE_S", "FlushLane"]


class FlushLane:
    """The batch both writers append to, the lock that serialises them, the flush."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        redis: redis_asyncio.Redis,
        cycle: CycleHealth,
        *,
        max_retain_s: float = RETAIN_MAX_AGE_S,
    ) -> None:
        self.factory = factory
        self.redis = redis
        self.cycle = cycle
        self.max_retain_s = max_retain_s
        self.batch = WriteBatch()
        self.lock = asyncio.Lock()
        self.invalidated: set[UUID] = set()
        """Markets whose rows were dropped at flush time (baseline vanished) and whose
        memory still has to be reloaded from the table (``rehydrate.resync_invalidated``)."""

        self.retained_since: datetime | None = None

    @property
    def blocked(self) -> bool:
        return self.cycle.blocked

    async def flush(self, *, now: datetime | None = None) -> bool:
        """Commit ``self.batch``; the caller holds ``self.lock``.

        ``True``: nothing is left behind (a fresh batch). ``False``: the flush failed
        and the batch is **kept** whole for the next attempt; the failure is already
        recorded in ``cycle`` (log line, streak, ``/ready``).
        """
        if self.batch.empty and not self.batch.acks:
            # Nothing is retained, so nothing is at risk: whatever failed (a flush, or
            # an evaluation that collected nothing) has no rows left to lose.
            self.retained_since = None
            self.cycle.recovered()
            return True
        wrote = not self.batch.empty  # an empty or ACK-only flush proves nothing
        try:
            invalidated = await flush_batch(self.factory, self.redis, self.batch, now=now)
        except Exception as error:
            self.invalidated |= self.batch.invalidated
            self._failed(error)
            return False
        self.batch = WriteBatch()
        self.invalidated |= invalidated
        self.retained_since = None
        self.cycle.blocked = False
        if wrote:
            self.cycle.committed()
        return True

    def failed(self, error: BaseException) -> None:
        """Record a failure of the cycle that is *not* a flush (an evaluation, a resync).

        It counts toward the retention bound like a failed flush: an evaluation that
        raises every cycle after collecting rows never reaches the flush, and without
        this the batch it keeps would grow for as long as the failure lasts.
        """
        self._failed(error)

    def _failed(self, error: BaseException) -> None:
        self.cycle.failed(error)
        moment = utcnow()
        if self.retained_since is None:
            self.retained_since = moment
        held = (moment - self.retained_since).total_seconds()
        if held > self.max_retain_s and not self.cycle.blocked:
            self.cycle.blocked = True
            logger.critical(
                "scanner_flush_blocked",
                held_s=int(held),
                snapshots=len(self.batch.snapshots),
                anomalies=len(self.batch.anomalies),
                opportunities=len(self.batch.opportunities),
                events=len(self.batch.events),
                acks=len(self.batch.acks),
                action=(
                    "evaluation paused, batch kept and retried every "
                    f"{BLOCKED_BACKOFF_S:.0f}s; a restart rehydrates from the database "
                    "and drops it"
                ),
            )
