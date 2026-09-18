"""``0052_meme_gate_after_drop_arm`` — "do not enter after the fall" as a
pre-registered research arm (T4.61a, EXP-M13, KB-0118).

**Measured before this seed existed.** KB-0118 (16/09/2026) read 613 entries
of the live gate over 5 days (12–16/09) against the curve's own photos and
found the cell *fell ≥ 50 % from a peak at most 60 s old* to be the **only
negative one** (−0,305 R, tail ≥ +2 R at 4,1 % against ~13 %); the same cell
with an **old** peak (60–180 s) was the best of all (+0,566 R, n = 17), which
is why the criterion is a refusal per decision and never a ban on the coin.
R56 (18/09) then read the desk's first real buys of 17→18/09: **7 of 7** were
made after a drop. The in-sample Δ of the filter is +0,038 R [+0,022; +0,054]
over 540 surviving entries — X and N chosen among nine combinations on the
same sample (KB-0092), so EXP-M13's registered default prediction is
``descartar``.

**Therefore: an arm, not a switch on the desk.** ``flow_v2/9`` (``…0016``,
``research_only``, ``exp_ref EXP-M13``, 15-second clock) is ``flow_v2/6``
(``0044``) with **one** key added — ``max_recent_drawdown_pct: "0.50"`` — and
nothing else: ``test_migration_0052`` proves ``flow_v2/9.params`` minus that
key equals ``flow_v2/6.params`` byte for byte. The window (60 s) and the
staleness bound (30 s) are the gate's defaults (``EntryGate``,
``hunter_meme_worker.lab_models._gate_from_params``) and are not restated: the
pre-registration froze them with the arm, not beside it. Nothing is retired,
``flow_v2/6`` stays active (it is this arm's control) and the desk's
``operator/5`` is not touched: only ``kind = 'operator'`` sets reach the
executor (``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED``: ``WHERE
rs.kind = 'operator' AND rs.status = 'active'``), so a ``research_only`` set
is paper by construction.

**What the seed alone cannot do.** Until T4.61a the 15-second lane never
filled ``GateRow.recent_drawdown_*`` (only the event lane did), so this set
would have refused **every** row ``recent_drawdown_unknown`` — the same
task lands ``hunter_meme_worker.lab_repo_drawdown`` (one bounded read of
``meme_curve_snapshots.real_sol_reserves`` per tick) so the arm measures the
fall and not the blindness. P5 of the page (``recent_drawdown_unknown`` ≤ 10 %
of the arm's refusals) is what says whether that held.

**Five declarations, rather than silence.**

1. *The version is ``flow_v2/9``, not the ``/8`` the page froze.* The page
   (16/09) reserved ``/8`` for itself; ``0050`` (T4.49, EXP-M14) took ``/8``
   the next day. Same arm, next free version.
2. *The revision is ``0052_meme_gate_after_drop_arm``.* The brief named it
   ``0052_meme_gate_no_entry_after_drop_arm`` (38 characters);
   ``alembic_version.version_num`` is ``VARCHAR(32)`` (§17.6, §30.7) and the
   project already paid for a 33-character id once (``0005``). 29 characters.
3. *The base is ``flow_v2/6``, which carries ``pedigree_e2b: true``.* The
   page names the live set (``flow_v2/5``) as the control; as ``0049`` and
   ``0050`` declare, the closest **research** set to the desk's calibrated
   gate is ``flow_v2/6``, so the honest reading is ``flow_v2/9`` **against
   ``flow_v2/6``**, both carrying E2-b, never against ``operator/5``.
4. *``gate_version`` stays 3.* One criterion is switched on by a param the
   gate already knows how to read; the field is descriptive and the arm is
   identified by ``flow_v2/9``.
5. *The fill looks back 120 s and the gate's window is 60 s.* The page's
   operational definition takes the peak over ``[t − 60 s, t]``; the pure
   gate (T4.52b-2) refuses only when the peak is at most
   ``recent_drawdown_window_s`` old and **passes** an older peak — KB-0118's
   best cell —, so the 15-second fill folds over the series' own 120 s
   horizon and carries the peak's age for the gate to judge. The refusal is
   the same for a single peak; they differ only when a lower, younger peak
   sits inside the 60 s behind an older, higher one — declared here and in
   the page, and it is the gate's (already shipped) reading that wins.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_e2b_arm import E2B_OVERRIDES
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_AFTER_DROP_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000016"

AFTER_DROP_OVERRIDE = '"max_recent_drawdown_pct": "0.50"'
"""The whole arm, as data: neither ``FLOW_V2_PARAMS`` nor ``E2B_OVERRIDES``
carries the key, so this last ``jsonb ||`` is the one difference between
``flow_v2/9`` and ``flow_v2/6``. A **string** (a fraction, ``0.50`` = half),
like every decimal threshold in these params: the worker parses it as
``Decimal`` (``optional_decimal``), and a JSON number would have changed the
type as well as the value."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_AFTER_DROP_RULE_SET_ID}', 'flow_v2', '9', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{E2B_OVERRIDES}}}'::jsonb
     || '{{{AFTER_DROP_OVERRIDE}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M13', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{FLOW_V2_AFTER_DROP_RULE_SET_ID}'"
)


def seed_after_drop_arm() -> None:
    """Idempotent on a database already at ``0052``; nothing is retired, and the
    desk's ``operator/5`` is not touched (the guard is paper only)."""
    op.execute(_SEED)


def unseed_after_drop_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/9 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/9 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded flow_v2/9 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded flow_v2/9 set - the seed cannot be removed under them",
    ),
)
"""``0049``/``0050``'s four: every table with a ``rule_set_id`` foreign key
to ``meme_rule_sets``, named so the ``DELETE`` fails with the §17.7 sentence
that says what was about to be lost and how to copy it out first, never as a
raw foreign-key violation."""


def refuse_a_downgrade_that_would_orphan_an_after_drop_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{FLOW_V2_AFTER_DROP_RULE_SET_ID}'"
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
