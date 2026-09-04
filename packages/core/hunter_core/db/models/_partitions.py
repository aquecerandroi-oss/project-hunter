"""How a monthly partition is named and bounded — DATABASE.md §1.3.

This lives next to the models because the models are what declare
``postgresql_partition_by``. Both consumers import it from here so there is one
definition, never two that can drift: ``infra/migrations/ddl/partitions.py``
(the initial revision) and ``infra/scripts/create_partitions.py`` (the daily job
that keeps three months ahead).

The suffix produced by :func:`partition_name` is exactly what the Alembic
``env.py`` regex filters out of autogenerate, so a partition never shows up as
schema drift.
"""

from __future__ import annotations

from datetime import UTC, datetime


def partition_name(table: str, year: int, month: int) -> str:
    """``candles`` + 2026-09 -> ``candles_2026_09``."""
    return f"{table}_{year:04d}_{month:02d}"


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


def create_partition_sql(table: str, year: int, month: int) -> str:
    """Idempotent ``CREATE TABLE ... PARTITION OF ... FOR VALUES FROM ... TO ...``."""
    lower, upper = month_bounds(year, month)
    child = partition_name(table, year, month)
    return (
        f"CREATE TABLE IF NOT EXISTS {child} PARTITION OF {table} "
        f"FOR VALUES FROM ('{lower}') TO ('{upper}')"
    )


def drop_partition_sql(table: str, year: int, month: int) -> str:
    """The reverse of :func:`create_partition_sql`."""
    return f"DROP TABLE IF EXISTS {partition_name(table, year, month)}"
