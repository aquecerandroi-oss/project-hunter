"""meme gate arm of the entry at the pullback: recuo_v1/1, paper only (T4.91)

Revision ID: 0063_meme_pullback_entry_arm
Revises: 0062_meme_decision_tapes

EXP-M24 (``obsidian/05-EXPERIMENTS/EXP-M24-entrada-no-recuo.md``, H-017 of
``obsidian/11-KNOWLEDGE/Fila de Hipoteses.md``): R77 refuted H-016 (waiting
for a 5 % pullback does not pay, ``KB-0157``) but its best cell — 3 % / 60 s,
+2,28 pp per SOL in paper, from the entry price — is a lead that can only be
judged on a new cohort. T4.91 built the entry at the pullback, **off by
default** (``hunter_meme_worker.entry_pullback``: a set without
``entry_pullback_pct`` proposes exactly as before); this revision seeds the
one paper arm that turns it on, on the decisions made after the deploy.

**One arm, no schema change, nothing retired, the desk untouched.**
``recuo_v1/1`` (``…001d``) is ``research_only`` under ``exp_ref EXP-M24``,
``operator/5``'s effective params (copied in the same statement — see
``ddl/meme_pullback_entry_arm.py`` for why, unlike ``0055``/``0060``, it reads
the live row) with the desk's exit/size restated, paper ceilings, and
``entry_pullback_pct "3"`` / ``entry_pullback_window_s 60``. The executor only
ever opens proposals of an ``operator`` set, so the arm is paper by
construction. The upgrade refuses when ``operator/5`` is missing or not
active; the downgrade refuses while a proposal, a bet, a param-history row or
a sampled refusal references the arm (§17.7).
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_pullback_entry_arm import (
    refuse_a_downgrade_that_would_orphan_a_pullback_row,
    seed_pullback_arm,
    unseed_pullback_arm,
)

revision: str = "0063_meme_pullback_entry_arm"
down_revision: str | None = "0062_meme_decision_tapes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_pullback_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_pullback_row()
    unseed_pullback_arm()
