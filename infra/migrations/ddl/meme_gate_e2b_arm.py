"""``0044_meme_gate_e2b_arm`` — E2-b as a pre-registered research arm
(T4.31, EXP-M9).

**Measured, twice, before this seed existed.**
KB-0103 (14–16/09/2026, 2 877 graduated coins, tape label on 390) found the
signature of the *forged* graduation: the curve filled ``<= 60 s`` after the
mint (88,4 % of the forged, 0,6 % of the organic) or a single wallet paid
``>= 35 %`` of the SOL bought on the rise (median 0,25 against 0,05). The two
legs together caught 100 % of the forged at a cost of 2,0 % of the organic,
while E2 v1 (``creator_serial`` / ``symbol_clone``) caught 34,9 % at a cost of
**51,3 %**. KB-0105 replicated it out of sample (12 and 13/09, 1 828 graduated,
307 labelled): the **direction** replicates (recall 92–100 % at a cost of
3,9–11,4 % against E2 v1's 35–54 % at 30–40 %), the **level** does not — the
cost of 2,0 % became 11,4 % in 12/09. On the 103 measured paper bets of those
two days E2-b would have marked 41, summing −14,2 R of −18,9 R, with a single
winner among them — but both days were losing days, so what is measured is
*loss avoided*, never edge.

**Therefore: an arm, not a switch on the desk.** ``flow_v2/6`` (``…0013``,
``research_only``, ``exp_ref EXP-M9``, 15-second clock) is the desk's current
calibrated gate plus ``pedigree_e2b: true`` — the criterion frozen in
``hunter_indicators.meme.pedigree_e2b`` (``pedigree_e2b/1``:
``e2b_top_buyer_share_max`` 0,35, ``e2b_min_buyers`` 10, ``e2b_born_full_s``
60). ``flow_v2/5`` **stays active** and the desk's ``operator/5`` is
untouched: the comparison is the whole point, and EXP-M9's default prediction
is ``descartar`` (KB-0092: never tune on the first days).

**What "the desk's calibrated gate" means here, spelled out.** ``flow_v2/5``
(``0039``) is arm 2 (``0034``) plus ``pedigree_repeat_dumper``; the desk's
numbers of 16/09 (KB-0099 §3 and KB-0102 §2, applied to ``operator/5`` on the
VPS by ``meme_rule_set.py --set-param``, and to ``exclude_mayhem`` by T4.27)
are the six keys of :data:`CALIBRATION_OVERRIDES`. The gate version bumps to
**3** because the criteria moved: a ``fluxo_e_holders/2`` proposal must keep
meaning what it meant the day arm 2 was frozen.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_creator_repeat import REPEAT_DUMPER_OVERRIDES
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_E2B_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000013"

CALIBRATION_OVERRIDES = (
    '"gate_version": 3, "require_holders_rising": false, "require_progress_rising": false, '
    '"min_snipers": 21, "max_snipers": 1000, "max_progress_pct": "50", "exclude_mayhem": true'
)
"""The desk's gate as it stands on 16/09/2026 18:xx BRT, restated as data:
holders >= 20 **not** rising, buyers >= 10, sells/buys <= 0,6, snipers >= 21
with no ceiling (KB-0102 §2), progress 5–50 % (the 15:08 audit), Mayhem
excluded (T4.27). ``min_holders``, ``min_unique_buyers``, ``max_sells_to_buys``
and ``min_progress_pct`` are already arm 2's and are not restated."""

E2B_OVERRIDES = REPEAT_DUMPER_OVERRIDES + ", " + CALIBRATION_OVERRIDES + ', "pedigree_e2b": true'
"""``flow_v2/5``'s params, plus the calibration, plus the one new switch:
``test_0044`` proves ``flow_v2/6.params − 'pedigree_e2b'`` equals
``flow_v2/5.params || CALIBRATION_OVERRIDES`` byte for byte. The three
thresholds of the criterion are **not** params: they are frozen in code
(``pedigree_e2b/1``), and moving one is a new version, never an edit."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_E2B_RULE_SET_ID}', 'flow_v2', '6', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{E2B_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M9', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{FLOW_V2_E2B_RULE_SET_ID}'"
)


def seed_e2b_arm() -> None:
    """Idempotent on a database already at ``0044``; nothing is retired, and
    the desk's ``operator/5`` is not touched (E2-b is paper only)."""
    op.execute(_SEED)


def unseed_e2b_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/6 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/6 set - the seed cannot be removed under them",
    ),
)


def refuse_a_downgrade_that_would_orphan_an_e2b_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{FLOW_V2_E2B_RULE_SET_ID}'"
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
