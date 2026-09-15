"""meme E1 sibling arms: snipers > 2 and top-10 medium, measured beside the live sets (T4.23)

Revision ID: 0037_meme_e1_arms_3_4
Revises: 0036_meme_creator_watch

The daily close of 13/09/2026 (§6.4/§6.5, repeated by the 14/09 lot) measured
``snipers > 2`` at R mean +0,25 (n = 17) against −0,28 elsewhere (n = 49) and
``top10_share`` 0,1767–0,257 at +0,25 (n = 14) against −0,25 elsewhere
(n = 52) — both contradict E1's own pre-registration (``snipers <= 2``, no
floor on ``top10_share``). Per the ruler this does not move the live sets: it
plants ``flow_v2/3`` (arm 2 + ``min_snipers 3``) and ``flow_v2/4`` (arm 2 +
``min_top10_share``/``max_top10_share``), both ``research_only``, EXP-M5,
prediction ``descartar``, judged on the same 15-second clock as arms 1 and 2.
Everything is in ``ddl/meme_e1_arms_3_4.py``; the downgrade refuses while a
proposal or a bet references either seeded set (§17.7). Nothing retires.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_e1_arms_3_4 import (
    refuse_a_downgrade_that_would_orphan_an_arm3_or_arm4_row,
    seed_e1_arms_3_4,
    unseed_e1_arms_3_4,
)

revision: str = "0037_meme_e1_arms_3_4"
down_revision: str | None = "0036_meme_creator_watch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_e1_arms_3_4()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_arm3_or_arm4_row()
    unseed_e1_arms_3_4()
