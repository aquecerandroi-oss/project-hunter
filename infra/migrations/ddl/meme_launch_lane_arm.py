"""``0053_meme_launch_lane_arm`` — the launch lane's own rule set, ``launch_v0/1``
(T4.67a, EXP-M18, ``obsidian/05-EXPERIMENTS/EXP-M18-sniper-de-lancamento.md``).

**A new ``clock``, not a new gate on an old one.** ``launch_v0/1`` has no
``gate_key``/``gate_version``, no age/progress/participation window, no
holders/tape/pedigree switch — the launch lane never reads a 15-second or
one-minute row (``docs/RISK_ENGINE_MEME.md`` §9's own launch-lane section).
``params.clock = "event"`` is what marks it as this lane's own:
``hunter_meme_worker.lab_models.CLOCKS`` never lists it, so the 15-second and
one-minute engines skip a ``clock = "event"`` row by construction — no code
change to either engine was needed for this seed to be safe beside them.

**Six params, exactly the pre-registration's numbers**: ``size_sol`` (0,01
SOL, the arm's own ticket), ``max_creator_initial_sol`` (2 SOL, the dev-buy
ceiling), ``exit_key`` (``lancamento_6s_ou_primeiro_sell``, named rather than
numbered — the launch lane has no ``EntryGate``/``ExitRules`` pair to key
against), ``time_stop_s`` (6), ``exit_on_first_third_party_sell`` (``true``)
and ``max_drawdown_from_peak_pct`` (20, EXP-M13's own guard reused at a
tighter number for a position meant to live seconds, not minutes).

**Paper by construction, not by flag** — the same sentence ``0049``/``0050``/
``0052`` already prove from the executor's own source: ``kind =
'research_only'`` and ``hunter_meme_executor.auto_approve`` only ever opens
proposals of a ``kind = 'operator'`` set.

**One schema change, and it only widens.** The launch lane prices its own
paper bets from a chain event, never a ``meme_curve_snapshots`` row
(``launch_lane_bets.py``, ``docs/RISK_ENGINE_MEME.md`` §9), so ``mark_source``
needs a third label beside ``0029``'s ``curve``/``pool_tape``: ``solana_ws``.
The CHECK is dropped and re-added with the wider list (``packages/core/hunter_core/db/models/meme_bets.py``'s
``MARK_SOURCES`` carries the same three, so ``alembic check`` stays clean);
the downgrade does **not** narrow it back — a bet already closed under
``solana_ws`` must never be left with a CHECK that refuses its own row.
"""

from __future__ import annotations

from alembic import op

LAUNCH_V0_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000017"

_MARK_SOURCE_CHECK = "ck_meme_paper_bets_mark_source_is_a_known_label"
_DROP_MARK_SOURCE_CHECK = f"ALTER TABLE meme_paper_bets DROP CONSTRAINT {_MARK_SOURCE_CHECK}"
_ADD_MARK_SOURCE_CHECK = (
    f"ALTER TABLE meme_paper_bets ADD CONSTRAINT {_MARK_SOURCE_CHECK} "
    "CHECK (mark_source IS NULL OR mark_source IN ('curve', 'pool_tape', 'solana_ws'))"
)

LAUNCH_PARAMS = (
    '"size_sol": "0.01", "max_creator_initial_sol": "2", '
    '"exit_key": "lancamento_6s_ou_primeiro_sell", "time_stop_s": 6, '
    '"exit_on_first_third_party_sell": true, "max_drawdown_from_peak_pct": "20", '
    '"clock": "event"'
)

_CODE_REF = (
    "hunter_indicators.meme.launch_lane:evaluate_launch"
    "+hunter_meme_worker.launch_lane_pricing:exit_trigger"
)

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{LAUNCH_V0_RULE_SET_ID}', 'launch_v0', '1', 'research_only',
   '{{{LAUNCH_PARAMS}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M18', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{LAUNCH_V0_RULE_SET_ID}'"
)


def widen_mark_source() -> None:
    """Two statements — asyncpg refuses more than one command per prepared
    statement. Idempotent-by-name: a re-run would fail on the ``DROP
    CONSTRAINT`` of a constraint that no longer has the old body — this
    revision runs once, like every other, and the guard is Alembic's own
    version table."""
    op.execute(_DROP_MARK_SOURCE_CHECK)
    op.execute(_ADD_MARK_SOURCE_CHECK)


def seed_launch_lane_arm() -> None:
    """Idempotent on a database already at ``0053``."""
    op.execute(_SEED)


def unseed_launch_lane_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded launch_v0/1 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded launch_v0/1 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded launch_v0/1 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded launch_v0/1 set - the seed cannot be removed under them",
    ),
)
"""Every table with a ``rule_set_id`` foreign key to ``meme_rule_sets``
(``0049``/``0050``/``0052``'s own four), named so the ``DELETE`` fails with
the §17.7 sentence that says what was about to be lost."""


def refuse_a_downgrade_that_would_orphan_a_launch_lane_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{LAUNCH_V0_RULE_SET_ID}'"
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
