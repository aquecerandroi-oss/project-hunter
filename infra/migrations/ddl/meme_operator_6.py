"""``0055_meme_operator6_desk`` — a second REAL desk, ``operator/6`` (T4.71).

**The decision, as data** (Everton, 19/09/2026 09:5x BRT, written; the
addendum of the same hour in ``obsidian/06-DECISIONS/2026-09-12-teste-pequeno
-meme-real.md``): 72 h of paper read ``flow_v2/1`` at +0,054 SOL (+0,103 in
the last 24 h, 38 bets, 45 % hit rate) while the desk's own ``operator/5``
read −0,070. "Vi que o Lab está dando bom, vamos operar com dinheiro real
também": a second desk that buys **where ``flow_v2/1`` buys** and sells the
way he sells.

**``operator/6`` = ``flow_v2/1``'s entry + Everton's exit + the desk's size.**

- **Entry** — ``FLOW_V2_PARAMS`` (``ddl/meme_gate_v2_seed.py``), the constant
  the ``0030`` seed planted ``flow_v2/1`` from, composed in SQL (``'{…}'::jsonb
  || '{…}'::jsonb``) and never retyped: gate ``fluxo_e_holders/1`` on the
  15-second clock, 30–300 s, progress ≥ 5 % and rising, positive flow, ≥ 10
  unique buyers, sells/buys ≤ 0,6, holders rising, ≤ 2 snipers, dev share
  ≤ 10 % (unknown refuses), creator not a net seller, participation ≤ 1 %,
  pedigree exclusions. **Read from the DDL seed on purpose:** the live row of
  ``flow_v2/1`` can be edited by ``infra/scripts/meme_rule_set.py --set-param``
  (``operator/5`` was, four times on 16/09 — §54), and a migration that copied
  the live row would plant a different desk on every database it ran on. What
  this revision plants is the **pre-registered** E1 gate; if ``flow_v2/1`` has
  since been edited, ``--history flow_v2/1`` says by how much.
  ``test_migration_0055`` proves ``operator/6.params − the 12 desk keys =
  flow_v2/1.params − the same 12 keys`` byte for byte, i.e. every entry key
  (and ``wallet_max_sol``/``daily_loss_cap_sol``/``fee_pct``/…) is
  ``flow_v2/1``'s.
- **Exit** — "regra do Everton" (measured 19/09 02:10 BRT on ``operator/5``,
  then chosen for the second desk): ``target_x "1.15"``, ``trailing_pct "10"``,
  ``trailing_arm_x null`` (armed from the entry — ``lab_params
  .arm_multiple_or_none`` reads ``null`` as "always", the executor's trailing
  is always armed), ``max_hold_s 300``, ``exit_key
  "alvo_1_15x_trailing_10_tempo_5m"``; ``exit_on_line_break true`` as
  ``operator/5`` has it; ``max_loss_pct "50"`` stays ``flow_v2/1``'s.
- **Size** — ``size_sol "0.07"``, ``max_sol_per_bet "0.07"``,
  ``max_exposure_per_mint_sol "0.07"``, ``max_open_positions 2``, ``ttl_s 180``
  (a proposal waits 180 s for the desk, ``0033``), ``pedigree_repeat_dumper
  true`` as ``operator/5`` (``0039``), ``clock "15s"`` as ``flow_v2/1``.
  Decimals are **strings** (the Lab refuses a bare float —
  ``RuleSetSpec.from_params``, T4.64); ``test_migration_0055`` loads the seeded
  ``params`` through ``RuleSetSpec.from_params`` + ``effective_params(...)
  .exit_rules()``, the exact path ``meme_rule_set.py --validate`` runs.

**Two desks, one set of brakes — confirmed in code, not assumed.**

- The executor opens proposals of **any** active ``operator`` set:
  ``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED`` selects ``WHERE
  rs.kind = 'operator' AND rs.status = 'active'`` with no name or version;
  ``repo_tape.pending_operator_mints`` (the worker's risk reader) does the
  same. ``operator/5`` and ``operator/6`` therefore both reach money the
  moment this seed lands, each proposal carrying its own set's ``suggested``
  (size, target, trailing, hold) into ``decision`` and from there into
  ``meme_live_positions.params`` — the exit of a position is its own set's.
- ``max_open_positions`` and the daily loss cap are **executor-level and
  shared**: ``hunter_risk_meme.checks_wallet`` counts open live positions
  against ``MemeLimits.max_open_positions`` (``MEME_MAX_OPEN_POSITIONS``) and
  the day's loss against ``MemeLimits.daily_loss_cap_sol``
  (``MEME_DAILY_LOSS_CAP_SOL``), with no ``rule_set_id`` in either predicate;
  ``max_open_positions: 2`` in the set's ``params`` is what the **paper** loop
  enforces per set, and what the desk's ``manual_plan`` states. Two desks
  cannot open more real positions together than one could, and the kill
  switch (``meme_live_kill_switch``, scope ``wallet``) latches for both.

**Nothing is retired — and the one-operator invariant is over.** ``0033``/
``0034``/``0039`` asserted "exactly one active operator set" after each
hand-over, because the desk's manual buy (``MemeDeskRepository
.get_operator_rule_set``) files under *the* operator set. That assertion
lives inside those revisions only (their own upgrade/downgrade), and this
revision's downgrade removes ``operator/6`` before any of them could run, so
the chain still reverses. The behavioural consequence is declared, not
hidden: ``get_operator_rule_set`` reads ``name = 'operator' AND status =
'active'`` ordered by version, **highest first** — from this revision on a
**manual** buy from the desk is filed under ``operator/6`` (ceiling
``max_sol_per_bet "0.07"``), and ``meme_rule_set.py --deprecate`` will let
either set retire while the other stays (``last_operator_set`` refuses only
the last one). ``operator/5`` stays active: the comparison is the point.

**Downgrade (§17.7).** Refuses while a row references ``operator/6`` in —
first, because a real position is the loudest thing to lose —
``meme_live_orders`` and ``meme_live_positions`` (through ``meme_proposals
.rule_set_id``: neither carries a ``rule_set_id`` of its own), then
``meme_proposals``, ``meme_paper_bets``, ``meme_rule_set_param_history`` and
``meme_gate_refusals_by_mint``, as ``0049``–``0054`` do. The slug is 24
characters (``alembic_version.version_num`` is ``VARCHAR(32)``, §17.6/§30.7).
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

OPERATOR_6_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000019"

OPERATOR_6_OVERRIDES = (
    '"exit_key": "alvo_1_15x_trailing_10_tempo_5m", '
    '"target_x": "1.15", "trailing_pct": "10", "trailing_arm_x": null, "max_hold_s": 300, '
    '"exit_on_line_break": true, '
    '"size_sol": "0.07", "max_sol_per_bet": "0.07", "max_exposure_per_mint_sol": "0.07", '
    '"max_open_positions": 2, "ttl_s": 180, "pedigree_repeat_dumper": true'
)
"""Everything that is **not** ``flow_v2/1``'s: the exit (Everton's rule), the
desk's size/ceilings, the desk's TTL and the repeat-dumper switch ``operator/5``
carries. Exactly :data:`OPERATOR_6_DESK_KEYS`; ``test_migration_0055`` proves
the seed minus these keys equals ``flow_v2/1`` minus the same keys."""

OPERATOR_6_DESK_KEYS: tuple[str, ...] = (
    "exit_key",
    "target_x",
    "trailing_pct",
    "trailing_arm_x",
    "max_hold_s",
    "exit_on_line_break",
    "size_sol",
    "max_sol_per_bet",
    "max_exposure_per_mint_sol",
    "max_open_positions",
    "ttl_s",
    "pedigree_repeat_dumper",
)
"""The twelve keys :data:`OPERATOR_6_OVERRIDES` writes — frozen beside it so a
test can subtract them from both rows and compare what is left."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{OPERATOR_6_RULE_SET_ID}', 'operator', '6', 'operator',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{OPERATOR_6_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', NULL, 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{OPERATOR_6_RULE_SET_ID}'"
)


def seed_operator_6() -> None:
    """Idempotent on a database already at ``0055``; nothing is retired —
    ``operator/5`` keeps running beside ``operator/6``."""
    op.execute(_SEED)


def unseed_operator_6() -> None:
    op.execute(_UNSEED)


_LIVE_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_live_orders",
        "real orders were placed under the seeded operator/6 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_live_positions",
        "real positions exist under the seeded operator/6 set - "
        "the seed cannot be removed under them",
    ),
)
"""The two live tables reach the set only through ``meme_proposals``; they are
counted first so the message names the money, never just the proposal."""

_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded operator/6 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded operator/6 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded operator/6 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded operator/6 set - the seed cannot be removed under them",
    ),
)
"""``0049``–``0054``'s four: every table with a ``rule_set_id`` foreign key to
``meme_rule_sets``, named so the ``DELETE`` fails with the §17.7 sentence that
says what was about to be lost and how to copy it out first."""


def _refuse(table: str, predicate: str, why: str) -> None:
    safe_predicate = predicate.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {why}', "
        f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
        f"END IF; END $$;"
    )


def refuse_a_downgrade_that_would_orphan_an_operator_6_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop.
    Real orders and positions first (joined through their proposal), then the
    four tables that reference the set directly."""
    through_proposal = (
        "WHERE proposal_id IN (SELECT id FROM meme_proposals "  # noqa: S608 - frozen id
        f"WHERE rule_set_id = '{OPERATOR_6_RULE_SET_ID}')"
    )
    for table, why in _LIVE_GUARDED:
        _refuse(table, through_proposal, why)
    direct = f"WHERE rule_set_id = '{OPERATOR_6_RULE_SET_ID}'"
    for table, why in _GUARDED:
        _refuse(table, direct, why)
