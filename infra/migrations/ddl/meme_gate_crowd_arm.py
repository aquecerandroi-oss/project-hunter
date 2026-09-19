"""``0054_meme_gate_crowd_arm`` — "a rise with people behind it" as a
pre-registered research arm (T4.66, EXP-M19,
``obsidian/05-EXPERIMENTS/EXP-M19-subida-com-gente-atras.md``).

**The hypothesis, as data.** Everton (19/09/2026, 00:4x BRT): "se está
subindo, vendas rápidas e mudanças rápidas de subida" — the rise that pays
has new wallets coming in and the first buyers (the snipers of blocks 1–3)
**holding**; the one that does not is a distribution. The event feed
(T4.52b, ~3 000 trades/min) says **who** buys and sells; until this arm the
gate only read counts off a photo (snipers, holders, progress).

**Therefore: an arm, not a switch on the desk.** ``flow_v2/10`` (``…0018``,
``research_only``, ``exp_ref EXP-M19``, 15-second clock) is ``flow_v2/6``
(``0044``) with **four** keys added and nothing else —
``test_migration_0054`` proves ``flow_v2/10.params`` minus the four equals
``flow_v2/6.params`` byte for byte:

- ``min_early_retention_pct: "0.70"`` — the early wallets still hold ≥ 70 %
  of what they bought (a **fraction**, a string, like every decimal here);
- ``min_early_age_s: 60`` — and have held it for ≥ 60 s;
- ``min_new_wallets_30s: 5`` — ≥ 5 wallets whose first trade fell in the
  last 30 s;
- ``max_quick_flip_share_30s: "0.20"`` — ≤ 20 % of the last 30 s of trades
  are sells by a wallet that bought < 20 s earlier.

The four are read by ``EntryGate`` through
``hunter_meme_worker.lab_gate_params.gate_from_params`` (T4.66) and judged by
``hunter_indicators.meme.rules_crowd``; the readings come from
``hunter_indicators.meme.crowd.CrowdLedger`` inside the event lane's
``MintEventState`` — **only the event lane** fills them, so on the 15-second
lane this set refuses every row ``early_retention_unknown`` /
``new_wallets_unknown`` / ``quick_flip_unknown`` (fail closed, by name),
exactly as ``flow_v2/9`` did before T4.61a for the drawdown. The share of
``*_unknown`` among the arm's refusals is the first number to read after
the deploy (EXP-M19's own "braço semeado" block).

Nothing is retired, ``flow_v2/6`` stays active (it is this arm's control) and
the desk's ``operator/5`` is not touched: only ``kind = 'operator'`` sets
reach the executor (``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED``:
``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a
``research_only`` set is paper by construction. ``gate_version`` stays 3 (a
criterion switched on by params the gate already reads; the arm is
identified by ``flow_v2/10``). The slug is 24 characters (``alembic_version
.version_num`` is ``VARCHAR(32)``, §17.6/§30.7).
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_e2b_arm import E2B_OVERRIDES
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_CROWD_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000018"

CROWD_OVERRIDES = (
    '"min_early_retention_pct": "0.70", "min_early_age_s": 60, '
    '"min_new_wallets_30s": 5, "max_quick_flip_share_30s": "0.20"'
)
"""The whole arm, as data: neither ``FLOW_V2_PARAMS`` nor ``E2B_OVERRIDES``
carries any of the four keys, so this last ``jsonb ||`` is the one difference
between ``flow_v2/10`` and ``flow_v2/6``. The two fractions are **strings**
(the worker parses them as ``Decimal``, ``optional_decimal``); the two counts
are JSON integers (``optional_int``), like ``min_holders``/``min_snipers``."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_CROWD_RULE_SET_ID}', 'flow_v2', '10', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{E2B_OVERRIDES}}}'::jsonb
     || '{{{CROWD_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M19', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{FLOW_V2_CROWD_RULE_SET_ID}'"
)


def seed_crowd_arm() -> None:
    """Idempotent on a database already at ``0054``; nothing is retired, and the
    desk's ``operator/5`` is not touched (the arm is paper only)."""
    op.execute(_SEED)


def unseed_crowd_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/10 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/10 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded flow_v2/10 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded flow_v2/10 set - the seed cannot be removed under them",
    ),
)
"""``0049``/``0050``/``0052``/``0053``'s four: every table with a ``rule_set_id``
foreign key to ``meme_rule_sets``, named so the ``DELETE`` fails with the
§17.7 sentence that says what was about to be lost and how to copy it out
first, never as a raw foreign-key violation."""


def refuse_a_downgrade_that_would_orphan_a_crowd_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{FLOW_V2_CROWD_RULE_SET_ID}'"
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
