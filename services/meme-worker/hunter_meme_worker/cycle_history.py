"""The durable history of cycle times — ``system_events`` rows, no migration.

EXP-M26 §6.8's "before vs after" needs every individual cycle of the chain loop
and of the Lab loop, not the rolling p95 of ``hb:meme:radar`` (a restart zeroes it
and a p95 of p95s is not a p95 of cycles). ``system_events`` already exists, is
append-only, takes ``INSERT`` from ``hunter_worker`` and is not a tenant table (no
``organization_id``, no RLS). Retention is **30 days** (``docs/DATABASE.md`` §1.3),
by whole monthly partitions: a "before" baseline or an experiment window must be
exported and frozen before it expires.

``component = 'meme-worker'``, ``level = 'info'``, three events:

``cycle``             ``{loop, run_id, seq, ended_at, duration_ms}`` — one per completed
                      cycle; ``seq`` is the meter's ``cycles_total`` inside its ``run_id``.
``generation_start``  ``{loop, run_id, started_at, enabled, nominal_ms, window}`` — at every
                      boot, for **both** loops, enabled or not: a loop that is off leaves
                      this row and no cycles, which is how an absence is explained.
``generation_end``    ``{loop, run_id, ended_at, cycles_total, overruns_total, clean}`` — at
                      shutdown, when the queue still reaches the database. ``clean`` is
                      ``true`` for a SIGTERM (a cancel) and ``false`` when a loop crashed
                      and took the process down. A generation **without** a
                      ``generation_end`` has an *unproven* ending (a hard kill, a crash
                      before the closing, or a shutdown with the database down — the queue
                      died with the process): its tail is unknown, so coverage is provable
                      only up to the last contiguous ``seq``, and a gap *inside* a
                      ``run_id`` is a declared hole.

**Uniqueness is not promised by the table.** A COMMIT applied whose confirmation is
lost (or a write abandoned at its budget that still commits) makes the writer retry the
batch, so a row can exist twice (another ``id``, another ``created_at``). The reader's
contract is therefore **identity = ``(loop, run_id, seq)``** for ``cycle`` and
**``(event, loop, run_id)``** for ``generation_*``, deduplicated before any percentile
(``CYCLES_SINCE_SQL`` does it for cycles), with windows cut by ``data->>'ended_at'`` —
never by ``created_at``, which is the instant of persistence and moves while the database
is down — and never ordered by it either: a batch is one transaction, so its rows share
one ``created_at``; order by ``(loop, run_id, seq)``.

**Never blocks a loop.** ``offer`` is synchronous and O(1) into a bounded queue; when
it is full the *oldest* row is dropped and counted (``dropped_total`` — an upper
bound of what was lost: a dropped row may still be in a batch that was written). A
separate task (``CycleInstruments.supervised`` runs it, in both the enabled and the disabled
radar, and restarts it after an unexpected exception: flush, *then* sleep ``FLUSH_EVERY_S``) writes batches in
one transaction as ``hunter_worker`` under one budget for the whole flush (database and
counter publication together); a failed or timed-out write keeps the rows for the next
try (``failed_total``). **The budget is a hard bound**: the write runs in its own task
that the flush *abandons* when the budget ends (``abandoned_total``) — ``asyncio.timeout``
would wait for the cancelled write to finish, and a hung peer can take minutes
(``asyncpg``'s out-of-band cancel has no deadline). At most one write is ever in flight:
while an abandoned one is still stuck no second connection is checked out. Only what a
batch contained is removed after it was written — a row offered during the write is
never acknowledged by it. At shutdown :func:`drain` writes until the queue is empty, a
write fails or its budget ends.

Counters published on ``hb:meme:radar`` (only when they change)::

    cycle_history_written_total / _failed_total / _dropped_total / _abandoned_total / _queued
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.cycle_metrics import CyclePublisher, CycleSample
from hunter_meme_worker.cycle_queue import (
    CAPACITY,
    EVENT_CYCLE,
    EVENT_END,
    EVENT_START,
    CycleHistory,
    HistoryRow,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

__all__ = [
    "CAPACITY",
    "CYCLES_SINCE_SQL",
    "EVENT_CYCLE",
    "EVENT_END",
    "EVENT_START",
    "FLUSH_EVERY_S",
    "CycleHistory",
    "CycleSample",
    "HistoryRow",
    "drain",
    "flush_once",
    "publish_counters",
]

WORKER_ROLE = "hunter_worker"
COMPONENT = "meme-worker"
BATCH = 500
FLUSH_EVERY_S = 5.0
FLUSH_BUDGET_S = 10.0

_INSERT = text(
    "INSERT INTO system_events (id, created_at, level, component, event, data) "
    "VALUES (gen_random_uuid(), now(), CAST(:level AS event_severity), :component, "
    ":event, CAST(:data AS jsonb))"
)

CYCLES_SINCE_SQL = """
SELECT DISTINCT ON (data->>'loop', data->>'run_id', (data->>'seq')::int)
       data->>'loop' AS loop, data->>'run_id' AS run_id, (data->>'seq')::int AS seq,
       (data->>'ended_at')::timestamptz AS ended_at, (data->>'duration_ms')::int AS duration_ms
FROM system_events
WHERE component = 'meme-worker' AND event = 'cycle'
  AND created_at >= CAST(:since AS timestamptz) - interval '1 day'
  AND created_at < CAST(:until AS timestamptz) + interval '1 day'
  AND (data->>'ended_at')::timestamptz >= CAST(:since AS timestamptz)
  AND (data->>'ended_at')::timestamptz < CAST(:until AS timestamptz)
ORDER BY data->>'loop', data->>'run_id', (data->>'seq')::int, created_at
"""
"""The reader's contract: one row per ``(loop, run_id, seq)`` (the first persisted),
windowed by ``ended_at``. ``created_at`` is bounded on **both** sides, ``[since - 1 day,
until + 1 day)``, only to prune partitions (a row is persisted after it ends, so a row
whose ``ended_at`` is in the window normally sits inside that range). ``:since``/``:until``
are timezone-aware UTC. A row persisted more than a day after the window closed, or whose
worker clock ran more than a day ahead of the database's, is **outside** the range and
not read: widen the window or see ``dropped_total``. Readers of ``generation_*`` rows
deduplicate by ``(event, loop, run_id)``."""


async def publish_counters(
    history: CycleHistory, publish: CyclePublisher, budget_s: float, *, force: bool = False
) -> None:
    """Publish the counters when they changed (or ``force``), within ``budget_s``;
    a zero or negative budget skips it — the flush's budget is one, not two."""
    counters = history.counters()
    if budget_s <= 0 or (not force and (counters == history.published or not any(counters))):
        return
    try:
        async with asyncio.timeout(budget_s):
            await publish(history.fields())
        history.published = counters
    except Exception:  # a heartbeat that cannot be written must not stop the writer
        logger.warning("meme_cycle_history_publish_failed")


async def flush_once(
    history: CycleHistory,
    session_factory: async_sessionmaker[AsyncSession],
    publish: CyclePublisher,
    *,
    batch: int = BATCH,
    budget_s: float = FLUSH_BUDGET_S,
) -> int:
    """Write up to ``batch`` queued rows; returns how many were written.

    ``budget_s`` bounds the whole call (database and counter publication). Never
    raises except for a cancel: a database that cannot be written is
    ``failed_total`` and a warning, and the rows wait for the next flush.
    """
    clock = asyncio.get_running_loop().time
    deadline = clock() + budget_s
    pending = history.peek(batch)
    written = 0
    if pending:
        if await _write_within(history, pending, session_factory, deadline - clock()):
            history.acknowledge(pending[-1][0])
            history.written_total += len(pending)
            written = len(pending)
        else:  # the loops must not feel a database that is down
            history.failed_total += 1
            logger.warning("meme_cycle_history_write_failed", queued=history.queued)
    await publish_counters(history, publish, deadline - clock())
    return written


async def _insert(
    pending: list[tuple[int, HistoryRow]], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with role_session(session_factory, db_role=WORKER_ROLE) as session:
        await session.execute(
            _INSERT,
            [
                {
                    "level": "info",
                    "component": COMPONENT,
                    "event": row.event,
                    "data": json.dumps(row.data),
                }
                for _, row in pending
            ],
        )


def _reap(task: asyncio.Future[None]) -> None:
    """An abandoned write that fails later must not end as 'exception never retrieved'."""
    if not task.cancelled():
        task.exception()


async def _write_within(
    history: CycleHistory,
    pending: list[tuple[int, HistoryRow]],
    session_factory: async_sessionmaker[AsyncSession],
    budget_s: float,
) -> bool:
    """``True`` when the batch was committed within ``budget_s`` — a hard bound.

    The transaction runs in a task of its own and is **abandoned** (cancelled, not
    awaited) when the budget ends: ``asyncio.timeout`` would wait for the cancelled
    write to wind down, which a hung peer never lets it do. One write at a time: a
    previous one still in flight gets the budget to finish, else this flush gives up
    without checking out another connection. A cancel of the caller propagates and
    cancels the write too.
    """
    deadline = asyncio.get_running_loop().time() + budget_s
    previous = history.inflight
    if previous is not None and not previous.done():
        await asyncio.wait({previous}, timeout=budget_s)
        if not previous.done():
            return False
    write = asyncio.ensure_future(_insert(pending, session_factory))
    write.add_done_callback(_reap)
    history.inflight = write
    try:
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        await asyncio.wait({write}, timeout=remaining)
    except BaseException:  # a cancel of the flush: the write must not outlive it unattended
        write.cancel()
        raise
    if not write.done():
        write.cancel()
        history.abandoned_total += 1
        return False
    return not write.cancelled() and write.exception() is None


async def drain(
    history: CycleHistory,
    session_factory: async_sessionmaker[AsyncSession],
    publish: CyclePublisher,
    *,
    budget_s: float,
) -> None:
    """Flush until the queue is empty, a write fails, or ``budget_s`` ends (shutdown)."""
    clock = asyncio.get_running_loop().time
    deadline = clock() + budget_s
    while history.queued and clock() < deadline:
        if await flush_once(history, session_factory, publish, budget_s=deadline - clock()) == 0:
            break
