#!/usr/bin/env python3
"""Delete finished idempotency rows past their retention — DATABASE.md §12.

``processed_events`` is the durable "have we already applied this delivery"
guard. It only has to answer for as long as a producer might redeliver, and
nothing redelivers a week later: after that a completed row is dead weight on a
table every webhook and every stream consumer writes to.

Two rules, and the second is the one worth reading:

- Only rows with ``completed_at NOT NULL`` are candidates. A row whose
  ``completed_at`` is still NULL is an unfinished claim — a delivery that was
  taken and never applied, because the process handling it died. Deleting it
  would erase the only record that it happened, and it is re-claimable by
  design (``services.webhook_delivery``), so it is left exactly where it is.
  A pile of them in this table is a signal, not garbage.
- The cutoff is ``completed_at``, not ``claimed_at``: retention starts when the
  effect landed, not when it was first attempted.

Idempotent by construction — what is gone is not deleted again — so it is safe
to schedule and safe to re-run after a partial failure.

``--dry-run`` counts and touches nothing.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) over
asyncpg — the only Postgres driver this workspace installs.

Usage:
    uv run python infra/scripts/prune_processed_events.py --dry-run
    uv run python infra/scripts/prune_processed_events.py
    uv run python infra/scripts/prune_processed_events.py --retention-days 30
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from hunter_core.settings import Settings

RETENTION_DAYS = 7
"""Days a completed row is kept. Comfortably longer than any producer's retry
schedule: Svix gives up well inside a day."""

_COUNT = text(
    "SELECT count(*) FROM processed_events "
    "WHERE completed_at IS NOT NULL "
    "AND completed_at < now() - make_interval(days => :retention_days)"
)
_DELETE = text(
    "DELETE FROM processed_events "
    "WHERE completed_at IS NOT NULL "
    "AND completed_at < now() - make_interval(days => :retention_days)"
)
"""Spelled out twice rather than sharing an interpolated WHERE clause: two
literal statements are what a reader (and the SQL-injection lint) can check at
a glance, and the duplication is three lines."""


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


async def expired(retention_days: int = RETENTION_DAYS) -> int:
    """How many completed rows are past the retention window."""
    engine = _engine()
    try:
        async with engine.connect() as connection:
            count = await connection.scalar(_COUNT, {"retention_days": retention_days})
    finally:
        await engine.dispose()
    return int(count or 0)


async def prune(retention_days: int = RETENTION_DAYS) -> int:
    """Delete them; returns how many rows went."""
    engine = _engine()
    try:
        async with engine.begin() as connection:
            result = await connection.execute(_DELETE, {"retention_days": retention_days})
    finally:
        await engine.dispose()
    return result.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune completed processed_events rows.")
    parser.add_argument(
        "--dry-run", action="store_true", help="count the rows without deleting them"
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=RETENTION_DAYS,
        help=f"days of completed rows to keep (default: {RETENTION_DAYS})",
    )
    args = parser.parse_args()

    if args.dry_run:
        candidates = asyncio.run(expired(args.retention_days))
        print(f"[dry-run] {candidates} completed row(s) would be deleted")
        return 0

    deleted = asyncio.run(prune(args.retention_days))
    print(f"{deleted} completed row(s) deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
