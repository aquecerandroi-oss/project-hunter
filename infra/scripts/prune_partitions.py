#!/usr/bin/env python3
"""Drop the partitions retention no longer covers — DATABASE.md §1.3.

The counterpart of ``create_partitions.py``: that one keeps the months around
the clock — three ahead and, since T2.5f, two behind — this one lets the rest of
the past go. Both read the same retention table, ``partition_retention.py``,
which is what keeps the creator from provisioning a month this job would drop
the same night. Both are scheduled by ``infra/vps/cron/hunter-partitions``.

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

**It must never jam the ingestion** (docs/design/retencao-e-disco-2026-09-27.md
§6, passo 2c). ``DETACH`` asks for ``ACCESS EXCLUSIVE`` on the parent; queued
behind the nightly ``pg_dump`` (``ACCESS SHARE`` on every table for 80+ minutes)
it made every later ``INSERT`` into that parent queue behind itself, and all the
drops ran in one transaction holding every lock until the last one. Now:

- one transaction per partition (``DETACH`` + ``DROP``), opened with ``SET
  LOCAL lock_timeout = '3s'`` and ``statement_timeout = '60s'``, so locks are
  held for one partition only. ``lock_timeout`` bounds **each** lock wait, not
  the transaction: ``DETACH`` waits for the parent and then for the child, so a
  writer queued behind it can wait up to ~6 s in the worst case, plus the
  milliseconds of ``DETACH``/``DROP``/``COMMIT`` themselves (Astra, review
  prune-locks) — bounded, where it used to be the whole dump;
- a partition whose lock times out is skipped **by name** and retried by the
  next run; any other error on one partition is recorded and the run moves on —
  one partition never fails the whole run;
- nothing is touched while a ``pg_dump`` is connected to this database
  (``pg_stat_activity.application_name = 'pg_dump'``, the name libpq gives every
  ``pg_dump`` that does not override it with ``PGAPPNAME`` — the backup of
  ``infra/vps/backup_postgres.sh`` does not); the check runs before every
  partition, so a dump that starts mid-run stops it. It is a check, not mutual
  exclusion: a dump that connects between the check and the ``DETACH`` either
  waits the milliseconds of that one partition or makes it time out and skip;
- every applied run leaves one ``system_events`` row (``component =
  'prune_partitions'``) with what was dropped, skipped and failed.

Exit codes, as ``create_partitions.py``: 0 all done; **75** (``EX_TEMPFAIL``)
something was skipped for a lock or a dump and the next run retries it; 1 a
partition failed for any other reason (investigate).

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
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from partition_retention import KEEP_FOREVER, is_expired, retention_days
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import detach_partition_sql
from hunter_core.domain.types import uuid7
from hunter_core.logging import get_logger
from hunter_core.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "KEEP_FOREVER",
    "PruneReport",
    "expired_partitions",
    "is_expired",
    "main",
    "prune",
    "retention_days",
]
"""``retention_days``/``is_expired`` moved to the sibling ``partition_retention``
when ``create_partitions.py`` gained a backward horizon (T2.5f) and needed the
same policy: the creator must not create a month this job would drop the same
night. Re-exported so this module's surface — and the tests that load it by path
— are unchanged by the split."""

logger = get_logger(__name__)

EXIT_TEMPFAIL = 75
LOCK_NOT_AVAILABLE = "55P03"
GUARDS = ("SET LOCAL lock_timeout = '3s'", "SET LOCAL statement_timeout = '60s'")
"""Opened in every partition's transaction (module docstring)."""

_CANDIDATES = text(
    "SELECT parent.relname, child.relname "
    "FROM pg_inherits i "
    "JOIN pg_class child ON child.oid = i.inhrelid "
    "JOIN pg_class parent ON parent.oid = i.inhparent "
    "WHERE child.relispartition AND child.relkind = 'r' "
    "ORDER BY parent.relname, child.relname"
)

_DUMP_ACTIVE = text(
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE application_name = 'pg_dump' AND datname = current_database() "
    "AND pid <> pg_backend_pid()"
)
"""``application_name`` is visible for every session, whatever the role."""

_RECORD = text(
    "INSERT INTO system_events (id, created_at, level, component, event, message, data) "
    "VALUES (:id, now(), CAST(:level AS event_severity), 'prune_partitions', "
    "'partitions_pruned', :message, CAST(:data AS jsonb))"
)

Statement = tuple[str, str]
"""``(partition being dropped, SQL)``."""


@dataclass
class PruneReport:
    """What one run did, partition by partition, in order."""

    dropped: list[str] = field(default_factory=list[str])
    skipped: dict[str, str] = field(default_factory=dict[str, str])
    """Lock timeout or ``pg_dump`` — the next run retries these."""
    failed: dict[str, str] = field(default_factory=dict[str, str])
    dump_active: bool = False

    def exit_code(self) -> int:
        if self.failed:
            return 1
        return EXIT_TEMPFAIL if self.skipped else 0


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


def _by_partition(statements: list[Statement]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name, sql in statements:
        grouped.setdefault(name, []).append(sql)
    return grouped


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


async def dump_in_progress(connection: AsyncConnection) -> bool:
    async with connection.begin():
        return bool(await connection.scalar(_DUMP_ACTIVE))


async def _drop_one(connection: AsyncConnection, name: str, sqls: list[str]) -> str | None:
    """One partition, one transaction; the reason it was skipped, or ``None``."""
    try:
        async with connection.begin():
            for guard in GUARDS:
                await connection.execute(text(guard))
            for sql in sqls:
                await connection.execute(text(sql))
    except DBAPIError as exc:
        # SQLSTATE, not ``isinstance(exc.orig, asyncpg...LockNotAvailableError)``:
        # through SQLAlchemy's asyncpg dialect ``orig`` is the dialect's own
        # wrapper, which carries the code as ``.sqlstate`` (the real-Postgres
        # test in tests/test_prune_partitions_integration.py caught this).
        if getattr(exc.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
            return "lock_timeout: ACCESS EXCLUSIVE not granted within 3s"
        raise
    return None


async def prune(statements: list[Statement], report: PruneReport | None = None) -> list[str]:
    """Drop partition by partition; return the partitions dropped, in order.

    ``report`` (optional) receives the skipped and failed partitions too.
    """
    report = report if report is not None else PruneReport()
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            for name, sqls in _by_partition(statements).items():
                if report.dump_active or await dump_in_progress(connection):
                    report.dump_active = True
                    report.skipped[name] = "pg_dump in progress on this database"
                    continue
                try:
                    reason = await _drop_one(connection, name, sqls)
                except DBAPIError as exc:
                    report.failed[name] = f"{type(exc.orig).__name__}: {exc.orig}"[:500]
                    logger.error(
                        "prune_partitions.failed", partition=name, error=report.failed[name]
                    )
                    continue
                if reason is None:
                    report.dropped.append(name)
                    continue
                report.skipped[name] = reason
                logger.warning(
                    "prune_partitions.skipped", partition=name, reason=reason, retry="next run"
                )
    finally:
        await engine.dispose()
    if report.dump_active:
        logger.warning("prune_partitions.dump_active", skipped=list(report.skipped))
    return report.dropped


async def record_run(report: PruneReport) -> None:
    """The run's one ``system_events`` row (never on ``--dry-run``)."""
    level = "error" if report.failed else "warning" if report.skipped else "info"
    message = (
        f"{len(report.dropped)} dropped, {len(report.skipped)} skipped, "
        f"{len(report.failed)} failed" + (" (pg_dump in progress)" if report.dump_active else "")
    )
    data = {
        "dropped": report.dropped,
        "skipped": report.skipped,
        "failed": report.failed,
        "dump_active": report.dump_active,
    }
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            await connection.execute(text(GUARDS[0]))
            await connection.execute(
                _RECORD,
                {"id": uuid7(), "level": level, "message": message, "data": json.dumps(data)},
            )
    finally:
        await engine.dispose()


async def _dry_run_dump_check() -> bool:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            return await dump_in_progress(connection)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print the statements without running them"
    )
    args = parser.parse_args()

    statements = asyncio.run(expired_partitions())
    if args.dry_run:
        for name, sqls in _by_partition(statements).items():
            for sql in (*GUARDS, *sqls):
                print(f"[dry-run] {name} (own transaction): {sql}")
        print(f"[dry-run] {len(_by_partition(statements))} partition(s) would be dropped")
        if asyncio.run(_dry_run_dump_check()):
            print("[dry-run] a pg_dump is connected now: a real run would touch nothing")
        return 0

    report = PruneReport()
    asyncio.run(prune(statements, report))
    for name in report.dropped:
        print(f"dropped {name}")
    for name, reason in report.skipped.items():
        print(f"skipped {name}: {reason} (next run retries)")
    for name, error in report.failed.items():
        print(f"FAILED {name}: {error}")
    print(
        f"{len(report.dropped)} partition(s) dropped, {len(report.skipped)} skipped, "
        f"{len(report.failed)} failed"
    )
    asyncio.run(record_run(report))
    return report.exit_code()


if __name__ == "__main__":
    sys.exit(main())
