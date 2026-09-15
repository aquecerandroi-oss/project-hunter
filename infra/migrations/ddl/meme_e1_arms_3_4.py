"""``0037_meme_e1_arms_3_4`` — two sibling arms of the E1 gate, contradicting
its own pre-registration (T4.23, EXP-M5).

**Measured by the daily close of 13/09/2026 (`obsidian/09-OPERATIONS/Diario-Meme/2026-09-13.md`
§6.4/§6.5, 66 measured bets, 95 % CI by hour blocks, repeated by the 14/09 lot):** ``snipers > 2``
paid R mean +0,25 (n = 17) against −0,28 elsewhere (n = 49) — Δ +0,53 R, CI [0,23, 0,88]; a
``top10_share`` of 0,1767–0,257 paid +0,25 (n = 14) against −0,25 elsewhere (n = 52) — Δ +0,50 R,
CI [0,14, 1,36]. Both contradict E1's own pre-registration (``snipers ≤ 2``, no floor on
``top10_share``): per the ruler (KB-0092) this does **not** move the live sets — it plants two
siblings, pre-registered ``descartar``, measured beside them.

**The seed plants two sets and retires nothing.** ``flow_v2/3`` (``…000e``, ``research_only``,
EXP-M5) is ``flow_v2/2``'s params (``ARM2_OVERRIDES`` over ``FLOW_V2_PARAMS``) plus
``min_snipers 3`` — ``max_snipers 10`` was already arm 2's. ``flow_v2/4`` (``…000f``, same kind) is
``flow_v2/2``'s params plus ``min_top10_share "0.1767"`` and ``max_top10_share "0.257"`` — neither
key existed on arm 2. ``flow_v2/1`` and ``flow_v2/2`` **stay active**: both siblings are measured
next to arms 1 and 2, the comparison is the point. The desk (``operator/4``) is untouched.

Predictions registered on the EXP-M5 page (arms 3 and 4): ``descartar``.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_e1_arm2 import ARM2_OVERRIDES
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_ARM3_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000000e"
FLOW_V2_ARM4_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000000f"

ARM3_OVERRIDES = ARM2_OVERRIDES + ', "min_snipers": 3'
"""Arm 2 plus the funnel's sniper floor: ``test_0037`` proves
``flow_v2/3.params − 'min_snipers' = flow_v2/2.params`` byte for byte."""

ARM4_OVERRIDES = ARM2_OVERRIDES + ', "min_top10_share": "0.1767", "max_top10_share": "0.257"'
"""Arm 2 plus the funnel's top-10 band: ``test_0037`` proves
``flow_v2/4.params − the two keys = flow_v2/2.params`` byte for byte."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_ARM3_RULE_SET_ID}', 'flow_v2', '3', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{ARM3_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M5', 'active'),
  ('{FLOW_V2_ARM4_RULE_SET_ID}', 'flow_v2', '4', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{ARM4_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M5', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen ids
    f"WHERE id IN ('{FLOW_V2_ARM3_RULE_SET_ID}', '{FLOW_V2_ARM4_RULE_SET_ID}')"
)


def seed_e1_arms_3_4() -> None:
    """Idempotent on a database already at ``0037``; nothing is retired."""
    op.execute(_SEED)


def unseed_e1_arms_3_4() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/3 or flow_v2/4 set - the seed cannot be removed "
        "under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/3 or flow_v2/4 set - the seed cannot be removed "
        "under them",
    ),
)


def refuse_a_downgrade_that_would_orphan_an_arm3_or_arm4_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id IN ('{FLOW_V2_ARM3_RULE_SET_ID}', '{FLOW_V2_ARM4_RULE_SET_ID}')"
    safe_predicate = predicate.replace("'", "''")
    for table, why in _GUARDED:
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
