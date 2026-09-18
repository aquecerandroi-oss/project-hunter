"""meme gate arm of "do not enter after the fall": flow_v2/9, paper only (T4.61a)

Revision ID: 0052_meme_gate_after_drop_arm
Revises: 0051_meme_treasury_swaps

KB-0118 (16/09/2026) read 613 entries of the live gate over 5 days against
the curve's own photos: entries made after the real SOL fell ≥ 50 % from a
peak at most 60 s old were the **only** negative cell (−0,305 R, tail 4,1 %
against ~13 %), while the same fall with an older peak was the best cell of
all. R56 (18/09) then found the desk's first real buys of 17→18/09 to be
**7 of 7** after a drop. Everton (18/09, 15:0x BRT): use the intelligence
already acquired and operate now. The in-sample Δ (+0,038 R) chose X and N
among nine combinations on the same sample (KB-0092), so EXP-M13's
registered default prediction is ``descartar``.

This revision seeds **one** research arm, ``flow_v2/9`` (``…0016``,
``research_only``, ``exp_ref EXP-M13``, 15-second clock): ``flow_v2/6``
(``0044``) plus ``max_recent_drawdown_pct: "0.50"`` and **every other param
identical**, which is what makes ``flow_v2/6`` its control. No schema change,
no retirement, and the desk is not touched: the executor only ever opens
proposals of an ``operator`` set (``hunter_meme_executor.auto_approve``
``_OPERATOR_PROPOSED`` selects ``WHERE rs.kind = 'operator' AND rs.status =
'active'``), so a ``research_only`` set is **paper by construction**.

Everything is in ``ddl/meme_gate_after_drop_arm.py``; the downgrade refuses
while a proposal, a bet, a param-history row or a sampled refusal references
the seeded set (§17.7), exactly as ``0049``/``0050`` do. Five declarations
(``/9`` and not the page's ``/8``; this 29-character slug and not the brief's
38; the ``pedigree_e2b`` the base carries; why ``gate_version`` stays 3; the
120 s fill behind the 60 s gate window) are written in that module, in
EXP-M13 and in ``docs/DATABASE.md`` § 59.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_after_drop_arm import (
    refuse_a_downgrade_that_would_orphan_an_after_drop_row,
    seed_after_drop_arm,
    unseed_after_drop_arm,
)

revision: str = "0052_meme_gate_after_drop_arm"
down_revision: str | None = "0051_meme_treasury_swaps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_after_drop_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_after_drop_row()
    unseed_after_drop_arm()
