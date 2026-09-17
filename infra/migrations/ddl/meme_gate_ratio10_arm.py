"""``0050_meme_gate_ratio10_arm`` — the ceiling of 1.0 on sells/buys as a
pre-registered research arm (T4.49, EXP-M14).

**Measured before this seed existed.** R48 (17/09/2026 01:51 BRT) read 24 h of
``meme_features_1m`` — 28 989 mints with ``>= 3`` readings, 459 graduated — and
found the live ceiling of **0,6** (``operator/5`` and ``flow_v2/6``) discarding
113 of the 459 graduated coins (24,6 %). The graduation rate **below** 0,6 is
0,53 % against 2,12 % above it (4× lower), and the rate peaks at **2,21 %** in
the 1,0–1,5 bucket: a ceiling at 1,0 keeps 95 %+ of the graduated while sitting
on that peak. R51 pointed the same way from the other side (dropping the ratio
criterion altogether: +9 graduated for +5 losers, 1,80 per extra loser), and
both readings are in-sample on a single day, with ``buy_sell_ratio`` NULL on 340
of the 459 graduated (KB-0092) — which is why EXP-M14's registered default
prediction is ``descartar``.

**Therefore: an arm, not a switch on the desk.** ``flow_v2/8`` (``…0015``,
``research_only``, ``exp_ref EXP-M14``, 15-second clock) is ``flow_v2/6``
(``0044``) with **one** number moved — ``max_sells_to_buys`` "0.6" → "1.0" — and
nothing else: ``test_migration_0050`` proves ``flow_v2/8.params`` and
``flow_v2/6.params`` differ on that key alone. Nothing is retired, ``flow_v2/6``
stays active (it is this arm's control) and the desk's ``operator/5`` is not
touched: only ``kind = 'operator'`` sets reach the executor
(``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED``:
``WHERE rs.kind = 'operator' AND rs.status = 'active'``), so a ``research_only``
set is paper by construction.

**Four declarations, rather than silence.**

1. *The param key is ``max_sells_to_buys``, not ``max_sell_buy_ratio``.*
   EXP-M14's frozen page names the knob ``max_sell_buy_ratio`` (the name of the
   **feature column**, ``meme_features_1m.buy_sell_ratio``); the key that
   ``flow_v2/6`` actually carries — seeded by ``0030`` in ``FLOW_V2_PARAMS`` and
   read by ``hunter_indicators.meme.rules`` — is ``max_sells_to_buys``, and its
   value is a **string** ("0.6"), not a number. Moving the key the page names
   would have seeded a param nothing reads, i.e. a clone of the control wearing
   a different name. Written back into the EXP-M14 page and ``docs/DATABASE.md``
   § 58.
2. *The revision is ``0050_meme_gate_ratio10_arm``.* The page, written before
   the migration existed, predicted the slug ``0050_meme_gate_sells_buys_arm``;
   the revision that landed carries the ceiling in its name instead. Same
   ``0050``, same arm.
3. *The base is ``flow_v2/6``, which carries ``pedigree_e2b: true``.* Same
   declaration ``0049`` makes: the base is the closest **research** set to the
   desk's calibrated gate that exists in the database, so the honest reading of
   this arm is ``flow_v2/8`` **against ``flow_v2/6``**, both carrying E2-b,
   never against ``operator/5`` — which is exactly the control the
   pre-registration names.
4. *``gate_version`` stays 3.* The set of criteria did not move: one threshold
   did, and the params already carry it. ``gate_version`` is descriptive only
   (``hunter_meme_worker.lab_models._gate_from_params``): the arm is identified
   by ``flow_v2/8``.

The "reentrada até 5 min" of the pre-registration is **not** a param, exactly as
in ``0049``: the gate is judged on every 15-second photo inside the 30–300 s
window already, so a coin over the ceiling on one bar and under it on a later
one is proposed then — refusing a coin for ever would have needed a new key, and
none was added.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_e2b_arm import E2B_OVERRIDES
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_RATIO10_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000015"

RATIO10_OVERRIDE = '"max_sells_to_buys": "1.0"'
"""The whole arm, as data. ``FLOW_V2_PARAMS`` writes ``"0.6"`` and
``E2B_OVERRIDES`` does not restate it, so this last ``jsonb ||`` is the one
difference between ``flow_v2/8`` and ``flow_v2/6``. A **string**, like every
decimal threshold in these params: the worker parses it as ``Decimal``, and a
JSON number would have changed the type as well as the value."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_RATIO10_RULE_SET_ID}', 'flow_v2', '8', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{E2B_OVERRIDES}}}'::jsonb
     || '{{{RATIO10_OVERRIDE}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M14', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{FLOW_V2_RATIO10_RULE_SET_ID}'"
)


def seed_ratio10_arm() -> None:
    """Idempotent on a database already at ``0050``; nothing is retired, and the
    desk's ``operator/5`` is not touched (the ceiling of 1,0 is paper only)."""
    op.execute(_SEED)


def unseed_ratio10_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/8 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/8 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded flow_v2/8 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded flow_v2/8 set - the seed cannot be removed under them",
    ),
)
"""``0044``'s two, plus the two tables ``0046`` added after it: both carry a
``rule_set_id`` foreign key to ``meme_rule_sets``, so without naming them here
the ``DELETE`` would fail as a raw foreign-key violation instead of the §17.7
sentence that says what was about to be lost and how to copy it out first."""


def refuse_a_downgrade_that_would_orphan_a_ratio10_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{FLOW_V2_RATIO10_RULE_SET_ID}'"
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
