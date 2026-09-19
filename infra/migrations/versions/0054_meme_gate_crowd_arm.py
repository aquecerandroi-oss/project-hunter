"""meme gate arm of "a rise with people behind it": flow_v2/10, paper only (T4.66)

Revision ID: 0054_meme_gate_crowd_arm
Revises: 0053_meme_launch_lane_arm

EXP-M19 (``obsidian/05-EXPERIMENTS/EXP-M19-subida-com-gente-atras.md``,
Everton 19/09/2026 00:4x BRT): the rise that pays has new wallets coming in
and the first buyers (the snipers of blocks 1–3) holding; the one that does
not is a distribution. The event feed (T4.52b) says who buys and sells, and
T4.66 folds that into four readings (``hunter_indicators.meme.crowd``) the
gate can ask for.

This revision seeds **one** research arm, ``flow_v2/10`` (``…0018``,
``research_only``, ``exp_ref EXP-M19``, 15-second clock): ``flow_v2/6``
(``0044``) plus ``min_early_retention_pct: "0.70"``, ``min_early_age_s: 60``,
``min_new_wallets_30s: 5``, ``max_quick_flip_share_30s: "0.20"`` and **every
other param identical**, which is what makes ``flow_v2/6`` its control. No
schema change, no retirement, and the desk is not touched: the executor only
ever opens proposals of an ``operator`` set (``hunter_meme_executor.auto_approve``
``_OPERATOR_PROPOSED`` selects ``WHERE rs.kind = 'operator' AND rs.status =
'active'``), so a ``research_only`` set is **paper by construction**.

Everything is in ``ddl/meme_gate_crowd_arm.py``; the downgrade refuses while
a proposal, a bet, a param-history row or a sampled refusal references the
seeded set (§17.7), exactly as ``0049``/``0050``/``0052``/``0053`` do.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_crowd_arm import (
    refuse_a_downgrade_that_would_orphan_a_crowd_row,
    seed_crowd_arm,
    unseed_crowd_arm,
)

revision: str = "0054_meme_gate_crowd_arm"
down_revision: str | None = "0053_meme_launch_lane_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_crowd_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_crowd_row()
    unseed_crowd_arm()
