"""meme boards and trades: the site's boards, the risk reads, the tape columns

Twenty-third revision. **Two tables** (both monthly ``RANGE`` parents), three
indexes, eight partitions, fifteen columns and nine CHECKs added to
``meme_features_1m``, one column relaxed on ``meme_trades``, grants by
subtraction. No enum, no RLS policy, no view changed, nothing touched in
``0022``.

T4.2c, on the storage T4.2 committed (``0021_meme_radar``) and the Lab T4.6
committed (``0022_meme_lab``): the second collector of the meme radar reads the
site's own screener boards (``wss://advanced-indexer.pump.fun/ws/trenches``:
holders, top-10 %, dev %, snipers, buys/sells, live, socials — per coin, per
second, no key) and the trade tape of ``swap-api.pump.fun`` (1000 req/60 s,
with a cursor), which is what fills the four feature columns ``0021`` left
``NULL`` with a reason and adds the ones the EXP-M1 gate refuses every row
without today (``creator_net_seller``, ``curve_volume_1m_sol``).

**Global, RLS-free** (DATABASE.md §1.1), like the nine ``meme_*`` tables
before: a board is what everybody sees, a trade belongs to the chain. The
``LIKE 'meme%'`` tests of ``0021`` assert the absence for these two as well.

**Why ``meme_trades.commitment`` becomes nullable here** and not in a revision
of its own: the column was written ``NOT NULL`` for an on-chain decoder that
states finality on every read; the producer that actually landed states none,
and a producer forced to write ``confirmed`` it never observed would be the
silent claim Astra's MUST-FIX 2 forbids. ``NULL`` is the same word
``meme_curve_snapshots.commitment`` already uses for the REST mirror.

**No upgrade guard, and that is an assertion**: ``ADD COLUMN`` of nullable
columns without defaults and ``DROP NOT NULL`` make no stored row
unrepresentable. **The downgrade refuses** while either new table holds a row,
while a feature row carries a ``0023`` column, or while a trade carries a
``NULL`` commitment (``ddl/meme_boards_guards.py``).

**Lock and pooler.** ``CREATE TABLE`` takes no lock on a relation that does not
yet exist; ``ADD COLUMN`` of a nullable column without a default and ``DROP NOT
NULL`` are catalogue-only in PostgreSQL 16 (no rewrite); ``ADD CONSTRAINT ...
CHECK`` scans the table once under ``SHARE ROW EXCLUSIVE`` — on
``meme_features_1m`` that is a scan of the rows of today, seconds, and the
collector's inserts wait for it. Nothing depends on session state. **Named
``0023_meme_boards_trades`` (23 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §35.

Revision ID: 0023_meme_boards_trades
Revises: 0022_meme_lab
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_boards import (
    create_meme_boards_partitions,
    create_meme_boards_tables,
    drop_meme_boards_tables,
    grant_meme_boards_privileges,
)
from ddl.meme_boards_guards import (
    add_feature_columns,
    drop_feature_columns,
    refuse_a_downgrade_that_would_lose_meme_boards_rows,
    relax_trade_commitment,
    restore_trade_commitment,
)

revision: str = "0023_meme_boards_trades"
down_revision: str | None = "0022_meme_lab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_boards_tables()
    create_meme_boards_partitions()
    add_feature_columns()
    relax_trade_commitment()
    grant_meme_boards_privileges()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_meme_boards_rows()
    restore_trade_commitment()
    drop_feature_columns()
    drop_meme_boards_tables()
