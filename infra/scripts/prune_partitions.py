#!/usr/bin/env python3
"""Drop the partitions retention no longer covers — DATABASE.md §1.3.

The counterpart of ``create_partitions.py``: that one keeps the future three
months ahead, this one lets the past go. Both are scheduled on the analytics
worker.

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
import re
import sys
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import (
    detach_partition_sql,
    list_partition_name,
    month_bounds,
)
from hunter_core.settings import Settings

KEEP_FOREVER: int | None = None
"""Retention for a relation DATABASE.md §1.3 gives no limit for."""

_MONTH_SUFFIX = re.compile(r"^(?P<owner>.+)_(?P<year>(?:19|20)\d{2})_(?P<month>0[1-9]|1[0-2])$")

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


def retention_days(settings: Settings | None = None) -> dict[str, int | None]:
    """Days of history to keep, per relation that directly owns monthly children.

    The two figures the platform tunes at runtime come from ``Settings``; the
    rest are the fixed table in DATABASE.md §1.3. Timeframes the document does
    not give a limit for (``15m``, ``4h``) are kept forever on purpose —
    inventing a retention for them here would silently delete data no decision
    covers.
    """
    config = settings or Settings()
    candles = {
        "1m": config.retention_candles_1m_days,
        "5m": 365,
        "15m": KEEP_FOREVER,
        "1h": KEEP_FOREVER,
        "4h": KEEP_FOREVER,
        "1d": KEEP_FOREVER,
    }
    equity = {
        "1m": 30,
        "5m": KEEP_FOREVER,
        "15m": KEEP_FOREVER,
        "1h": KEEP_FOREVER,
        "4h": KEEP_FOREVER,
        "1d": KEEP_FOREVER,
    }
    policy: dict[str, int | None] = {
        "audit_logs": KEEP_FOREVER,
        "system_events": 30,
        "market_snapshots": 30,
        "liquidations": 30,
        "opportunity_history": 90,
        "feature_snapshots": config.retention_feature_snapshots_days,
    }
    for label, days in candles.items():
        policy[list_partition_name("candles", label)] = days
    for label, days in equity.items():
        policy[list_partition_name("portfolio_equity_snapshots", label)] = days
    return policy


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def is_expired(child: str, keep_days: int | None, now: datetime) -> bool:
    """True when every row ``child`` can hold is older than the retention window.

    A monthly partition covers ``[start, end)``; it is expired only once ``end``
    itself is past the cutoff, so the month a retained row could still fall in is
    never a candidate.
    """
    if keep_days is None:
        return False
    match = _MONTH_SUFFIX.match(child)
    if match is None:
        return False
    _lower, upper = month_bounds(int(match["year"]), int(match["month"]))
    cutoff = now.timestamp() - keep_days * 86400
    return datetime.strptime(upper, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() <= cutoff


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
