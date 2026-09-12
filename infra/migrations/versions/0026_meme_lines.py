"""meme lines: the drawn lines and the hype as columns, probe and scale legs

Twenty-sixth revision. **Thirteen columns** on ``meme_features_1m`` with eight
CHECKs, **two columns** on ``meme_paper_bets`` with a self-referencing foreign
key, two CHECKs and a partial index, and a **seed of two rule sets**. No table,
no view, no enum, no RLS policy, no grant (columns inherit their tables'), and
nothing touched in ``0022``–``0025``.

T4.10, on the Lab ``0022`` committed and the features ``0023``–``0025`` grew:
Everton's directive of 12/09/2026 — every analysed coin must have its lines
drawn (support through the last two local lows, the previous window's high as
resistance, the breakout) as a **computed feature**, and a coin too young to
have a line is not left out: it enters **semi-bought** by hype, a small paper
probe that scales to the full size when the line is born and confirms. Two
pre-registered arms (``obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md``,
``EXP-M3-sonda-de-hype.md``), both paper, both measured by the Lab.

**Upgrade guard: none, and that is an assertion** — every new column is
nullable or defaulted (``leg = 'single'``), every CHECK is scoped so a row of
today satisfies it, and the seed is ``ON CONFLICT DO NOTHING``. **The downgrade
refuses** while a bet carries a leg or a parent, a feature row carries a line,
or the seeded sets are referenced (``ddl/meme_lines.py``).

**Lock and pooler.** ``ADD COLUMN`` without a volatile default is
catalogue-only; the CHECKs on ``meme_features_1m`` are ``NOT VALID`` then
``VALIDATE``d under ``SHARE UPDATE EXCLUSIVE`` (the fold keeps inserting);
``meme_paper_bets`` holds hundreds of rows. Nothing depends on session state.
**Named ``0026_meme_lines`` (15 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §38.

Revision ID: 0026_meme_lines
Revises: 0025_meme_mayhem_denominator
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_lines import (
    add_bet_legs,
    add_line_columns,
    drop_bet_legs,
    drop_line_columns,
    refuse_a_downgrade_that_would_lose_a_line_or_a_leg,
    seed_line_rule_sets,
    unseed_line_rule_sets,
)

revision: str = "0026_meme_lines"
down_revision: str | None = "0025_meme_mayhem_denominator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_line_columns()
    add_bet_legs()
    seed_line_rule_sets()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_line_or_a_leg()
    unseed_line_rule_sets()
    drop_bet_legs()
    drop_line_columns()
