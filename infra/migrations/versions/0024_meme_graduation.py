"""meme graduation: four completion signals, the denominator's provenance, the matrix

Twenty-fourth revision. **Six nullable columns** on ``meme_tokens``, four
CHECKs, one trigger function replaced, one view replaced with columns
appended, one view created, one backfill from the evidence tables, no new
table, no enum, no RLS policy, nothing touched in ``0022``/``0023``.

T4.2d, on the boards collector T4.2c committed (``0023_meme_boards_trades``):
the plantão measured that the REST ``complete = true`` is **not** a
graduation (77 of 140 "complete" coins carried a zero reserve; 72 were absent
from the ``graduated`` board), and that the denominator of progress was
written only from a virgin photo (117/123 gate rows ``progress_unknown``).
``meme_tokens`` gains ``rest_complete_seen_at``, ``curve_filled_seen_at``,
``graduated_board_seen_at``, ``pool_created_at``/``pool_created_source`` and
``progress_denominator_source``; ``completed_at`` becomes the earliest of the
four (a REST complete with a zero reserve counting for nothing on its own) and
may only ever move earlier. ``meme_graduation_matrix_v1`` is the agreement
matrix per Brasília day — the M-D1/M-D2 diagnostic as a panel.

**The backfill reads the evidence this database already holds** (snapshots
that said complete, board minutes, the ``migrate`` frames kept as
``migrated_at``) and writes nothing it cannot point at; the fill threshold
needs the ``/global-params`` record a migration does not read, so
``curve_filled_seen_at`` starts at the deploy. The ``0021`` write-once trigger
is **disabled for the backfill** and enabled again: the one statement that
must move ``completed_at`` (to an earlier signal, or to NULL for a REST-only
zero-reserve coin) is the statement that redefines the column.

**Upgrade guard: none, and that is an assertion** — nullable columns without
defaults make no stored row unrepresentable, and the CHECKs are added *after*
the backfill that satisfies them. **The downgrade refuses** while any row
carries a completion signal or a ``global_params`` denominator
(``ddl/meme_graduation.py``).

**Lock and pooler.** ``ADD COLUMN`` of a nullable column without a default is
catalogue-only in PostgreSQL 16; the backfill is a handful of set-based
``UPDATE``s over ``meme_tokens`` (~40 k rows/day, pruned at 90 days) with one
``min()`` per mint over the snapshots that said complete (a scan of
``meme_curve_snapshots``, ~90 k rows/day — seconds) and one over
``meme_board_observations``; ``ADD CONSTRAINT ... CHECK`` scans
``meme_tokens`` once under ``SHARE ROW EXCLUSIVE``, and the collector's
upserts wait for it. ``CREATE OR REPLACE VIEW`` takes ``ACCESS EXCLUSIVE`` on
the view for the duration of a catalogue write. Nothing depends on session
state. **Named ``0024_meme_graduation`` (20 characters)** — ``VARCHAR(32)``
(§17.6). Described in ``docs/DATABASE.md`` §36.

Revision ID: 0024_meme_graduation
Revises: 0023_meme_boards_trades
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_graduation import (
    add_graduation_checks,
    add_graduation_columns,
    backfill_graduation_signals,
    create_graduation_views,
    create_meme_token_guards_0024,
    drop_graduation_checks,
    drop_graduation_columns,
    refuse_a_downgrade_that_would_lose_a_completion_signal,
    restore_radar_view_0021,
)
from ddl.meme_radar_guards import create_meme_token_guards

revision: str = "0024_meme_graduation"
down_revision: str | None = "0023_meme_boards_trades"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_graduation_columns()
    backfill_graduation_signals()
    add_graduation_checks()
    create_meme_token_guards_0024()
    create_graduation_views()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``.

    ``create_meme_token_guards`` is ``0021``'s own installer: the write-once
    function goes back to the list that revision froze, ``completed_at`` included.
    """
    refuse_a_downgrade_that_would_lose_a_completion_signal()
    restore_radar_view_0021()
    create_meme_token_guards()
    drop_graduation_checks()
    drop_graduation_columns()
