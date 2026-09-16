"""meme gate E2-b arm: flow_v2/6, the forged-fill criterion in paper (T4.31)

Revision ID: 0044_meme_gate_e2b_arm
Revises: 0043_meme_events_scan_cursor

KB-0103 (14–16/09/2026) and KB-0105 (replication in 12–13/09) measured that a
*forged* graduation is a curve that filled within 60 s of the mint **or** a
coin whose largest buyer paid 35 % or more of the SOL bought on the rise:
92–100 % of the forged coins at a cost of 2,0–11,4 % of the organic ones,
against the 35–54 % / 30–51 % of today's E2 (``creator_serial`` /
``symbol_clone``). On the 103 measured paper bets of 12–13/09 the rule would
have refused 41 of them, summing −14,2 R of −18,9 R — on two losing days, so
it is loss avoided and not edge.

This revision seeds **one** research arm, ``flow_v2/6`` (``…0013``,
``research_only``, EXP-M9, 15-second clock): the desk's current calibrated
gate (``ddl/meme_gate_e2b_arm.CALIBRATION_OVERRIDES``) plus
``pedigree_e2b: true``. ``flow_v2/5`` stays active and the desk's
``operator/5`` is untouched — the comparison is the point and the arm is
paper only. Everything is in ``ddl/meme_gate_e2b_arm.py``; the downgrade
refuses while a proposal or a bet references the seeded set (§17.7).
Prediction registered on ``obsidian/05-EXPERIMENTS/EXP-M9-pedigree-e2b.md``:
``descartar``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_e2b_arm import (
    refuse_a_downgrade_that_would_orphan_an_e2b_row,
    seed_e2b_arm,
    unseed_e2b_arm,
)

revision: str = "0044_meme_gate_e2b_arm"
down_revision: str | None = "0043_meme_events_scan_cursor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_e2b_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_e2b_row()
    unseed_e2b_arm()
