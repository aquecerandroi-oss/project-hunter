"""The partitions ``0001`` creates, and how each one is secured — DATABASE.md §1.3.

Naming and bounds come from ``hunter_core.db.models`` so the revision,
``infra/scripts/create_partitions.py`` and ``infra/scripts/prune_partitions.py``
cannot disagree about what a partition is called. The table lists, on the other
hand, are frozen: a revision must describe the schema as of that revision, so a
partitioned table added to the models later must not silently change what
``0001`` creates. ``test_migrations.py`` asserts the frozen lists still equal
``partitioned_tables()`` and ``list_partitioned_tables()``.

Two shapes:

- six monthly ``RANGE`` parents (``audit_logs`` and friends);
- two ``LIST``-then-``RANGE`` parents. ``candles`` is split by ``timeframe``
  first, so ``candles_1m`` can be pruned at 90 days while ``candles_1h`` is kept
  forever; ``portfolio_equity_snapshots`` likewise by ``resolution``. Their
  monthly leaves live one level down: ``candles_1m_2026_09``.

``INITIAL_MONTHS`` is hardcoded on purpose: a migration replayed at any future
date must produce the same schema, so its bounds must not depend on the clock.
Everything after the last month here belongs to ``create_partitions.py``, which
the analytics worker runs daily and which keeps three months ahead.

Every child — intermediate or leaf — is hardened as it is created:
``harden_partition_sql`` revokes the application roles' access (all traffic goes
through the parent) and, for a child of a tenant parent, enables, forces and
polices RLS on the child itself. Neither privileges nor policies are inherited
from a partitioned parent, which is what let ``DELETE FROM audit_logs_2026_09``
through and what left the same rows readable across tenants.
"""

from __future__ import annotations

from alembic import op

from ddl.tables import TENANT_TABLES
from hunter_core.db.models import (
    create_list_partition_sql,
    create_partition_sql,
    drop_partition_sql,
    harden_partition_sql,
    list_partition_name,
)

PARTITIONED_TABLES: tuple[str, ...] = (
    "audit_logs",
    "feature_snapshots",
    "liquidations",
    "market_snapshots",
    "opportunity_history",
    "system_events",
)
"""Monthly ``RANGE`` parents, frozen as of this revision."""

LIST_PARTITIONED_TABLES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("candles", ("1m", "5m", "15m", "1h", "4h", "1d"), "open_time"),
    ("portfolio_equity_snapshots", ("1m", "5m", "15m", "1h", "4h", "1d"), "ts"),
)
"""``(parent, LIST values, sub-partition key)``, frozen as of this revision.

The values are every ``candle_timeframe`` label, not only the ones the ingestion
writes today: a row whose timeframe has no partition is refused outright, and a
refused write is an outage, not a warning.
"""

INITIAL_MONTHS: tuple[tuple[int, int], ...] = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
)


def _harden(child: str, parent: str) -> None:
    """Revoke, and police, one freshly created child of ``parent``."""
    for statement in harden_partition_sql(
        child,
        tenant=parent in TENANT_TABLES,
        audit_scope=parent == "audit_logs",
    ):
        op.execute(statement)


def create_initial_partitions() -> None:
    """Create ``INITIAL_MONTHS`` under every partitioned parent, then harden."""
    for table in PARTITIONED_TABLES:
        for year, month in INITIAL_MONTHS:
            op.execute(create_partition_sql(table, year, month))
            _harden(f"{table}_{year:04d}_{month:02d}", table)

    for parent, values, sub_key in LIST_PARTITIONED_TABLES:
        for value in values:
            intermediate = list_partition_name(parent, value)
            op.execute(create_list_partition_sql(parent, value, sub_key))
            _harden(intermediate, parent)
            for year, month in INITIAL_MONTHS:
                op.execute(create_partition_sql(intermediate, year, month))
                _harden(f"{intermediate}_{year:04d}_{month:02d}", parent)


def drop_initial_partitions() -> None:
    """Drop the partitions this revision created; the parents go with the tables."""
    for parent, values, _sub_key in reversed(LIST_PARTITIONED_TABLES):
        for value in reversed(values):
            intermediate = list_partition_name(parent, value)
            for year, month in reversed(INITIAL_MONTHS):
                op.execute(drop_partition_sql(intermediate, year, month))
            op.execute(f"DROP TABLE IF EXISTS {intermediate}")
    for table in PARTITIONED_TABLES:
        for year, month in reversed(INITIAL_MONTHS):
            op.execute(drop_partition_sql(table, year, month))
