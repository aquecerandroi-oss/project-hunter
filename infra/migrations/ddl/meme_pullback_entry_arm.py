"""``0063_meme_pullback_entry_arm`` — the entry at the pullback on a new
cohort (T4.91, H-017, EXP-M24,
``obsidian/05-EXPERIMENTS/EXP-M24-entrada-no-recuo.md``).

**What it is — and what it is not.** One arm, ``recuo_v1/1`` (``…001d``),
``research_only`` under ``exp_ref = 'EXP-M24'``: the desk's own gate, the
desk's own exit, and **one** difference in the entry — after the gate passes
at ``t0`` it waits for the price to fall 3 % from the max seen since ``t0``
and buys at the first trade that touches it, within 60 s; no pullback, no
entry (``hunter_meme_worker.entry_pullback``). R77 refuted H-016 (the +5 pp
do not exist, ``KB-0157``) but its best cell, 3 % / 60 s, gave +2,28 pp per
SOL in paper from the **entry price** alone — a lead born of the same
population, pre-registered as **H-017** (23/09/2026 ~22:40 BRT) and judged
only on decisions after this deploy. A different cell is a new arm and a new
EXP, never an edit of this row.

**The gate is ``operator/5``'s effective row, copied at upgrade time — on
purpose, and unlike ``0055``/``0060``.** EXP-M24 pairs every armed decision
with ``operator/5``'s paper shadow of the same decision at ``t0``; that
pairing only holds if the two gates are the same document. ``operator/5``'s
live row was edited by ``infra/scripts/meme_rule_set.py --set-param`` on the
VPS (gate ``fluxo_e_holders/2``, the exit, the size — §54), and no constant
in this tree carries those edits, so the seed is ``operator/5.params ||``
:data:`PULLBACK_ARM_OVERRIDES` read in the same statement. Consequence,
declared: on the VPS the arm is the desk as it runs on the day of the deploy;
on a fresh database (CI) it is ``operator/5``'s seed (``0039``) — and
``test_migration_0063`` proves on either that ``arm − the arm's keys ==
operator/5 − the same keys``, byte for byte. The copied document is this
row's own ``params`` (``--history``/``--validate recuo_v1/1`` read it); a
later edit of ``operator/5`` splits the EXP-M24 cohorts, it does not follow
into the arm. The upgrade **refuses** when ``operator/5`` is missing or not
active (nothing to copy is not an arm), and when its ``clock`` is anything but
``15s`` (absent/``null`` included): the event lane reads only ``15s`` sets and
``entry_pullback_of`` refuses a pullback on any other clock.

**The overrides** (:data:`PULLBACK_ARM_KEYS`, and nothing else):

- the exit and the size the brief names, restated so a CI database gets them
  too — alvo 1,15×, trailing 10 % armed at the entry (``trailing_arm_x
  null``), 300 s, 0,07 SOL (``size_sol`` = ``max_sol_per_bet`` =
  ``max_exposure_per_mint_sol``), ``exit_key "alvo_1_15x_trailing_10_tempo_5m"``;
- the paper ceilings ``max_open_positions 25``, ``daily_loss_cap_sol "10.0"``,
  ``wallet_max_sol "100.0"`` — ``0060``'s own reasoning: at the desk's
  ceilings the arm would latch shut on its own bankroll and the sample would
  measure that, not the entry;
- ``entry_pullback_pct "3"`` and ``entry_pullback_window_s 60`` (H-017's cell).

**Paper by construction, not by flag** — ``kind = 'research_only'``:
``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED`` selects only ``rs.kind
= 'operator'`` (``test_migration_0063`` runs that very query against a
proposal of this arm), and a ``research_only`` proposal is born ``approved``
by ``rules`` and filled by the Lab's paper engine. The clock is
``operator/5``'s ``15s``: the event lane reads the set and arms it; the
15-second lane never proposes for it (``lab_fast``, ``entry_pullback
_event_lane_only``). The desk is not touched and nothing is retired.

**Downgrade (§17.7)** refuses while a proposal, a bet, a param-history row or
a sampled refusal references the arm — the four tables ``0049``–``0060``
guard. The slug is 28 characters (``VARCHAR(32)``).
"""

from __future__ import annotations

from alembic import op

from ddl.meme_creator_repeat import OPERATOR_5_RULE_SET_ID

PULLBACK_ARM_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000001d"
SEEDED_RULE_SET_IDS_0063: tuple[str, ...] = (PULLBACK_ARM_RULE_SET_ID,)

PULLBACK_ARM_OVERRIDES = (
    '"exit_key": "alvo_1_15x_trailing_10_tempo_5m", '
    '"target_x": "1.15", "trailing_pct": "10", "trailing_arm_x": null, "max_hold_s": 300, '
    '"size_sol": "0.07", "max_sol_per_bet": "0.07", "max_exposure_per_mint_sol": "0.07", '
    '"max_open_positions": 25, "daily_loss_cap_sol": "10.0", "wallet_max_sol": "100.0", '
    '"entry_pullback_pct": "3", "entry_pullback_window_s": 60'
)
"""Exactly :data:`PULLBACK_ARM_KEYS`; every other key is ``operator/5``'s."""

PULLBACK_ARM_KEYS: tuple[str, ...] = (
    "exit_key",
    "target_x",
    "trailing_pct",
    "trailing_arm_x",
    "max_hold_s",
    "size_sol",
    "max_sol_per_bet",
    "max_exposure_per_mint_sol",
    "max_open_positions",
    "daily_loss_cap_sol",
    "wallet_max_sol",
    "entry_pullback_pct",
    "entry_pullback_window_s",
)

_CODE_REF = (
    "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"
    "+hunter_meme_worker.entry_pullback:ArmedEntry.observe"
)

_SOURCE = f"d.id = '{OPERATOR_5_RULE_SET_ID}' AND d.status = 'active'"
"""The one row the arm is copied from — the guard and the ``INSERT … SELECT``
read the same predicate, so the check and the copy can never disagree."""
_REFUSE_WITHOUT_OPERATOR_5 = (
    "DO $$ BEGIN "  # noqa: S608 - this module's own frozen id
    f"IF NOT EXISTS (SELECT 1 FROM meme_rule_sets d WHERE {_SOURCE}) THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: operator/5 is missing or not active - "
    "recuo_v1/1 copies its effective gate and has nothing to copy', "
    "HINT = 'EXP-M24 pairs the arm with operator/5; seed a new arm against the desk that runs'; "
    "END IF; "
    f"IF NOT EXISTS (SELECT 1 FROM meme_rule_sets d WHERE {_SOURCE} "
    "AND d.params ->> 'clock' = '15s') THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: operator/5 is not on the 15s clock - "
    "recuo_v1/1 would copy a clock the event lane never reads and the Lab cannot load "
    "with an entry pullback', "
    "HINT = 'the arm waits on the event lane: seed it against a 15s desk'; "
    "END IF; END $$;"
)
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
SELECT '{PULLBACK_ARM_RULE_SET_ID}', 'recuo_v1', '1', 'research_only',
       d.params || '{{{PULLBACK_ARM_OVERRIDES}}}'::jsonb,
       '{_CODE_REF}', 'EXP-M24', 'active'
FROM meme_rule_sets d WHERE {_SOURCE}
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{PULLBACK_ARM_RULE_SET_ID}'"
)


def seed_pullback_arm() -> None:
    """Refuses without an active ``operator/5``; idempotent on a database
    already at ``0063``; nothing is retired and the desk is not touched."""
    op.execute(_REFUSE_WITHOUT_OPERATOR_5)
    op.execute(_SEED)


def unseed_pullback_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded recuo_v1 set - they carry EXP-M24's "
        "entry_pullback blocks and cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded recuo_v1 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded recuo_v1 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded recuo_v1 set - they are EXP-M24's "
        "armed/no_pullback counterfactuals and cannot be removed under them",
    ),
)
"""``0049``–``0060``'s four: every table with a ``rule_set_id`` foreign key to
``meme_rule_sets``. The last one matters here: the ``no_pullback`` rows are
the only record of the decisions that did not enter."""


def refuse_a_downgrade_that_would_orphan_a_pullback_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{PULLBACK_ARM_RULE_SET_ID}'"
    safe_predicate = predicate.replace("'", "''")
    for table, why in _GUARDED:
        safe_why = why.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
