"""meme organic E3: the slow-organic arm that enters later and holds through migration (T4.22)

Revision ID: 0035_meme_organic_e3
Revises: 0034_meme_gate_e1_arm2

Every live set buys 30–300 s after creation and 31 of 35 measured closes of
12/09/2026 never traded above the entry. ``organic_v0/1`` (EXP-M7, prediction
``descartar``) enters on the closed minute when the curve crosses 10–30 % with
≥ 20 holders rising, top-10 ≤ 30 %, snipers ≤ 2, dev ≤ 10 %, creator not a net
seller, and holds through migration (target 5×, trailing 40 % after 2×, 60 min).
Everything is in ``ddl/meme_organic_e3.py``; the downgrade refuses while a
proposal or a bet references the set (§17.7).
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_organic_e3 import (
    refuse_a_downgrade_that_would_orphan_an_organic_row,
    seed_organic_e3,
    unseed_organic_e3,
)

revision: str = "0035_meme_organic_e3"
down_revision: str | None = "0034_meme_gate_e1_arm2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_organic_e3()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_organic_row()
    unseed_organic_e3()
