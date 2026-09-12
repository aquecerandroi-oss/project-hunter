"""``0029_meme_moonshot`` — a paper bet may survive the migration and be marked
on the PumpSwap pool's tape; the moonshot arms (10×/25×) and ``operator/2``
(T4.11, EXP-M4: "pode colocar valores mais alto para sair num mega ROI, meme
coin é diferente").

**``meme_paper_bets`` gains ``mark_source`` and ``mark_stale_s``.**
``mark_source`` ∈ {``curve``, ``pool_tape``} names what priced the last mark:
the curve's snapshot (every mark of today — backfilled ``'curve'`` where a
mark exists, because that is what it was) or the pool's last trade after the
migration. ``(mark_sol IS NULL) = (mark_source IS NULL)``: a mark without a
source is a number nobody can explain. ``mark_stale_s`` is how many seconds
the tape had been silent when the mark was refreshed (the desk's "marca
envelhecida há Ns"); never negative, ``NULL`` when the loop did not measure it.

**``meme_trades`` gains ``program``** (``pump`` | ``pump_amm``): the venue of
the fill, which the ``swap-api`` states on every row and the puller used to
filter on *before* writing (T4.2c kept only the curve). Rows written before
this revision are ``NULL`` and are curve rows by construction — every reader
of the curve's tape says ``coalesce(program, 'pump') = 'pump'``. The CHECK
is added ``NOT VALID`` then ``VALIDATE``d (``SHARE UPDATE EXCLUSIVE``; the
tape keeps inserting) — the ``0025``/``0026`` pattern on a partitioned table.

**The seed plants the two moonshot arms and ``operator/2``, and retires
``operator/1``.** ``moonshot_v0/1`` (10×) and ``moonshot_v0/2`` (25×, the
falsification sibling of the tail) are ``research_only`` with the parameters
frozen in the brief and in ``obsidian/05-EXPERIMENTS/EXP-M4-moonshot.md``:
the gate of ``hype_probe_v0``, 0,02 SOL, trailing 50 % armed only after 3×,
7 200 s, ``exit_on_migration = false``, exits ``creator_dump`` and ``dead``
(tape silent ≥ 900 s **and** mark ≤ 50 % of the cost), 0,20 SOL a day, 8
open. ``operator/2`` proposes with the same geometry as its ``suggested``
(size 0,05) and waits for the desk; ``operator/1`` is ``retired`` with
``retired_at`` — the desk files manual buys under the active ``operator`` set.
Fixed ids, like ``0022``'s and ``0026``'s.

**Upgrade guard: none, and that is an assertion** — nullable columns, a
backfill implied by the existing rows, scoped CHECKs, ``ON CONFLICT DO
NOTHING``. **The downgrade refuses** while a pool trade exists (dropping
``program`` would turn the pool's tape into curve trades), while a bet was
marked or closed on the pool (``mark_source = 'pool_tape'`` or ``exit.reason
= 'dead'``), or while a proposal or a bet references the three seeded sets;
the seed reverses and ``operator/1`` comes back ``active``.
"""

from __future__ import annotations

from alembic import op

BET_COLUMNS_0029: tuple[str, ...] = ("mark_source", "mark_stale_s")
TRADE_COLUMNS_0029: tuple[str, ...] = ("program",)
MARK_SOURCES_0029: tuple[str, ...] = ("curve", "pool_tape")
PROGRAMS_0029: tuple[str, ...] = ("pump", "pump_amm")

MOONSHOT_10X_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000005"
MOONSHOT_25X_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000006"
OPERATOR_2_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000007"
OPERATOR_1_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000002"
"""``operator/1`` is ``0022``'s; the three new ids continue the sequence."""


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_ADD_BET_COLUMNS = (
    "ALTER TABLE meme_paper_bets ADD COLUMN mark_source text, ADD COLUMN mark_stale_s integer"
)
_BACKFILL_MARK_SOURCE = (
    "UPDATE meme_paper_bets SET mark_source = 'curve' WHERE mark_sol IS NOT NULL"
)
"""Every mark written before this revision was priced on the curve: the
backfill states what the rows already imply, never a guess (§17.7)."""
_BET_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_meme_paper_bets_mark_source_is_a_known_label",
        f"mark_source IS NULL OR mark_source IN ({_labels(MARK_SOURCES_0029)})",
    ),
    ("ck_meme_paper_bets_a_mark_names_its_source", "(mark_sol IS NULL) = (mark_source IS NULL)"),
    (
        "ck_meme_paper_bets_mark_stale_s_is_not_negative",
        "mark_stale_s IS NULL OR mark_stale_s >= 0",
    ),
)

_ADD_TRADE_COLUMN = "ALTER TABLE meme_trades ADD COLUMN program text"
_TRADE_CHECK = (
    "ck_meme_trades_program_is_a_known_label",
    f"program IS NULL OR program IN ({_labels(PROGRAMS_0029)})",
)

_HYPE_GATE = (
    '"gate_key": "sonda_de_hype", "gate_version": 1, '
    '"min_age_s": 30, "max_age_s": 300, "min_progress_pct": "0", "max_progress_pct": "100", '
    '"require_progress": false, "max_participation_pct": "1", '
    '"require_creator_not_net_seller": true, "min_hype_score": "0.6", '
    '"max_dev_share": "0.10", "dev_share_unknown_allowed": true, "max_snipers": 2'
)
"""The gate of ``hype_probe_v0/1`` (``0026``), verbatim: the brief says "porta =
a mesma do hype_probe_v0"."""

_MOONSHOT_GEOMETRY = (
    '"size_sol": "0.02", "trailing_pct": "50", "trailing_arm_x": "3", "max_hold_s": 7200, '
    '"max_loss_pct": "100", "exit_on_migration": false, '
    '"exit_on_dead": true, "dead_stale_s": 900, "dead_mark_pct": "50", '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.02", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 8, "max_exposure_per_mint_sol": "0.02", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""What the two arms share. ``max_loss_pct = 100`` is a **declared** choice
the brief does not spell out: the exits it lists are the target, the trailing
armed at 3×, the 2 h horizon, ``creator_dump`` and ``dead`` — a 50 % floor
would sell most moonshots on the drawdown they are meant to ride. The
``dead`` rule (silent 15 min **and** ≤ 50 % of the cost) is the floor."""

_MOONSHOT_10X_PARAMS = (
    f"{_HYPE_GATE}, "
    '"exit_key": "alvo_10x_trailing_50_apos_3x_tempo_2h", "exit_version": 1, '
    f'"target_x": "10", {_MOONSHOT_GEOMETRY}'
)
_MOONSHOT_25X_PARAMS = (
    f"{_HYPE_GATE}, "
    '"exit_key": "alvo_25x_trailing_50_apos_3x_tempo_2h", "exit_version": 1, '
    f'"target_x": "25", {_MOONSHOT_GEOMETRY}'
)
_OPERATOR_2_PARAMS = (
    '"gate_key": "comprar_cedo_na_curva", "gate_version": 1, '
    '"exit_key": "alvo_10x_trailing_50_apos_3x_tempo_2h", "exit_version": 1, '
    '"min_age_s": 30, "max_age_s": 600, "min_progress_pct": "2", "max_progress_pct": "50", '
    '"max_participation_pct": "1", "require_creator_not_net_seller": true, '
    '"size_sol": "0.05", "target_x": "10", "trailing_pct": "50", "trailing_arm_x": "3", '
    '"max_hold_s": 7200, "max_loss_pct": "100", "exit_on_migration": false, '
    '"exit_on_dead": true, "dead_stale_s": 900, "dead_mark_pct": "50", '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.05", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 3, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""``operator/2``: ``operator/1``'s gate and ceilings, the brief's new
``suggested`` (10×, trailing 50 % after 3×, 7 200 s, 0,05 SOL,
``exit_on_migration = false``) and the same declared ``max_loss_pct = 100``
(with ``dead``) as the arms. The approval sheet stays editable: the four
numbers come from the operator's ``decision``; the switches from here."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{MOONSHOT_10X_RULE_SET_ID}', 'moonshot_v0', '1', 'research_only',
   '{{{_MOONSHOT_10X_PARAMS}}}'::jsonb, '{_CODE_REF}', 'EXP-M4', 'active'),
  ('{MOONSHOT_25X_RULE_SET_ID}', 'moonshot_v0', '2', 'research_only',
   '{{{_MOONSHOT_25X_PARAMS}}}'::jsonb, '{_CODE_REF}', 'EXP-M4', 'active'),
  ('{OPERATOR_2_RULE_SET_ID}', 'operator', '2', 'operator',
   '{{{_OPERATOR_2_PARAMS}}}'::jsonb, '{_CODE_REF}', NULL, 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants

_RETIRE_OPERATOR_1 = (
    "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "  # noqa: S608
    f"WHERE id = '{OPERATOR_1_RULE_SET_ID}' AND status = 'active'"
)
_REVIVE_OPERATOR_1 = (
    "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL "  # noqa: S608
    f"WHERE id = '{OPERATOR_1_RULE_SET_ID}'"
)
_UNSEED = (
    "DELETE FROM meme_rule_sets WHERE id IN "  # noqa: S608 - this module's own frozen ids
    f"('{MOONSHOT_10X_RULE_SET_ID}', '{MOONSHOT_25X_RULE_SET_ID}', '{OPERATOR_2_RULE_SET_ID}')"
)
_SEEDED_IDS = (
    f"('{MOONSHOT_10X_RULE_SET_ID}', '{MOONSHOT_25X_RULE_SET_ID}', '{OPERATOR_2_RULE_SET_ID}')"
)


def add_mark_columns() -> None:
    """``mark_source``/``mark_stale_s``, the backfill the rows imply, three CHECKs."""
    op.execute(_ADD_BET_COLUMNS)
    op.execute(_BACKFILL_MARK_SOURCE)
    for name, predicate in _BET_CHECKS:
        op.execute(f"ALTER TABLE meme_paper_bets ADD CONSTRAINT {name} CHECK ({predicate})")


def drop_mark_columns() -> None:
    for name, _predicate in reversed(_BET_CHECKS):
        op.execute(f"ALTER TABLE meme_paper_bets DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE meme_paper_bets "
        + ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in BET_COLUMNS_0029)
    )


def add_trade_program() -> None:
    """``meme_trades.program`` and its CHECK (``NOT VALID`` + ``VALIDATE``)."""
    op.execute(_ADD_TRADE_COLUMN)
    name, predicate = _TRADE_CHECK
    op.execute(f"ALTER TABLE meme_trades ADD CONSTRAINT {name} CHECK ({predicate}) NOT VALID")
    op.execute(f"ALTER TABLE meme_trades VALIDATE CONSTRAINT {name}")


def drop_trade_program() -> None:
    name, _predicate = _TRADE_CHECK
    op.execute(f"ALTER TABLE meme_trades DROP CONSTRAINT IF EXISTS {name}")
    op.execute("ALTER TABLE meme_trades DROP COLUMN IF EXISTS program")


def seed_moonshot_rule_sets() -> None:
    """The two arms and ``operator/2``; ``operator/1`` retired. Idempotent."""
    op.execute(_SEED)
    op.execute(_RETIRE_OPERATOR_1)


def unseed_moonshot_rule_sets() -> None:
    op.execute(_UNSEED)
    op.execute(_REVIVE_OPERATOR_1)


_GUARDED: tuple[tuple[str, str, str], ...] = (
    (
        "meme_trades",
        "WHERE program = 'pump_amm'",
        "pool trades exist - dropping the column would turn the PumpSwap pool tape into "
        "bonding-curve trades",
    ),
    (
        "meme_paper_bets",
        "WHERE mark_source = 'pool_tape' OR exit ->> 'reason' = 'dead'",
        "bets were marked or closed on the pool tape - dropping the columns would leave marks "
        "nobody can explain",
    ),
    (
        "meme_proposals",
        f"WHERE rule_set_id IN {_SEEDED_IDS}",
        "proposals reference the seeded moonshot_v0/operator/2 sets - the seed cannot be "
        "removed under them",
    ),
    (
        "meme_paper_bets",
        f"WHERE rule_set_id IN {_SEEDED_IDS}",
        "bets reference the seeded moonshot_v0/operator/2 sets - the seed cannot be removed "
        "under them",
    ),
)


def refuse_a_downgrade_that_would_lose_the_pool_tape_or_a_moonshot() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, predicate, why in _GUARDED:
        safe_why = why.replace("'", "''")
        # The predicate is quoted twice: bare in the COUNT, and inside the HINT's
        # string literal — where its own quotes (``= 'pool_tape'``) must double.
        safe_predicate = predicate.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
