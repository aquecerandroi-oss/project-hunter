"""meme gate arm of the REFUSED coins: refused_probe_v0/1, paper only (T4.85)

Revision ID: 0060_meme_refused_probe_arm
Revises: 0059_market_events

EXP-M23 (``obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md``, frozen
on 23/09/2026, Emenda 1 the same day), born out of R69: the desk has 41 905
recorded refusals and **not one measured outcome**. Until the lower row of the
2×2 has numbers in it, a gate that SELECTS and a gate that merely bets LESS
OFTEN look exactly alike in our data.

This revision seeds **one** arm, ``refused_probe_v0/1`` (``…001c``),
``research_only`` under ``exp_ref EXP-M23``, on its own clock ``refused``.
Its population is not a series: it is the mints the operator gate refused in a
tick and no arm admitted, sampled with a frozen seed and a **recorded**
inclusion probability (stratum A, a single failed criterion: 10 %, 50 % for a
rare reason; stratum B, two or more: 0,1 % and 0,5 %) — the sampler and those
four rates are frozen in ``hunter_meme_worker.refused_probe``, never in params,
so moving one is a new arm rather than an edit of a live row.

**No schema change, no retirement, and the desk is not touched.** The executor
only ever opens proposals of an ``operator`` set
(``hunter_meme_executor.auto_approve``'s ``_OPERATOR_PROPOSED`` selects
``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a
``research_only`` set is **paper by construction**; and no existing gate step
selects ``clock = 'refused'``. The control arm is ``operator/6`` itself
(``0055``), whose approved proposals already become paper bets with the same
0,07 SOL / 1,15× / 300 s / trailing 10 % armed at the entry — seeding a second
mirror would add a population, not a control.

Everything is in ``ddl/meme_refused_probe_arm.py``; the downgrade refuses while
a proposal, a bet, a param-history row or a sampled refusal references the
seeded set (§17.7), exactly as ``0049``–``0058`` do — and here the guard is
worth more than usual, because a probe proposal's ``reasons`` is the only copy
of that mint's refusal reasons, its stratum and its inclusion probability.

**Named ``0060_meme_refused_probe_arm`` (26 characters)** — ``VARCHAR(32)``
(§17.6). ``down_revision`` is ``0059_market_events`` (T4.82), which was
uncommitted but in flight when this task started; ``0058_meme_gate_absorb_arm``
(T4.79) sits under it, likewise uncommitted. Neither file is touched here.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_refused_probe_arm import (
    refuse_a_downgrade_that_would_orphan_a_probe_row,
    seed_refused_probe_arm,
    unseed_refused_probe_arm,
)

revision: str = "0060_meme_refused_probe_arm"
down_revision: str | None = "0059_market_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_refused_probe_arm()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_probe_row()
    unseed_refused_probe_arm()
