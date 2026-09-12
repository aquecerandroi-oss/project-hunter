"""meme operator 3: the desk proposes through the E1 gate, and retires operator/2

Thirty-third revision. **A seed of one rule set that retires one.** No table,
no column, no view, no enum, no RLS policy, no grant; nothing touched in
``0022``–``0032``.

T4.19, on the Lab (``0022``), the moonshot seed (``0029``: ``operator/2``)
and the flow gate (``0030``: ``flow_v2/1``): Everton's directive of
12/09/2026, 17:3x BRT — "coloca aí qual entra, quanto comprar e na mesma hora
qual horário vender". He executes the real test **by hand**, with the observed
wallet writing the fill (T4.12); the desk therefore has to propose through
the gate the study of the 21 bets chose — E1 (flow and holders, EXP-M5) with
the E2 exclusions (pedigree, EXP-M6) — instead of ``operator/2``'s inherited
EXP-M1 gate (reproved, 9/9 negative). ``operator/3`` is ``flow_v2/1``'s
params composed in SQL with the brief's overrides (``ttl_s = 180``,
``max_open_positions = 2``; ``ddl/meme_operator_3.py``); every proposal it
makes carries ``suggested.manual_plan`` (written by the worker, not by this
revision).

**Upgrade guard: one, after the seed** — ``operator/2`` is retired **before**
the insert and the revision then asserts that exactly one ``operator`` set is
active (a set planted by hand, or an ``operator/3`` that already existed
retired, would leave the desk with two or none: refused, never repaired
here). **The downgrade refuses** while a proposal or a bet references
``operator/3``; then the seed reverses, ``operator/2`` comes back ``active``
and the same invariant is asserted.

**Lock and pooler.** One ``UPDATE`` of one row and one ``INSERT`` of one row
on a table of a dozen rows; nothing depends on session state.
**Named ``0033_meme_operator_3`` (20 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §45.

**Chain.** Revises ``0032_meme_activity`` (T4.2g, written in parallel — the
brief of T4.19 still named this revision ``0032``; the head on disk had moved).

Revision ID: 0033_meme_operator_3
Revises: 0032_meme_activity
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_operator_3 import (
    refuse_a_downgrade_that_would_orphan_an_operator_3_row,
    seed_operator_3,
    unseed_operator_3,
)

revision: str = "0033_meme_operator_3"
down_revision: str | None = "0032_meme_activity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_operator_3()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_operator_3_row()
    unseed_operator_3()
