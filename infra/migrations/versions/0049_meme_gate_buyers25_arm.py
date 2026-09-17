"""meme gate arm of the 25 unique buyers: flow_v2/7, paper only (T4.48)

Revision ID: 0049_meme_gate_buyers25_arm
Revises: 0048_meme_creator_initial_buy

KB-0112 §4 (16/09/2026) found ``unique_buyers`` to be the only variable of the
minute with a tail signal (Spearman with ``R >= +2`` = +0,153, p = 0,004) and
KB-0114 measured the seven floors over 345 entries in 5 days: ``>= 25`` adds
**+0,090 R** ([+0,038; +0,201]) over today's floor of 10, is the only floor whose
gain survives leave-one-day-out, and still leaves 273 bets in 5 days — enough for
the ruler to close. Every number is in-sample (KB-0092), so EXP-M10's registered
default prediction is ``descartar``.

This revision seeds **one** research arm, ``flow_v2/7`` (``…0014``,
``research_only``, ``exp_ref EXP-M10``, 15-second clock): ``flow_v2/6``
(``0044``) with ``min_unique_buyers`` 10 → 25 and **every other param
identical**, which is what makes ``flow_v2/6`` its control. No schema change, no
retirement, and the desk is not touched: the executor only ever opens proposals
of an ``operator`` set (``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED``
selects ``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a
``research_only`` set is **paper by construction** — this arm can never reach
real money.

Everything is in ``ddl/meme_gate_buyers25_arm.py``; the downgrade refuses while a
proposal, a bet, a param-history row or a sampled refusal references the seeded
set (§17.7), exactly as ``0044`` does, with ``0046``'s two tables added to the
list. Two declarations (the ``pedigree_e2b`` the base carries, and why
``gate_version`` stays 3) are written in that module, in EXP-M10 and in
``docs/DATABASE.md`` §57.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_buyers25_arm import (
    refuse_a_downgrade_that_would_orphan_a_buyers25_row,
    seed_buyers25_arm,
    unseed_buyers25_arm,
)

revision: str = "0049_meme_gate_buyers25_arm"
down_revision: str | None = "0048_meme_creator_initial_buy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_buyers25_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_buyers25_row()
    unseed_buyers25_arm()
