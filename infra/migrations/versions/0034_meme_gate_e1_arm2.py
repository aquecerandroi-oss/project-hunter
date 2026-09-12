"""meme gate E1 arm 2: flow_v2/2 and operator/4 with the funnel's thresholds (T4.21)

Revision ID: 0034_meme_gate_e1_arm2
Revises: 0033_meme_operator_3

The E1 gate frozen as ``flow_v2/1`` / ``operator/3`` requires ``snipers ≤ 2``
and no mint with real demand has fewer than six (measured 12/09/2026 18:3x–
19:0x BRT, ``infra/scripts/sql/research/2026-09-12-t421-funil-e1.sql``): zero
proposals since 18:44. This revision seeds the second arm — ``max_snipers 10``,
``min_holders 20``, holders not falling instead of rising, an unknown creator
vouched for by a measured ``dev_share``, the 60 s market-cap delta as an
alternative to progress rising — as ``flow_v2/2`` (research, EXP-M5 arm 2,
prediction ``descartar``) and ``operator/4`` (the desk, ``ttl_s 180``), retiring
``operator/3``. ``flow_v2/1`` stays active for the comparison. Everything is in
``ddl/meme_gate_e1_arm2.py``; the downgrade refuses while a proposal or a bet
references either seeded set (§17.7) and revives ``operator/3``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_e1_arm2 import (
    refuse_a_downgrade_that_would_orphan_an_arm2_row,
    seed_e1_arm2,
    unseed_e1_arm2,
)

revision: str = "0034_meme_gate_e1_arm2"
down_revision: str | None = "0033_meme_operator_3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_e1_arm2()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_arm2_row()
    unseed_e1_arm2()
