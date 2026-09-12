"""``0034_meme_gate_e1_arm2`` — the second arm of the E1 gate (T4.21, EXP-M5 arm 2).

**Measured after the tape by batch went live (deploy ``6fc3a43``, 18:3x–19:0x
BRT of 12/09/2026, ``meme_features_15s``, 30 minutes —
``infra/scripts/sql/research/2026-09-12-t421-funil-e1.sql``):** 13 mints passed
E1's flow base (age 30–300 s, net SOL flow > 0, ≥ 10 buyers, sells/buys ≤ 0,6),
12 with progress ≥ 5 %. Of those, ``snipers ≤ 2`` left **zero** (≤ 10: 5;
≤ 25: 9); holders *rising* between two readings 3 (not falling with ≥ 20: 6);
dev ≤ 10 %: 12; creator known not a seller 5, unknown 7. The arm frozen as
``flow_v2/1`` (and the desk's ``operator/3``, ``0033``) proposed nothing since
18:44 — a gate with no exit cannot be measured.

**The seed plants two sets and retires one.** ``flow_v2/2`` (``…000b``,
``research_only``, EXP-M5 arm 2) and ``operator/4`` (``…000c``, ``kind =
operator``) are ``FLOW_V2_PARAMS`` composed in SQL (``jsonb ||``) with the
arm-2 switches written over it — ``max_snipers 10``, ``min_holders 20``,
``holders_rising_or_flat``, ``creator_unknown_allowed_if_dev_measured``,
``progress_or_mcap_rising`` (``rules.py``, all off by default so arm 1 reads
exactly as frozen) — plus, for the desk only, the hand-executed numbers of
``0033`` (``ttl_s 180``, ``max_open_positions 2``). ``flow_v2/1`` **stays
active**: arm 1 keeps being measured next to arm 2, the comparison is the
point. ``operator/3`` → ``retired`` **before** the insert (the desk never sees
two active ``operator`` sets); the ``downgrade`` deletes both seeds and brings
``operator/3`` back ``active``, exactly as ``0033`` did with ``operator/2``.

Prediction registered on the EXP-M5 page (arm 2): ``descartar``.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS
from ddl.meme_operator_3 import OPERATOR_3_RULE_SET_ID

FLOW_V2_ARM2_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000000b"
OPERATOR_4_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000000c"

ARM2_OVERRIDES = (
    '"gate_version": 2, "max_snipers": 10, "min_holders": 20, '
    '"holders_rising_or_flat": true, "creator_unknown_allowed_if_dev_measured": true, '
    '"progress_or_mcap_rising": true'
)
"""What the funnel of 12/09 changes, and nothing else: ``test_0034`` proves
``flow_v2/2.params − the five keys = flow_v2/1.params`` byte for byte."""

OPERATOR_4_OVERRIDES = (
    ARM2_OVERRIDES + ', "ttl_s": 180, "max_open_positions": 2, '
    '"size_sol": "0.05", "max_sol_per_bet": "0.05", "max_exposure_per_mint_sol": "0.05", '
    '"target_x": "3", "trailing_pct": "35", "trailing_arm_x": "1.5", '
    '"max_hold_s": 1800, "max_loss_pct": "50", "exit_on_line_break": true'
)
"""The desk's set = arm 2 + ``0033``'s hand-executed numbers, restated."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_RETIRE_OPERATOR_3 = (
    "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "  # noqa: S608
    f"WHERE id = '{OPERATOR_3_RULE_SET_ID}' AND status = 'active'"
)
_REVIVE_OPERATOR_3 = (
    "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL "  # noqa: S608
    f"WHERE id = '{OPERATOR_3_RULE_SET_ID}'"
)
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_ARM2_RULE_SET_ID}', 'flow_v2', '2', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{ARM2_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M5', 'active'),
  ('{OPERATOR_4_RULE_SET_ID}', 'operator', '4', 'operator',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{OPERATOR_4_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', NULL, 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen ids
    f"WHERE id IN ('{FLOW_V2_ARM2_RULE_SET_ID}', '{OPERATOR_4_RULE_SET_ID}')"
)

_ASSERT_ONE_ACTIVE_OPERATOR = (
    "DO $$ DECLARE active_operators bigint; BEGIN "
    "SELECT count(*) INTO active_operators FROM meme_rule_sets "
    "WHERE kind = 'operator' AND status = 'active'; "
    "IF active_operators <> 1 THEN RAISE EXCEPTION USING "
    "MESSAGE = 'PROJECT HUNTER: ' || active_operators || ' operator sets are active - the desk "
    "files manual buys under exactly one', "
    "HINT = 'retire the extra set (infra/scripts/meme_rule_set.py --deprecate) or restore the "
    "missing one before migrating'; "
    "END IF; END $$;"
)
"""The desk's invariant (``0033``), asserted after the hand-over in both directions."""


def seed_e1_arm2() -> None:
    """``operator/3`` retired first, then the two arm-2 sets planted; then the
    invariant. Idempotent on a database already at ``0034``."""
    op.execute(_RETIRE_OPERATOR_3)
    op.execute(_SEED)
    op.execute(_ASSERT_ONE_ACTIVE_OPERATOR)


def unseed_e1_arm2() -> None:
    op.execute(_UNSEED)
    op.execute(_REVIVE_OPERATOR_3)
    op.execute(_ASSERT_ONE_ACTIVE_OPERATOR)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/2 or operator/4 set - the seed cannot be removed "
        "under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/2 or operator/4 set - the seed cannot be removed "
        "under them",
    ),
)


def refuse_a_downgrade_that_would_orphan_an_arm2_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id IN ('{FLOW_V2_ARM2_RULE_SET_ID}', '{OPERATOR_4_RULE_SET_ID}')"
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
