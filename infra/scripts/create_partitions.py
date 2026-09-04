#!/usr/bin/env python3
"""Keep monthly partitions ahead of the clock — DATABASE.md §1.3.

``0001_initial_schema`` creates 2026-09 through 2026-12; from there on this
script owns the future. The analytics worker runs it daily, and a missing
partition is a `critical` `system_event` — so it must never be the reason an
insert fails.

Two shapes are kept ahead. Six parents are plain monthly ``RANGE``; ``candles``
and ``portfolio_equity_snapshots`` are ``LIST`` on the timeframe first, so this
script ensures the ``candles_1m`` level exists too (cheap, and it is what makes a
newly added ``candle_timeframe`` label writable) before creating that level's
months.

Every child is hardened the moment it is created, exactly as the migration does
it: the application roles are revoked (all traffic goes through the parent) and,
for a child of a tenant parent, RLS is enabled, forced and policed **on the
child** — Postgres consults neither the parent's grants nor the parent's
policies for a query that names the child.

Idempotent: creation is ``CREATE TABLE IF NOT EXISTS ... PARTITION OF``, the
revoke is unconditional, and each policy is dropped before being recreated, so a
second run changes nothing. Names and bounds come from
``hunter_core.db.models`` — the same helpers the migration uses, so the two can
never disagree.

**One transaction per partitioned parent.** Creating a partition takes an
``ACCESS EXCLUSIVE`` lock on its parent; a single transaction over all eight
parents held all eight locks until the very last statement committed, so this
job blocked writes to ``audit_logs`` while it worked through ``candles``.
Because every statement is idempotent, splitting the work costs nothing: a run
that fails halfway keeps what it already created and the next run finishes it.

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
    create_list_partition_sql,
    create_partition_sql,
    harden_partition_sql,
    list_partition_name,
    list_partitioned_tables,
    monthly_partition_parents,
    months_from,
    partition_name,
    tenant_tables,
)
from hunter_core.settings import Settings

_EXISTING_PARTITIONS = text(
    "SELECT c.relname FROM pg_class c "
    "WHERE c.relispartition AND c.relnamespace = 'public'::regnamespace"
)
"""What already exists, in *this* schema.

Unqualified, the query counts a partition of the same name in any schema of the
database — a staging copy, an extension's own partitioned table — and the script
would then report a partition it had just created in ``public`` as "already
present". The statements themselves are unqualified and so resolve through
``search_path`` to ``public``; the census has to agree with them.
"""

Statement = tuple[str, str]
"""``(relation the statement concerns, SQL)``."""

Group = tuple[str, list[Statement]]
"""``(partitioned parent, its statements)`` — the unit of one transaction."""


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _harden(child: str, root: str, tenants: frozenset[str]) -> list[Statement]:
    return [
        (child, sql)
        for sql in harden_partition_sql(
            child, tenant=root in tenants, audit_scope=root == "audit_logs"
        )
    ]


def planned_groups(months_ahead: int, now: datetime | None = None) -> list[Group]:
    """Everything needed for the current month plus ``months_ahead`` more, per parent.

    Grouped by the *top-level* partitioned table, which is the relation whose
    lock every statement in the group contends for: the ``candles_1m`` level and
    every ``candles_1m_YYYY_MM`` under it all belong to ``candles``. Within a
    group the order still matters — the LIST level is created before the months
    that hang off it — and the flattened order is unchanged from before.
    """
    start = now or datetime.now(UTC)
    tenants = frozenset(tenant_tables())
    months = months_from(start, months_ahead + 1)
    groups: dict[str, list[Statement]] = {}

    for parent, (_column, labels, sub_key) in list_partitioned_tables().items():
        statements = groups.setdefault(parent, [])
        for label in labels:
            intermediate = list_partition_name(parent, label)
            statements.append((intermediate, create_list_partition_sql(parent, label, sub_key)))
            statements += _harden(intermediate, parent, tenants)

    for owner, root in monthly_partition_parents().items():
        statements = groups.setdefault(root, [])
        for year, month in months:
            child = partition_name(owner, year, month)
            statements.append((child, create_partition_sql(owner, year, month)))
            statements += _harden(child, root, tenants)

    return list(groups.items())


def planned_statements(months_ahead: int, now: datetime | None = None) -> list[Statement]:
    """:func:`planned_groups` flattened — what ``--dry-run`` prints."""
    return [
        statement
        for _parent, statements in planned_groups(months_ahead, now)
        for statement in statements
    ]


async def ensure_partitions(groups: list[Group]) -> list[str]:
    """Run each group in a transaction of its own; return the names that are new.

    One transaction per partitioned parent, not one spanning all eight.
    ``CREATE TABLE ... PARTITION OF`` takes an ``ACCESS EXCLUSIVE`` lock on the
    parent, and a single transaction held every one of those locks until the last
    statement of the last parent committed — so this daily job blocked writes to
    ``audit_logs`` for as long as it took to reach the end of ``candles``, which
    is by far the largest of them. Per parent, each lock is released as soon as
    that parent is done, and a failure on one parent no longer throws away the
    partitions already created for the others — the next run picks up where this
    one stopped, because every statement is idempotent.
    """
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    created: list[str] = []
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                result = await connection.execute(_EXISTING_PARTITIONS)
                existing = {row[0] for row in result}
            for _parent, statements in groups:
                async with connection.begin():
                    for name, sql in statements:
                        await connection.execute(text(sql))
                        if name not in existing and name not in created:
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

    groups = planned_groups(args.months_ahead)
    partitions = {name for _parent, statements in groups for name, _sql in statements}
    if args.dry_run:
        for parent, statements in groups:
            for name, sql in statements:
                print(f"[dry-run] {parent} -> {name}: {sql}")
        print(f"[dry-run] {len(partitions)} partition(s) would be ensured")
        return 0

    created = asyncio.run(ensure_partitions(groups))
    for name in created:
        print(f"created {name}")
    print(f"{len(created)} partition(s) created, {len(partitions) - len(created)} already present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
