#!/usr/bin/env python3
"""Keep monthly partitions around the clock — DATABASE.md §1.3.

``0001_initial_schema`` creates 2026-09 through 2026-12; from there on this
script owns the future **and, since T2.5f, the recent past**. The analytics
worker runs it daily, and a missing partition is a `critical` `system_event` —
so it must never be the reason an insert fails.

``--months-behind`` (default 2) is the half that did not exist. The job only
ever looked forward, so a backfill request for seven days made on the 6th named
minutes in the previous month that no partition accepted: the market-worker's
consumer refused 3 300 of 8 547 minutes with ``market_backfill_refused
reason=no_partition``, and the baseline bootstrap (7 days) and replay/β
(30 days) would keep hitting it. A past month is created only while retention
would still keep it (``partition_plan``, ``partition_retention``) — creating one
the pruner drops the same night would just be the two daily jobs fighting over
the same partition.

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

Two session guards, ``SET LOCAL`` inside the same transaction as the DDL
(docs/plans/M1.md, "D4 —" and "D12 —"):

- ``lock_timeout = '3s'`` — creating a partition takes ``ACCESS EXCLUSIVE`` on
  its parent. Without a timeout that request queues behind whatever read
  currently holds the parent (e.g. gap detection's ``ACCESS SHARE`` on
  ``candles``) and then queues *every* later request too, including the
  candle-flush ``INSERT``s — a lock-queue jam, not a slow query, and one that
  breaches the flush's 10 s timeout long before Postgres would ever cancel the
  DDL itself. 3 s is comfortably inside that budget. Because every statement
  here is idempotent, a group that times out is not a failure worth crashing
  over: it is logged (structlog, parent + reason) and skipped, the run moves
  on to the next parent, and the next scheduled run retries the skipped one
  from a clean slate. The process still exits non-zero when anything was
  skipped — silently exiting 0 would hide a jam that is worth an operator
  noticing (cron mail, log scrape) even though nothing here demands a page;
  the T1.3 readiness check is the actual page (`system_event` critical when a
  partition is missing for ``now + 1 day``). It exits **75** for this case
  specifically (sysexits.h ``EX_TEMPFAIL``, "temp failure; user is invited to
  retry" — same file this workspace already draws ``64``/``EX_USAGE`` from in
  ``infra/docker/entrypoint.sh``), never plain ``1``: a benign, self-healing
  skip and an unhandled ``DBAPIError`` (which propagates and ends the process
  with Python's default ``1``) must not share one exit code, or an operator
  who learns "nightly exit 1 is just the routine skip" stops reading
  ``partitions.log`` and a real failure — revoked ``CREATE`` privilege, full
  disk — repeats unnoticed.
- ``TimeZone = 'UTC'`` — ``_partitions.py`` emits date-only bounds
  (``'2026-09-01'``) with no offset; Postgres resolves those against the
  *session* ``TimeZone``, so a non-UTC session leaves an hours-wide gap
  between two months that the first row landing in it would abort on. Belt
  and braces: :func:`_explicit_utc_bounds` also rewrites those bounds to carry
  an explicit ``+00`` from this script's side, without touching the frozen
  ``_partitions.py``.

Usage:
    uv run python infra/scripts/create_partitions.py
    uv run python infra/scripts/create_partitions.py --months-ahead 6
    uv run python infra/scripts/create_partitions.py --months-behind 2
    uv run python infra/scripts/create_partitions.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable

import asyncpg
from partition_plan import (
    DEFAULT_MONTHS_AHEAD,
    DEFAULT_MONTHS_BEHIND,
    Group,
    Statement,
    planned_groups,
    planned_statements,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.logging import get_logger
from hunter_core.settings import Settings

logger = get_logger(__name__)

_LOCK_TIMEOUT_SQL = "SET LOCAL lock_timeout = '3s'"
_SESSION_UTC_SQL = "SET LOCAL TimeZone = 'UTC'"
"""D4 / D12 (docs/plans/M1.md) — see the module docstring."""

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

__all__ = [
    "DEFAULT_MONTHS_AHEAD",
    "DEFAULT_MONTHS_BEHIND",
    "Group",
    "Statement",
    "ensure_partitions",
    "main",
    "migration_url",
    "planned_groups",
    "planned_statements",
]
"""The plan moved to ``partition_plan`` (T2.5f, 350-line budget) but the two
test suites that drive this job load *this* file by path and call
``planned_groups``/``planned_statements`` on it
(``packages/core/tests/integration/test_schema_seed_and_partitions.py``,
``infra/scripts/tests/test_create_partitions.py``). Re-exported here so the
script's public surface is unchanged by an internal split."""


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def ensure_partitions(
    groups: list[Group], on_skip: Callable[[str], None] | None = None
) -> list[str]:
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

    Each group's transaction opens with ``SET LOCAL lock_timeout`` and ``SET
    LOCAL TimeZone`` (D4/D12, module docstring). A lock-timeout hit rolls that
    one group back — nothing from it is added to ``created`` — logs a warning
    naming the parent (structlog) and, if given, calls ``on_skip(parent)`` so a
    caller (``main`` below) can decide what that means for its own exit code
    without this function's return type having to carry it. Then it moves on
    to the next group; the timeout is not raised, because the script is
    idempotent and the next scheduled run retries the skipped parent from
    scratch. Any other database error still propagates: only ``lock_timeout``
    (SQLSTATE ``55P03``) is a condition this job expects and knows how to
    defer.
    """
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    created: list[str] = []
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                result = await connection.execute(_EXISTING_PARTITIONS)
                existing = {row[0] for row in result}
            for parent, statements in groups:
                group_created: list[str] = []
                try:
                    async with connection.begin():
                        await connection.execute(text(_LOCK_TIMEOUT_SQL))
                        await connection.execute(text(_SESSION_UTC_SQL))
                        for name, sql in statements:
                            await connection.execute(text(sql))
                            # Checked against `created` *and* this group's own
                            # buffer: several statements in one group name the
                            # same partition (the CREATE and every harden
                            # statement all carry the child's name), and
                            # `created` itself is only extended once the group
                            # commits — checking it alone would let a name
                            # in the group but not yet in `created` re-add
                            # itself once per harden statement.
                            if (
                                name not in existing
                                and name not in created
                                and name not in group_created
                            ):
                                group_created.append(name)
                except DBAPIError as exc:
                    if not isinstance(exc.orig, asyncpg.exceptions.LockNotAvailableError):
                        raise
                    logger.warning(
                        "create_partitions.group_skipped",
                        parent=parent,
                        reason=(
                            "lock_timeout: ACCESS EXCLUSIVE not granted within 3s, "
                            "likely queued behind a concurrent reader/writer on this parent"
                        ),
                        retry="next scheduled run (idempotent)",
                    )
                    if on_skip is not None:
                        on_skip(parent)
                    continue
                created.extend(group_created)
    finally:
        await engine.dispose()
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months-ahead",
        type=int,
        default=DEFAULT_MONTHS_AHEAD,
        help=f"months to create beyond the current one (default {DEFAULT_MONTHS_AHEAD})",
    )
    parser.add_argument(
        "--months-behind",
        type=int,
        default=DEFAULT_MONTHS_BEHIND,
        help=(
            "months of history to keep writable before the current one "
            f"(default {DEFAULT_MONTHS_BEHIND}); a past month retention would "
            "already drop is skipped"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the statements without running them"
    )
    args = parser.parse_args()

    if args.months_ahead < 0:
        print("--months-ahead must be >= 0")
        return 2
    if args.months_behind < 0:
        print("--months-behind must be >= 0")
        return 2

    groups = planned_groups(args.months_ahead, months_behind=args.months_behind)
    partitions = {name for _parent, statements in groups for name, _sql in statements}
    if args.dry_run:
        for parent, statements in groups:
            # The two SET LOCAL guards (D4/D12) open every real transaction but
            # are not part of `statements` (they are not partition-name-bearing
            # DDL) — printed once per group here so --dry-run shows exactly
            # what ensure_partitions() executes.
            print(f"[dry-run] {parent} -> (transaction) {_LOCK_TIMEOUT_SQL}")
            print(f"[dry-run] {parent} -> (transaction) {_SESSION_UTC_SQL}")
            for name, sql in statements:
                print(f"[dry-run] {parent} -> {name}: {sql}")
        print(f"[dry-run] {len(partitions)} partition(s) would be ensured")
        return 0

    skipped: list[str] = []
    created = asyncio.run(ensure_partitions(groups, on_skip=skipped.append))
    for name in created:
        print(f"created {name}")
    print(f"{len(created)} partition(s) created, {len(partitions) - len(created)} already present")
    if skipped:
        # 75 (EX_TEMPFAIL), not 1: a skip is not a bug (idempotent, retried by
        # the next scheduled run — module docstring) but it is worth a cron
        # failure/alert. The T1.3 readiness check is the actual page for a
        # partition still missing when it matters (now + 1 day); this exit
        # code is just so an operator scraping cron output notices sooner.
        # It must be a code distinct from a hard DBAPIError's plain 1 (Python's
        # default for an uncaught exception) — the whole point of splitting
        # them is so `partitions.log`'s exit status alone tells "routine,
        # retries tomorrow" from "propagated, go investigate" apart, which is
        # exactly what infra/vps/README.md promises the operator.
        print(f"{len(skipped)} group(s) skipped (lock_timeout): {', '.join(skipped)}")
        return 75
    return 0


if __name__ == "__main__":
    sys.exit(main())
