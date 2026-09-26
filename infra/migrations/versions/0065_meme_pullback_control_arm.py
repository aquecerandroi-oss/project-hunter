"""meme gate arm: recuo_ctrl_v1/1, the immediate-entry control of recuo_v1/1 (T4.95)

Revision ID: 0065_meme_pullback_control_arm
Revises: 0064_meme_tokens_symbol_index

EXP-M25 (``obsidian/05-EXPERIMENTS/EXP-M25-controle-do-recuo.md``) supplies the
control H-017 (EXP-M24) lacked: R79 found ``operator/5``'s paper shadow exists
only when the real desk accepts, so 132 of 171 ``recuo_v1/1`` armings had no
pair. This revision seeds ``recuo_ctrl_v1/1`` (``…001e``), ``research_only``,
``recuo_v1/1``'s live params minus ``entry_pullback_pct`` /
``entry_pullback_window_s`` (the entry is immediate at ``t0``), copied in the
same statement the guard checks. **One arm, no schema change, nothing retired,
the desk untouched.** The upgrade refuses when ``recuo_v1/1`` is missing, not
active or not on the ``15s`` clock; the downgrade refuses while a proposal, a
bet, a param-history row or a sampled refusal references the control (§17.7).
Everything is in ``ddl/meme_pullback_control_arm.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_pullback_control_arm import (
    refuse_a_downgrade_that_would_orphan_a_control_row,
    seed_pullback_control,
    unseed_pullback_control,
)

revision: str = "0065_meme_pullback_control_arm"
down_revision: str | None = "0064_meme_tokens_symbol_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_pullback_control()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_control_row()
    unseed_pullback_control()
