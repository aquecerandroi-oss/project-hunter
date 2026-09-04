"""How a partition is named, bounded and secured — DATABASE.md §1.3.

This lives next to the models because the models are what declare
``postgresql_partition_by``. Every consumer imports it from here so there is one
definition, never two that can drift: ``infra/migrations/ddl/partitions.py`` (the
initial revision), ``infra/scripts/create_partitions.py`` (the daily job that
keeps three months ahead) and ``infra/scripts/prune_partitions.py`` (the daily
job that drops what retention no longer covers).

Two shapes exist:

- **monthly RANGE** — ``audit_logs`` and friends: ``audit_logs_2026_09``;
- **LIST then RANGE** — ``candles`` is partitioned by ``timeframe`` first and
  each of those by month, so retention differs per timeframe (1m: 90 d, 5m: 1 a,
  1h/1d: unlimited) by dropping whole sub-partitions instead of deleting rows.
  ``portfolio_equity_snapshots`` is the same shape on ``resolution``/``ts``.
  Leaves are named ``candles_1m_2026_09``.

:func:`harden_partition_sql` is the other reason this module is shared. A
partition does **not** inherit its parent's privileges or its parent's RLS
policies: reads through the parent are checked on the parent, but a query naming
a child directly is checked on the child alone. Every child therefore has all
grants revoked (access goes through the parent) and, when the parent is a tenant
table, RLS enabled, forced and policed in its own right.
"""

from __future__ import annotations

from datetime import UTC, datetime

APP_ROLE = "hunter_app"
WORKER_ROLE = "hunter_worker"
"""The two application roles. Neither may touch a partition child directly."""

TENANT_POLICY = "tenant_isolation"

ORG_SETTING = "NULLIF(current_setting('app.current_org', true), '')::uuid"
"""The current organization, or NULL — and NULL matches no row.

``NULLIF`` is not decoration. ``current_setting(name, true)`` returns NULL only
while the session has *never* seen the setting; once a transaction has run
``SET LOCAL app.current_org``, the GUC survives the commit as an **empty
string** for the rest of that backend. Behind a transaction pooler the next
checkout of that same connection is a different request, so the plain
``current_setting(...)::uuid`` in DATABASE.md §1.2 raises ``invalid input syntax
for type uuid: ""`` instead of quietly returning no rows — a hard 500 on any
request that legitimately runs without an organization.
"""

ORG_MATCH = f"organization_id = {ORG_SETTING}"
"""The one tenant predicate, shared by parents and partition children."""

AUDIT_SYSTEM_POLICY = "audit_system_scope"
"""``audit_logs`` only: lets the app write a system-scope (NULL org) audit row."""

SUBPARTITION_KEY: dict[str, str] = {
    "candles": "open_time",
    "portfolio_equity_snapshots": "ts",
}
"""LIST-partitioned parent -> the column its sub-partitions RANGE over."""


def partition_name(table: str, year: int, month: int) -> str:
    """``candles_1m`` + 2026-09 -> ``candles_1m_2026_09``."""
    return f"{table}_{year:04d}_{month:02d}"


def list_partition_name(table: str, value: str) -> str:
    """``candles`` + ``1m`` -> ``candles_1m`` (an intermediate, still partitioned)."""
    return f"{table}_{value}"


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """``[first day of the month, first day of the next month)`` as UTC dates."""
    start = datetime(year, month, 1, tzinfo=UTC)
    end_year = year + 1 if month == 12 else year
    end_month = 1 if month == 12 else month + 1
    end = datetime(end_year, end_month, 1, tzinfo=UTC)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def months_from(start: datetime, count: int) -> list[tuple[int, int]]:
    """``count`` consecutive ``(year, month)`` pairs beginning with ``start``'s month."""
    months: list[tuple[int, int]] = []
    year, month = start.year, start.month
    for _ in range(count):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def months_before(cutoff: datetime, count: int) -> list[tuple[int, int]]:
    """``count`` consecutive ``(year, month)`` pairs ending just before ``cutoff``'s."""
    months: list[tuple[int, int]] = []
    year, month = cutoff.year, cutoff.month
    for _ in range(count):
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        months.append((year, month))
    return list(reversed(months))


def create_partition_sql(table: str, year: int, month: int) -> str:
    """Idempotent ``CREATE TABLE ... PARTITION OF ... FOR VALUES FROM ... TO ...``."""
    lower, upper = month_bounds(year, month)
    child = partition_name(table, year, month)
    return (
        f"CREATE TABLE IF NOT EXISTS {child} PARTITION OF {table} "
        f"FOR VALUES FROM ('{lower}') TO ('{upper}')"
    )


def create_list_partition_sql(parent: str, value: str, sub_key: str) -> str:
    """The intermediate ``candles_1m``: one LIST value, itself RANGE-partitioned."""
    child = list_partition_name(parent, value)
    return (
        f"CREATE TABLE IF NOT EXISTS {child} PARTITION OF {parent} "
        f"FOR VALUES IN ('{value}') PARTITION BY RANGE ({sub_key})"
    )


def drop_partition_sql(table: str, year: int, month: int) -> str:
    """The reverse of :func:`create_partition_sql`."""
    return f"DROP TABLE IF EXISTS {partition_name(table, year, month)}"


def detach_partition_sql(parent: str, child: str) -> str:
    """``DETACH`` before ``DROP`` so a long-running scan of the parent is not blocked."""
    return f"ALTER TABLE {parent} DETACH PARTITION {child}"


def harden_partition_sql(child: str, *, tenant: bool, audit_scope: bool = False) -> list[str]:
    """Make ``child`` unreachable except through its parent.

    Privileges are never inherited from a partitioned parent, so a child that
    kept the schema-wide grant let ``hunter_app`` run ``DELETE FROM
    audit_logs_2026_09`` even though the parent is append-only. Policies are not
    inherited either — a query naming the child directly is filtered by the
    child's own policies, of which an RLS-enabled child has none unless we
    create them. Both halves are fixed here, at creation time.

    Idempotent: the revoke is unconditional and each policy is dropped before it
    is created, so ``create_partitions.py`` may run twice.
    """
    statements = [f"REVOKE ALL ON {child} FROM {APP_ROLE}, {WORKER_ROLE}"]
    if not tenant:
        return statements
    statements += [
        f"ALTER TABLE {child} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {child} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {TENANT_POLICY} ON {child}",
        f"CREATE POLICY {TENANT_POLICY} ON {child} USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})",
    ]
    if audit_scope:
        statements += [
            f"DROP POLICY IF EXISTS {AUDIT_SYSTEM_POLICY} ON {child}",
            f"CREATE POLICY {AUDIT_SYSTEM_POLICY} ON {child} "
            f"FOR INSERT WITH CHECK (organization_id IS NULL)",
        ]
    return statements
