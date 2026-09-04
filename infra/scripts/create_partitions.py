#!/usr/bin/env python3
"""Keep monthly partitions ahead of the clock — DATABASE.md §1.3.

``0001_initial_schema`` creates 2026-09 through 2026-12; from there on this
script owns the future. The analytics worker runs it daily, and a missing
partition is a `critical` `system_event` — so it must never be the reason an
insert fails.

Idempotent: every statement is ``CREATE TABLE IF NOT EXISTS ... PARTITION OF``,
so a second run changes nothing. The partitioned tables and their keys are read
from ``Base.metadata``; names and bounds come from ``hunter_core.db.models``,
the same helpers the migration uses, so the two can never disagree.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) over
asyncpg — the only Postgres driver this workspace installs.

Usage:
    uv run python infra/scripts/create_partitions.py
    uv run python infra/scripts/create_partitions.py --months-ahead 6
    uv run python infra/scripts/create_partitions.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import (
    create_partition_sql,
    months_from,
    partition_name,
    partitioned_tables,
)
from hunter_core.settings import Settings

_EXISTING_PARTITIONS = text("SELECT c.relname FROM pg_class c WHERE c.relispartition")


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def planned_statements(months_ahead: int, now: datetime | None = None) -> list[tuple[str, str]]:
    """``(partition name, SQL)`` for the current month plus ``months_ahead`` more."""
    start = now or datetime.now(UTC)
    statements: list[tuple[str, str]] = []
    for table in partitioned_tables():
        for year, month in months_from(start, months_ahead + 1):
            statements.append(
                (partition_name(table, year, month), create_partition_sql(table, year, month))
            )
    return statements


async def ensure_partitions(statements: list[tuple[str, str]]) -> list[str]:
    """Run every statement; return the names that did not exist beforehand."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    created: list[str] = []
    try:
        async with engine.begin() as connection:
            result = await connection.execute(_EXISTING_PARTITIONS)
            existing = {row[0] for row in result}
            for name, sql in statements:
                await connection.execute(text(sql))
                if name not in existing:
                    created.append(name)
    finally:
        await engine.dispose()
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months-ahead",
        type=int,
        default=3,
        help="months to create beyond the current one (default 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the statements without running them"
    )
    args = parser.parse_args()

    if args.months_ahead < 0:
        print("--months-ahead must be >= 0")
        return 2

    statements = planned_statements(args.months_ahead)
    if args.dry_run:
        for name, sql in statements:
            print(f"[dry-run] {name}: {sql}")
        print(f"[dry-run] {len(statements)} partition(s) would be ensured")
        return 0

    created = asyncio.run(ensure_partitions(statements))
    for name in created:
        print(f"created {name}")
    print(f"{len(created)} partition(s) created, {len(statements) - len(created)} already present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
