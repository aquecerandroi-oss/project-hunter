"""meme gate arm of the 1.0 sells/buys ceiling: flow_v2/8, paper only (T4.49)

Revision ID: 0050_meme_gate_ratio10_arm
Revises: 0049_meme_gate_buyers25_arm

R48 (17/09/2026 01:51 BRT) read 24 h of ``meme_features_1m`` and found the live
ceiling of 0,6 on sells/buys discarding 113 of 459 graduated coins (24,6 %),
with the graduation rate 4× lower below 0,6 (0,53 % against 2,12 %) and peaking
at 2,21 % in the 1,0–1,5 bucket. R51 agreed from the other side (dropping the
criterion: +9 graduated for +5 losers). Both are one day, in-sample, with
``buy_sell_ratio`` NULL on 340 of the 459 graduated (KB-0092), so EXP-M14's
registered default prediction is ``descartar``.

This revision seeds **one** research arm, ``flow_v2/8`` (``…0015``,
``research_only``, ``exp_ref EXP-M14``, 15-second clock): ``flow_v2/6``
(``0044``) with ``max_sells_to_buys`` "0.6" → "1.0" and **every other param
identical**, which is what makes ``flow_v2/6`` its control. No schema change, no
retirement, and the desk is not touched: the executor only ever opens proposals
of an ``operator`` set (``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED``
selects ``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a
``research_only`` set is **paper by construction** — this arm can never reach
real money.

Everything is in ``ddl/meme_gate_ratio10_arm.py``; the downgrade refuses while a
proposal, a bet, a param-history row or a sampled refusal references the seeded
set (§17.7), exactly as ``0049`` does. Four declarations (the key is
``max_sells_to_buys`` and not the page's ``max_sell_buy_ratio``, the slug the
page predicted, the ``pedigree_e2b`` the base carries, and why ``gate_version``
stays 3) are written in that module, in EXP-M14 and in ``docs/DATABASE.md``
§ 58.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_ratio10_arm import (
    refuse_a_downgrade_that_would_orphan_a_ratio10_row,
    seed_ratio10_arm,
    unseed_ratio10_arm,
)

revision: str = "0050_meme_gate_ratio10_arm"
down_revision: str | None = "0049_meme_gate_buyers25_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_ratio10_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_ratio10_row()
    unseed_ratio10_arm()
