"""meme moonshot: marks on the pool tape, the venue of a trade, the 10x/25x arms

Twenty-ninth revision. **Two columns** on ``meme_paper_bets`` with three
CHECKs and a backfill the rows imply, **one column** on ``meme_trades`` with a
CHECK added ``NOT VALID`` and validated, and a **seed of three rule sets**
that also retires one. No table, no view, no enum, no RLS policy, no grant
(columns inherit their tables'), and nothing touched in ``0022``–``0028``.

T4.11, on the Lab (``0022``), the lines (``0026``), the wallets (``0027``) and
the live ledger (``0028``): Everton's directive of 12/09/2026 — "pode colocar
valores mais alto para sair num mega ROI, meme coin é diferente". Targets of
2× cut the tail that pays in memes; the Lab gains an arm with 10×/25× targets,
a two-hour horizon and a position that **survives the migration** to PumpSwap,
marked by the pool's own tape (``meme_trades.program = 'pump_amm'``) instead
of sold on the curve's completion. Two pre-registered arms
(``obsidian/05-EXPERIMENTS/EXP-M4-moonshot.md``), both paper, both measured
by the Lab; ``operator/2`` replaces ``operator/1`` with the new suggested
geometry, the approval sheet still editable.

**Upgrade guard: none, and that is an assertion** — every new column is
nullable, the backfill (``mark_source = 'curve'`` where a mark exists) states
what every mark of today was, the CHECKs hold on every row of today and the
seed is ``ON CONFLICT DO NOTHING``. **The downgrade refuses** while a pool
trade, a pool-marked or ``dead``-closed bet, or a reference to the seeded
sets exists (``ddl/meme_moonshot.py``).

**Lock and pooler.** ``ADD COLUMN`` without a volatile default is
catalogue-only; the backfill touches the hundreds of rows of
``meme_paper_bets``; the CHECK on ``meme_trades`` (partitioned, millions of
rows) is ``NOT VALID`` then ``VALIDATE``d under ``SHARE UPDATE EXCLUSIVE``
(the tape keeps inserting). Nothing depends on session state.
**Named ``0029_meme_moonshot`` (18 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §41.

Revision ID: 0029_meme_moonshot
Revises: 0028_meme_live
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_moonshot import (
    add_mark_columns,
    add_trade_program,
    drop_mark_columns,
    drop_trade_program,
    refuse_a_downgrade_that_would_lose_the_pool_tape_or_a_moonshot,
    seed_moonshot_rule_sets,
    unseed_moonshot_rule_sets,
)

revision: str = "0029_meme_moonshot"
down_revision: str | None = "0028_meme_live"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_mark_columns()
    add_trade_program()
    seed_moonshot_rule_sets()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_the_pool_tape_or_a_moonshot()
    unseed_moonshot_rule_sets()
    drop_trade_program()
    drop_mark_columns()
