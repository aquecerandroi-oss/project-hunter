"""The pending index of the two outbox queues — DATABASE.md §16.4/§17.5.

``0002`` and ``0003`` each shipped their queue with ``INDEX (id) WHERE
dispatched_at IS NULL``. The dispatcher does not claim in ``id`` order and
never could: the sequence has gaps and its order is not commit order, so
``claim_pending`` orders by ``(created_at, id)``. An index whose key is ``id``
alone can still *find* the pending rows, but it cannot deliver them in the
order asked for — and once a sort is unavoidable the planner stops using the
index at all.

Measured (``EXPLAIN ANALYZE`` of the real claim, Postgres 16, 30k pending
rows): with ``(id)`` it is a **Seq Scan over all 30k rows plus a 3.5 MB
quicksort**, 15.255 ms; with ``(created_at, id)`` it is an Index Scan that
stops after the 20 rows asked for, 0.237 ms. At the readiness ceiling of 500
pending rows the difference is noise — this matters exactly when it hurts,
during the backlog a Redis outage leaves behind, which is also when the sweep
must drain fastest.

Both queues are changed together on purpose: they are shape-identical by
design (the absorption of ``shadow_outbox`` is an ``INSERT ... SELECT``), and
letting their indexes diverge would make one of the two silently slower for no
reason anybody could later reconstruct.

**Everything a revision reads from here is frozen per revision**
(``PENDING_INDEXES_0004``, ``DRAIN_ORDER_0004``, ``LEGACY_ORDER_0004``), the
same rule ``ddl/tables.py``, ``ddl/shadow.py``, ``ddl/analysis.py`` and
``ddl/enums.py`` follow and for the reason DATABASE.md §16.5 names: a live list
read at migration time is retroactive. A ``0005`` that adds an
``execution_outbox`` queue and appends it to a shared ``PENDING_INDEXES`` would
make ``0004`` — which had two indexes to rebuild the day it was written — try
to rebuild a third that does not exist at its point in the history, and fail on
every clean database. A new queue brings its own tuple; ``0004``'s never grows.
"""

from __future__ import annotations

from alembic import op

PENDING_PREDICATE = "dispatched_at IS NULL"
"""What "pending" means, in every queue. Never a watermark over ``id``.

Not frozen per revision, because it is not a list that grows: it is the
definition of the debt itself (DATABASE.md §1.3, §16.4). A revision that
changed it would not be adding a queue, it would be changing what the outbox
promises, and would say so in its own SQL.
"""

STAGING_SUFFIX = "_rebuilding"
"""Suffix of the name the new index is built under before it takes over.

The rebuild is not transactional (see :func:`rebuild_pending_indexes`), so the
intermediate state is observable and needs a name that says what it is.
"""

PENDING_INDEXES_0004: tuple[tuple[str, str], ...] = (
    ("outbox_events", "ix_outbox_events_pending"),
    ("shadow_outbox", "ix_shadow_outbox_pending"),
)
"""``(table, index)`` — the two queues that existed when ``0004`` was written."""

DRAIN_ORDER_0004: tuple[str, ...] = ("created_at", "id")
"""The key ``0004`` installs — the dispatcher's own ``ORDER BY``."""

LEGACY_ORDER_0004: tuple[str, ...] = ("id",)
"""The key ``0002``/``0003`` created, restored by ``0004``'s downgrade."""

__all__ = [
    "DRAIN_ORDER_0004",
    "LEGACY_ORDER_0004",
    "PENDING_INDEXES_0004",
    "PENDING_PREDICATE",
    "STAGING_SUFFIX",
    "rebuild_pending_indexes",
]


def _create(table: str, index: str, columns: tuple[str, ...]) -> str:
    keyed = ", ".join(columns)
    return (
        f"CREATE INDEX CONCURRENTLY {index} ON {table} "
        f"USING btree ({keyed}) WHERE {PENDING_PREDICATE}"
    )


def rebuild_pending_indexes(
    indexes: tuple[tuple[str, str], ...], columns: tuple[str, ...]
) -> None:
    """Re-key every pending index in ``indexes`` onto ``columns``, concurrently.

    ``outbox_events`` is a hot write path: every business transaction of the
    market-worker inserts into it (order of 700k rows/day, DATABASE.md §1.3),
    and the dispatcher writes to it on every sweep. A plain ``DROP INDEX`` plus
    ``CREATE INDEX`` takes an ``ACCESS EXCLUSIVE`` lock on the table and builds
    the replacement while holding it, so for the length of the build *every*
    producer blocks — and the readiness ceiling of 500 pending rows does not
    bound that work, because it is an alarm rather than a physical limit and it
    counts only the pending rows, while the build scans the whole table,
    dispatched history included (Astra, T2.9b review).

    So the rebuild never holds a lock over a build:

    1. ``CREATE INDEX CONCURRENTLY`` under a staging name — readers and writers
       keep going, the old index keeps serving the claim;
    2. ``DROP INDEX CONCURRENTLY`` on the old one, so the queue is never
       without an index the planner can use;
    3. ``ALTER INDEX ... RENAME`` — a catalog-only lock, held for microseconds.

    The price, stated because it is real: **this revision is not atomic.** None
    of the three commands may run inside a transaction block, so they run in
    :meth:`~alembic.runtime.migration.MigrationContext.autocommit_block`, which
    commits whatever came before it and reverts to autocommit. A crash halfway
    leaves a staging index behind, possibly ``indisvalid = false`` — which is
    why every step starts by dropping the staging name ``IF EXISTS``: rerunning
    the revision is the recovery, and rerunning it is idempotent, including
    over a successful previous run.
    """
    with op.get_context().autocommit_block():
        for table, index in indexes:
            staging = f"{index}{STAGING_SUFFIX}"
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {staging}")
            op.execute(_create(table, staging, columns))
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index}")
            op.execute(f"ALTER INDEX {staging} RENAME TO {index}")
