"""meme mature opportunities: EXP-M26's first opportunity per (rule set, mint)

Revision ID: 0066_meme_mature_opportunities
Revises: 0065_meme_pullback_control_arm

R1 of EXP-M26 (``docs/design/exp-m26-grafico-moedas-maduras.md`` §1.6, §7;
H-022). **One new table**, ``meme_mature_opportunities``, everything in
``ddl/meme_mature_opportunities.py``: no column on an existing table, no view,
no enum, no RLS policy (global, §1.1), no partition, no retention until H-022
is read (``docs/DATABASE.md`` §68). No rule set is seeded here — the writer
works with zero EXP-M26 sets (the seed is ``0068``).

Upgrade guard: none, and that is an assertion — the table is new. The
downgrade refuses while a row exists (§17.7). **Named
``0066_meme_mature_opportunities`` (30 characters)** — ``VARCHAR(32)`` (§17.6).

Create Date: 2026-09-26
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_mature_opportunities import (
    create_meme_mature_opportunities,
    drop_meme_mature_opportunities,
    grant_meme_mature_opportunities_privileges,
    refuse_a_downgrade_that_would_lose_an_opportunity,
)

revision: str = "0066_meme_mature_opportunities"
down_revision: str | None = "0065_meme_pullback_control_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_mature_opportunities()
    grant_meme_mature_opportunities_privileges()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_an_opportunity()
    drop_meme_mature_opportunities()
