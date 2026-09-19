"""a second real desk: operator/6 = flow_v2/1's entry + Everton's exit (T4.71)

Revision ID: 0055_meme_operator6_desk
Revises: 0054_meme_gate_crowd_arm

Everton, 19/09/2026 09:5x BRT (written; ``obsidian/06-DECISIONS/2026-09-12-
teste-pequeno-meme-real.md``, addendum of the same hour): 72 h of paper read
``flow_v2/1`` at +0,054 SOL (+0,103 in the last 24 h) while the desk's own
``operator/5`` read −0,070 — "vamos operar com dinheiro real também". This
revision seeds **one** set, ``operator/6`` (``…0019``, ``kind = operator``,
``exp_ref`` null, 15-second clock), and retires nothing.

**What it is.** ``FLOW_V2_PARAMS`` — the constant the ``0030`` seed planted
``flow_v2/1`` from (``ddl/meme_gate_v2_seed.py``), composed in SQL and never
retyped — plus twelve desk keys (``ddl/meme_operator_6.OPERATOR_6_OVERRIDES``):
the exit Everton chose on 19/09 02:10 BRT (``target_x "1.15"``, ``trailing_pct
"10"``, ``trailing_arm_x null`` = armed from the entry, ``max_hold_s 300``,
``exit_key "alvo_1_15x_trailing_10_tempo_5m"``, ``exit_on_line_break true`` as
``operator/5``), the ticket (``size_sol``/``max_sol_per_bet``/
``max_exposure_per_mint_sol`` ``"0.07"``, ``max_open_positions 2``, ``ttl_s
180``) and ``pedigree_repeat_dumper true`` as ``operator/5``. Every other key
— the whole E1 entry gate, ``wallet_max_sol``, ``daily_loss_cap_sol``,
``max_loss_pct``, ``fee_pct`` — is ``flow_v2/1``'s byte for byte
(``test_migration_0055``). **The entry is read from the DDL seed, not from the
live row:** ``flow_v2/1`` may have been edited since by ``infra/scripts/
meme_rule_set.py --set-param`` (§54), and a migration must plant the same desk
on every database; what is planted is the pre-registered E1 gate. Decimals are
strings — the Lab refuses a bare float (T4.64) — and the test loads the seed
through ``RuleSetSpec.from_params`` + the exit rules, the path ``--validate``
runs.

**Two desks share the brakes — read from the code.** The executor opens
proposals of **any** active operator set (``hunter_meme_executor.auto_approve
._OPERATOR_PROPOSED``: ``WHERE rs.kind = 'operator' AND rs.status = 'active'``,
no name, no version), so ``operator/6`` reaches money the moment this lands,
each proposal carrying its own set's exit into ``meme_live_positions.params``.
``max_open_positions`` and the daily loss cap are **executor-level**:
``hunter_risk_meme.checks_wallet`` counts *all* open live positions against
``MEME_MAX_OPEN_POSITIONS`` and the day's loss against
``MEME_DAILY_LOSS_CAP_SOL`` with no ``rule_set_id`` in the predicate; the set's
own ``max_open_positions: 2`` is the paper loop's per-set ceiling. The kill
switch latches for both.

**Declared consequence.** ``0033``/``0034``/``0039`` asserted "exactly one
active operator set" inside their own upgrade/downgrade; this revision's
downgrade removes ``operator/6`` before any of them could run, so the chain
still reverses. But ``MemeDeskRepository.get_operator_rule_set`` picks the
highest active ``operator`` version, so from here a **manual** buy from the
desk is filed under ``operator/6`` (ceiling 0,07 SOL); ``--deprecate`` lets
either set retire while the other stays.

**Downgrade (§17.7).** Refuses while ``meme_live_orders`` or
``meme_live_positions`` (through the proposal), ``meme_proposals``,
``meme_paper_bets``, ``meme_rule_set_param_history`` or
``meme_gate_refusals_by_mint`` reference the set; clean, the seed goes and
``operator/5`` is untouched. One ``INSERT … ON CONFLICT DO NOTHING``, no session
state, no maintenance window; 24-character slug.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_operator_6 import (
    refuse_a_downgrade_that_would_orphan_an_operator_6_row,
    seed_operator_6,
    unseed_operator_6,
)

revision: str = "0055_meme_operator6_desk"
down_revision: str | None = "0054_meme_gate_crowd_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_operator_6()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_an_operator_6_row()
    unseed_operator_6()
