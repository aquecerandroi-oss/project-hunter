"""Monthly RANGE partitions created by the initial revision — DATABASE.md §1.3.

Naming and bounds come from ``hunter_core.db.models`` so the revision and
``infra/scripts/create_partitions.py`` cannot disagree about what a partition is
called. ``PARTITIONED_TABLES``, on the other hand, is frozen: a revision must
describe the schema as of that revision, so a partitioned table added to the
models later must not silently change what ``0001`` creates.
``test_migrations.py`` asserts the frozen list still equals
``hunter_core.db.models.partitioned_tables()``.

``INITIAL_MONTHS`` is hardcoded on purpose: a migration replayed at any future
date must produce the same schema, so its bounds must not depend on the clock.
Everything after the last month here belongs to ``create_partitions.py``, which
the analytics worker runs daily and which keeps three months ahead.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import create_partition_sql, drop_partition_sql

PARTITIONED_TABLES: tuple[str, ...] = (
    "audit_logs",
    "candles",
    "feature_snapshots",
    "liquidations",
    "market_snapshots",
    "opportunity_history",
    "portfolio_equity_snapshots",
    "system_events",
)

INITIAL_MONTHS: tuple[tuple[int, int], ...] = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
)


def create_initial_partitions() -> None:
    """Create ``INITIAL_MONTHS`` for every partitioned parent in the metadata."""
    for table in PARTITIONED_TABLES:
        for year, month in INITIAL_MONTHS:
            op.execute(create_partition_sql(table, year, month))


def drop_initial_partitions() -> None:
    """Drop the partitions this revision created; the parents go with the tables."""
    for table in PARTITIONED_TABLES:
        for year, month in reversed(INITIAL_MONTHS):
            op.execute(drop_partition_sql(table, year, month))
