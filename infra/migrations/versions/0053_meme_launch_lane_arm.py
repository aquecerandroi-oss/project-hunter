"""meme launch lane: launch_v0/1, paper only (T4.67a)

Revision ID: 0053_meme_launch_lane_arm
Revises: 0052_meme_gate_after_drop_arm

Everton, 2026-09-19 00:3x BRT: "assim que a moeda é criada dá um pico; se
comprarmos assim que começa a subir conseguimos comprar no lançamento e
vender na alta rápida?" — EXP-M18's pre-registration
(``obsidian/05-EXPERIMENTS/EXP-M18-sniper-de-lancamento.md``).

This revision seeds **one** rule set, ``launch_v0/1`` (``…0017``,
``research_only``, ``exp_ref EXP-M18``, ``clock = "event"``): a size of 0,01
SOL, a creator-buy ceiling of 2 SOL, a fixed +6 s/first-third-party-sell exit
(``exit_key = "lancamento_6s_ou_primeiro_sell"``) and a 20 % drawdown-from-peak
guard; the desk is untouched (only a ``kind = 'operator'`` set ever reaches
the executor, ``hunter_meme_executor.auto_approve``'s own ``_OPERATOR_PROPOSED``
query). One schema change: ``meme_paper_bets.mark_source``'s own CHECK widens
from ``{curve, pool_tape}`` to ``{curve, pool_tape, solana_ws}`` — the launch
lane's own reconstruction of the curve from a chain event, never a
``meme_curve_snapshots`` row — and is never narrowed back on downgrade.

Everything is in ``ddl/meme_launch_lane_arm.py``; the downgrade refuses while
a proposal, a bet, a param-history row or a sampled refusal references the
seeded set (§17.7), exactly as ``0049``/``0050``/``0052`` do.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_launch_lane_arm import (
    refuse_a_downgrade_that_would_orphan_a_launch_lane_row,
    seed_launch_lane_arm,
    unseed_launch_lane_arm,
    widen_mark_source,
)

revision: str = "0053_meme_launch_lane_arm"
down_revision: str | None = "0052_meme_gate_after_drop_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    widen_mark_source()
    seed_launch_lane_arm()


def downgrade() -> None:
    """Refuse first, then unwind the seed — the widened ``mark_source`` CHECK
    is never narrowed back (a bet already marked ``solana_ws`` must keep a
    CHECK that explains it)."""
    refuse_a_downgrade_that_would_orphan_a_launch_lane_row()
    unseed_launch_lane_arm()
