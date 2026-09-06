"""outbox: the pending index becomes the drain order

One thing, in both queues: ``ix_outbox_events_pending`` and
``ix_shadow_outbox_pending`` go from ``(id) WHERE dispatched_at IS NULL`` to
``(created_at, id) WHERE dispatched_at IS NULL``.

The predicate is unchanged and was never the problem — ``dispatched_at IS
NULL`` is what "pending" means and no watermark over ``id`` could replace it.
What was wrong is the *key*: ``claim_pending`` orders by ``(created_at, id)``
because the sequence has gaps and its order is not commit order, so an index on
``id`` alone forced a sort of the entire pending set on every sweep. Measured
with ``EXPLAIN ANALYZE`` of the real claim on Postgres 16 with 30k pending
rows: **15.255 ms** before (Seq Scan over all 30k rows plus a 3.5 MB
quicksort), **0.237 ms** after (Index Scan stopping at the 20 rows asked for).
Rationale, and the reason both queues move together: ``ddl/outbox_index.py``.

**This revision does not run in a transaction.** ``outbox_events`` is a hot
write path, so the rebuild is ``CREATE INDEX CONCURRENTLY`` under a staging
name, ``DROP INDEX CONCURRENTLY`` of the old one, then ``ALTER INDEX ...
RENAME``; none of those may run inside a transaction block, so
``rebuild_pending_indexes`` opens an ``autocommit_block``. A crash halfway is
recovered by rerunning the revision, which is idempotent — see the function's
docstring for the whole trade.

Nothing about identity, retention or delivery changes here; ``downgrade()``
puts both indexes back on ``(id)``, the same way, and is tested.

Revision ID: 0004_outbox_pending_index
Revises: 0003_analysis
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.outbox_index import (
    DRAIN_ORDER_0004,
    LEGACY_ORDER_0004,
    PENDING_INDEXES_0004,
    rebuild_pending_indexes,
)

revision: str = "0004_outbox_pending_index"
down_revision: str | None = "0003_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    rebuild_pending_indexes(PENDING_INDEXES_0004, DRAIN_ORDER_0004)


def downgrade() -> None:
    rebuild_pending_indexes(PENDING_INDEXES_0004, LEGACY_ORDER_0004)
