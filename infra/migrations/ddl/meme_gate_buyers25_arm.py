"""``0049_meme_gate_buyers25_arm`` — the floor of 25 unique buyers as a
pre-registered research arm (T4.48, EXP-M10).

**Measured before this seed existed.** KB-0112 §4 found ``unique_buyers`` to be
the only one of the minute's three variables with a tail signal (Spearman with
``R >= +2`` = **+0,153**, p = 0,004) and closed asking for the floor 10 → 25.
KB-0114 measured the seven floors over 345 entries in 5 days (12–16/09/2026, 3
full): at ``>= 25`` the mean R moves **+0,090 R** ([+0,038; +0,201],
P(Δ > 0) = 1,00) against today's floor of 10, the only floor whose gain survives
leave-one-day-out (+0,216 to +0,246), with a cadence that still closes the ruler
(273 bets in 5 days, 81,3/day of ceiling). Everything is in-sample: the 25 came
out of looking at the same sample that measures it (KB-0092), so EXP-M10's
registered default prediction is ``descartar``.

**Therefore: an arm, not a switch on the desk.** ``flow_v2/7`` (``…0014``,
``research_only``, ``exp_ref EXP-M10``, 15-second clock) is ``flow_v2/6``
(``0044``) with **one** number moved — ``min_unique_buyers`` 10 → 25 — and
nothing else: ``test_migration_0049`` proves ``flow_v2/7.params`` and
``flow_v2/6.params`` differ on that key alone. Nothing is retired, ``flow_v2/6``
stays active (it is this arm's control) and the desk's ``operator/5`` is not
touched: only ``kind = 'operator'`` sets reach the executor
(``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED``:
``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a ``research_only``
set is paper by construction.

**Two declarations, rather than silence.**

1. *The base is ``flow_v2/6``, which carries ``pedigree_e2b: true``.*
   EXP-M10's frozen page describes the arm as "clone exato do conjunto vivo"
   and its criteria table lists E2 v1 (``creator_serial``/``symbol_clone``)
   without the E2-b leg. The seeded base is the closest **research** set to the
   desk's calibrated gate that exists in the database (``flow_v2/5`` predates
   the calibration of 16/09 and ``operator/5`` is the desk's own, edited by
   hand), so the honest reading of this arm is ``flow_v2/7`` **against
   ``flow_v2/6``**, both carrying E2-b, never against ``operator/5``. Written
   back into the EXP-M10 page and ``docs/DATABASE.md`` §57.
2. *``gate_version`` stays 3.* ``0034`` and ``0044`` bumped it because the set
   of criteria moved (new keys, a criterion switched off); here the criteria are
   byte for byte ``flow_v2/6``'s and a single threshold moves, which the params
   already carry. ``gate_version`` is descriptive only
   (``hunter_meme_worker.lab_models._gate_from_params``): the arm is identified
   by ``flow_v2/7``.

The "reentrada" of the pre-registration is **not** a param: the gate is judged
on every 15-second photo inside the 30–300 s window already, so a coin that
misses 25 buyers on one bar and reaches it on a later one is proposed then —
refusing a coin for ever would have needed a new key, and none was added.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_e2b_arm import E2B_OVERRIDES
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_BUYERS25_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000014"

BUYERS25_OVERRIDE = '"min_unique_buyers": 25'
"""The whole arm, as data. ``FLOW_V2_PARAMS`` writes ``10`` and ``E2B_OVERRIDES``
does not restate it, so this last ``jsonb ||`` is the one difference between
``flow_v2/7`` and ``flow_v2/6``."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_BUYERS25_RULE_SET_ID}', 'flow_v2', '7', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{E2B_OVERRIDES}}}'::jsonb
     || '{{{BUYERS25_OVERRIDE}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M10', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{FLOW_V2_BUYERS25_RULE_SET_ID}'"
)


def seed_buyers25_arm() -> None:
    """Idempotent on a database already at ``0049``; nothing is retired, and the
    desk's ``operator/5`` is not touched (the floor of 25 is paper only)."""
    op.execute(_SEED)


def unseed_buyers25_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/7 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/7 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded flow_v2/7 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded flow_v2/7 set - the seed cannot be removed under them",
    ),
)
"""``0044``'s two, plus the two tables ``0046`` added after it: both carry a
``rule_set_id`` foreign key to ``meme_rule_sets``, so without naming them here
the ``DELETE`` would fail as a raw foreign-key violation instead of the §17.7
sentence that says what was about to be lost and how to copy it out first."""


def refuse_a_downgrade_that_would_orphan_a_buyers25_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{FLOW_V2_BUYERS25_RULE_SET_ID}'"
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
