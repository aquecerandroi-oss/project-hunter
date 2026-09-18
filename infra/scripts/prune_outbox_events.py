#!/usr/bin/env python3
"""Delete dispatched ``outbox_events`` rows past their retention — DATABASE.md §1.3.

The outbox is a queue, not a log: a row exists so that a committed event
cannot be lost before a dispatcher publishes it to Redis. Once ``dispatched_at``
is set the row has done its job, and DATABASE.md §1.3 keeps it for **7 days**
only as the ceiling of the replay window (``reconcile(since=)``). Nothing ever
pruned it in practice — the table was documented as the ``analytics-worker``'s
daily job (M5), a worker that does not exist — so on 2026-09-18 the VPS carried
19.569.162 dispatched rows (17 GB, every one of them ``dispatched_at NOT NULL``,
growing ~2,1 M rows / ~1,5 GB a day) inside a 58 GB database whose nightly dump
had gone from 1,6 GB to 10,6 GB in a week. This script is that job.

Two rules, both enforced by ``hunter_core.events.outbox_store.prune_dispatched``
rather than restated here:

- A row with ``dispatched_at IS NULL`` is an obligation and is never deleted at
  any age. A pile of them is a signal (dispatcher down), not garbage.
- Deletion is **batched** (``PRUNE_BATCH`` = 5 000 ids, taken from the primary
  key in ``id`` order; ``dispatched_at`` has no index on purpose, so the last
  batch over a drained table may still walk the surviving rows). One
  transaction per batch, with a short pause between batches (``--pause-s``),
  so the lock footprint and the WAL of any single statement stay small on a
  table the dispatcher is writing to at the same time. The loop stops when a
  batch comes back short, or at ``--max-batches`` so a first run over a week of
  backlog can be spread across several cron nights if the operator wants.

Deleting rows frees space **inside** the table for reuse (after autovacuum);
it does not shrink the file or move ``df`` (Astra, review-T4.63). What the
operator sees on disk comes back only as growth stops eating new pages.

Idempotent by construction — what is gone is not deleted again — so it is safe
to schedule and safe to re-run after a partial failure.

``--dry-run`` counts and touches nothing.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) over
asyncpg, like ``prune_processed_events.py``; on the VPS it runs through
``compose.sh ops`` (the deployed image, never a build) — recipe in
``infra/vps/README.md``.

Usage:
    uv run python infra/scripts/prune_outbox_events.py --dry-run
    uv run python infra/scripts/prune_outbox_events.py
    uv run python infra/scripts/prune_outbox_events.py --retention-days 7 --max-batches 400
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from hunter_core.events.outbox_store import PRUNE_BATCH, prune_dispatched
from hunter_core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

RETENTION_DAYS = 7
"""Days a dispatched row is kept — DATABASE.md §1.3. It is the ceiling of the
replay window (``reconcile(since=)`` can only reach rows still in the table),
not a retry schedule: every consumer is idempotent by ``event_id``."""

MAX_BATCHES_DEFAULT = 0
"""``0`` = no ceiling: loop until a batch comes back short."""

PAUSE_S_DEFAULT = 0.05
"""Seconds between batches: a rate limit on WAL and on the I/O the dispatcher
shares, not a correctness device. ``0`` disables it."""

_COUNT = text(
    "SELECT count(*) FROM outbox_events "
    "WHERE dispatched_at IS NOT NULL AND dispatched_at < :older_than"
)
"""Dry-run only. The real deletion never uses this predicate directly — it goes
through ``prune_dispatched`` so the id-ordered, index-backed batch is the only
shape of DELETE this table ever sees."""


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _engine() -> AsyncEngine:
    return create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})


def cutoff(retention_days: int, now: datetime | None = None) -> datetime:
    """The ``older_than`` handed to the store: ``now - retention``, tz-aware."""
    if retention_days < 1:
        raise ValueError(f"retention must be at least 1 day, got {retention_days}")
    base = now if now is not None else datetime.now(UTC)
    if base.tzinfo is None:
        raise ValueError("cutoff needs a timezone-aware clock")
    return base - timedelta(days=retention_days)


async def prunable(retention_days: int = RETENTION_DAYS) -> int:
    """How many dispatched rows are past the retention window (dry run)."""
    engine = _engine()
    try:
        async with engine.connect() as connection:
            count = await connection.scalar(_COUNT, {"older_than": cutoff(retention_days)})
    finally:
        await engine.dispose()
    return int(count or 0)


async def prune_in_batches(
    delete_batch: Callable[[], Awaitable[int]],
    *,
    batch: int = PRUNE_BATCH,
    max_batches: int = MAX_BATCHES_DEFAULT,
    pause_s: float = 0.0,
) -> tuple[int, int]:
    """Drive ``delete_batch`` until it returns fewer than ``batch`` rows.

    Returns ``(rows_deleted, batches_run)``. ``max_batches > 0`` caps the
    loop — the caller reports the cap was hit so the operator knows rows may
    remain. Negative values are refused rather than read as "no cap". Pure
    control flow, so it is unit-tested without a database; the SQL it drives
    is ``prune_dispatched``, tested in
    ``packages/core/tests/integration/test_outbox_integration.py``.
    """
    if batch < 1:
        raise ValueError(f"batch must be positive, got {batch}")
    if max_batches < 0:
        raise ValueError(f"max_batches must be >= 0 (0 = no cap), got {max_batches}")
    if pause_s < 0:
        raise ValueError(f"pause_s must be >= 0, got {pause_s}")
    deleted = 0
    batches = 0
    while max_batches == 0 or batches < max_batches:
        went = await delete_batch()
        batches += 1
        deleted += went
        if went < batch:
            break
        if pause_s:
            await asyncio.sleep(pause_s)
    return deleted, batches


async def prune(
    retention_days: int = RETENTION_DAYS,
    *,
    batch: int = PRUNE_BATCH,
    max_batches: int = MAX_BATCHES_DEFAULT,
    pause_s: float = PAUSE_S_DEFAULT,
) -> tuple[int, int]:
    """Delete dispatched rows past retention, one transaction per batch."""
    older_than = cutoff(retention_days)
    engine = _engine()

    async def _one_batch() -> int:
        async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
            return await prune_dispatched(session, older_than, batch)

    try:
        return await prune_in_batches(
            _one_batch, batch=batch, max_batches=max_batches, pause_s=pause_s
        )
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune dispatched outbox_events rows.")
    parser.add_argument(
        "--dry-run", action="store_true", help="count the rows without deleting them"
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=RETENTION_DAYS,
        help=f"days of dispatched rows to keep (default: {RETENTION_DAYS})",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=PRUNE_BATCH,
        help=f"rows per DELETE transaction (default: {PRUNE_BATCH})",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=MAX_BATCHES_DEFAULT,
        help="stop after this many batches even if rows remain (default: 0 = no cap)",
    )
    parser.add_argument(
        "--pause-s",
        type=float,
        default=PAUSE_S_DEFAULT,
        help=f"seconds to sleep between batches (default: {PAUSE_S_DEFAULT}; 0 = none)",
    )
    args = parser.parse_args()
    if args.max_batches < 0 or args.batch < 1 or args.pause_s < 0:
        parser.error("--batch >= 1, --max-batches >= 0 and --pause-s >= 0")

    if args.dry_run:
        candidates = asyncio.run(prunable(args.retention_days))
        print(f"[dry-run] {candidates} dispatched row(s) would be deleted")
        return 0

    deleted, batches = asyncio.run(
        prune(
            args.retention_days,
            batch=args.batch,
            max_batches=args.max_batches,
            pause_s=args.pause_s,
        )
    )
    capped = args.max_batches > 0 and batches >= args.max_batches
    suffix = " (max-batches reached; rows may remain — run again)" if capped else ""
    print(f"{deleted} dispatched row(s) deleted in {batches} batch(es){suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
