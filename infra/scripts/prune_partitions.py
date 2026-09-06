#!/usr/bin/env python3
"""Drop the partitions retention no longer covers — DATABASE.md §1.3.

The counterpart of ``create_partitions.py``: that one keeps the months around
the clock — three ahead and, since T2.5f, two behind — this one lets the rest of
the past go. Both are scheduled on the analytics worker and both read the same
retention table, ``partition_retention.py``, which is what keeps the creator from
provisioning a month this job would drop the same night.

Retention is per *partition*, never per row. ``DELETE FROM candles WHERE
open_time < ...`` would rewrite and bloat the partitions holding the history we
keep, and would have to be VACUUMed afterwards; ``DETACH`` + ``DROP`` of a whole
month is O(1) and reclaims the disk immediately. That is the reason ``candles``
is ``LIST (timeframe)`` before it is ``RANGE (open_time)``: the retentions differ
per timeframe (1m 90 days, 1h forever), and a single monthly partition could only
ever expire all of them together.

Only a partition whose **upper bound is already past the cutoff** is dropped, so
a month still holding retained rows is never touched. The candidates are read
from ``pg_inherits`` rather than generated from the calendar, which is what makes
a second run a no-op: what is gone is not listed again.

``--dry-run`` prints the statements and touches nothing.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) over
asyncpg — the only Postgres driver this workspace installs.

Usage:
    uv run python infra/scripts/prune_partitions.py --dry-run
    uv run python infra/scripts/prune_partitions.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from partition_retention import KEEP_FOREVER, is_expired, retention_days
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import detach_partition_sql
from hunter_core.settings import Settings

__all__ = ["KEEP_FOREVER", "expired_partitions", "is_expired", "main", "prune", "retention_days"]
"""``retention_days``/``is_expired`` moved to the sibling ``partition_retention``
when ``create_partitions.py`` gained a backward horizon (T2.5f) and needed the
same policy: the creator must not create a month this job would drop the same
night. Re-exported so this module's surface — and the tests that load it by path
— are unchanged by the split."""

_CANDIDATES = text(
    "SELECT parent.relname, child.relname "
    "FROM pg_inherits i "
    "JOIN pg_class child ON child.oid = i.inhrelid "
    "JOIN pg_class parent ON parent.oid = i.inhparent "
    "WHERE child.relispartition AND child.relkind = 'r' "
    "ORDER BY parent.relname, child.relname"
)

Statement = tuple[str, str]
"""``(partition being dropped, SQL)``."""


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def planned_statements(
    partitions: list[tuple[str, str]],
    now: datetime | None = None,
    settings: Settings | None = None,
) -> list[Statement]:
    """``DETACH`` then ``DROP`` for every ``(parent, child)`` past its retention."""
    moment = now or datetime.now(UTC)
    policy = retention_days(settings)
    statements: list[Statement] = []
    for parent, child in partitions:
        if parent not in policy:
            continue
        if not is_expired(child, policy[parent], moment):
            continue
        statements.append((child, detach_partition_sql(parent, child)))
        statements.append((child, f"DROP TABLE IF EXISTS {child}"))
    return statements


async def expired_partitions(
    now: datetime | None = None, settings: Settings | None = None
) -> list[Statement]:
    """Read the live partition list and plan what to drop from it."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            result = await connection.execute(_CANDIDATES)
            partitions = [(row[0], row[1]) for row in result]
    finally:
        await engine.dispose()
    return planned_statements(partitions, now, settings)


async def prune(statements: list[Statement]) -> list[str]:
    """Run every statement; return the partitions dropped, in order."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    dropped: list[str] = []
    try:
        async with engine.begin() as connection:
            for name, sql in statements:
                await connection.execute(text(sql))
                if sql.startswith("DROP TABLE"):
                    dropped.append(name)
    finally:
        await engine.dispose()
    return dropped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the statements without running them"
    )
    args = parser.parse_args()

    statements = asyncio.run(expired_partitions())
    if args.dry_run:
        for name, sql in statements:
            print(f"[dry-run] {name}: {sql}")
        print(f"[dry-run] {len(statements) // 2} partition(s) would be dropped")
        return 0

    dropped = asyncio.run(prune(statements))
    for name in dropped:
        print(f"dropped {name}")
    print(f"{len(dropped)} partition(s) dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
