"""meme gate arms of "sell absorption": absorb_v0/1 + absorb_v0/2, paper only (T4.79)

Revision ID: 0058_meme_gate_absorb_arm
Revises: 0057_spot_desk

EXP-M22 (``obsidian/05-EXPERIMENTS/EXP-M22-absorcao-de-venda.md``, Astra's
strategy review of 20/09/2026 over R62/R64): a sell ≥ 5 % of the curve's
real SOL is the trigger that precedes the dumps, but alone it does not tell a
dump from a shake-out — the demand that recomposes it does. T4.79 folds that
into a per-mint state machine on the event lane (``hunter_meme_worker.absorb``)
and two switches a set can ask for.

This revision seeds **two** research arms on the 15-second clock, both
``research_only`` under ``exp_ref EXP-M22``: ``absorb_v0/1`` (``…001a``,
``require_absorb_confirmed: true`` — enter only after the price is back at the
pre-sell level within 30 s and held 10 s) and ``absorb_v0/2`` (``…001b``,
``require_absorb_sell_seen: true`` — the control: enter right after the same
sell), **every other param identical**. No schema change, no retirement, and
the desk is not touched: the executor only ever opens proposals of an
``operator`` set (``hunter_meme_executor.auto_approve``'s ``_OPERATOR_PROPOSED``
selects ``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a
``research_only`` set is **paper by construction**.

Everything is in ``ddl/meme_gate_absorb_arm.py``; the downgrade refuses while
a proposal, a bet, a param-history row or a sampled refusal references either
seeded set (§17.7), exactly as ``0049``–``0054`` do.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_absorb_arm import (
    refuse_a_downgrade_that_would_orphan_an_absorb_row,
    seed_absorb_arms,
    unseed_absorb_arms,
)

revision: str = "0058_meme_gate_absorb_arm"
down_revision: str | None = "0057_spot_desk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_absorb_arms()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_absorb_row()
    unseed_absorb_arms()
