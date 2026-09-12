"""``0026_meme_lines`` — the lines Everton draws by hand become columns, the
hype of a coin too young to have a line becomes a score, and a paper bet may
be a probe or the second leg that scales it (T4.10, EXP-M2/EXP-M3).

**``meme_features_1m`` gains thirteen columns** (``meme_features_v3``): the
line of the last two local lows (``support_line_sol``, ``support_line_slope``,
``higher_lows``, ``distance_to_support_pct``), the window's extremes and the
breakout against the *previous* window (``high_15m_sol``, ``low_15m_sol``,
``breakout_15m``), the ln(mcap) slopes (``mcap_slope_5m``, ``mcap_slope_15m``),
the count and the reason (``line_points``, ``line_reason``) and the documented
hype score with its reason (``hype_score``, ``hype_reason``). Every CHECK below
is scoped to ``line_points IS NOT NULL`` — the mark of a row a lines-aware fold
wrote. A row folded before this revision carries no ``line_points``, no line
and no hype, and **no invented reason**: the brief's vocabulary (``too_few_points``,
``no_snapshot``, ``flat``, ``out_of_range``; ``no_tape_no_board``, ``partial``)
names what a fold saw, and no fold saw those minutes.

**``meme_paper_bets`` gains ``parent_bet_id`` and ``leg``** (``probe`` |
``scale`` | ``single``, default ``single`` so every bet of today keeps its
meaning): a ``scale`` leg names the probe it rides on, and only a ``scale``
leg does (biconditional CHECK); the parent is a foreign key into the same
table, indexed where present.

**The seed plants the two pre-registered arms** (``research_only``, parameters
frozen in the brief and in ``obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md``
/ ``EXP-M3-sonda-de-hype.md``): ``trendline_v0/1`` and ``hype_probe_v0/1``,
with fixed ids like ``0022``'s so two databases agree on what the diary names.

**The downgrade refuses** while a bet carries a leg other than ``single`` or a
parent, while a feature row carries ``line_points`` (a line a fold drew is
evidence), or while a proposal or a bet references either seeded set; the seed
alone reverses. ``ADD COLUMN`` without a volatile default and ``ADD CONSTRAINT``
on ``meme_paper_bets`` (a table of hundreds of rows) open no maintenance
window; the CHECKs on ``meme_features_1m`` are added ``NOT VALID`` and then
``VALIDATE``d (``SHARE UPDATE EXCLUSIVE``, the ``0025`` pattern), so the fold's
inserts keep flowing during the scan.
"""

from __future__ import annotations

from alembic import op

FEATURE_COLUMNS_0026: tuple[str, ...] = (
    "mcap_slope_5m",
    "mcap_slope_15m",
    "high_15m_sol",
    "low_15m_sol",
    "breakout_15m",
    "support_line_sol",
    "support_line_slope",
    "higher_lows",
    "distance_to_support_pct",
    "line_points",
    "line_reason",
    "hype_score",
    "hype_reason",
)
"""Frozen: what ``0026`` adds to ``meme_features_1m`` and what its downgrade removes."""

BET_COLUMNS_0026: tuple[str, ...] = ("parent_bet_id", "leg")
LINE_REASONS_0026: tuple[str, ...] = ("too_few_points", "no_snapshot", "flat", "out_of_range")
HYPE_REASONS_0026: tuple[str, ...] = ("no_tape_no_board", "partial")
LEGS_0026: tuple[str, ...] = ("probe", "scale", "single")

TRENDLINE_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000003"
HYPE_PROBE_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000004"
"""Fixed, like ``0022``'s two, so the diary and the desk name the same ids on
every database."""

_ADD_FEATURE_COLUMNS = (
    "ALTER TABLE meme_features_1m "
    "ADD COLUMN mcap_slope_5m numeric(12, 6), "
    "ADD COLUMN mcap_slope_15m numeric(12, 6), "
    "ADD COLUMN high_15m_sol numeric(28, 10), "
    "ADD COLUMN low_15m_sol numeric(28, 10), "
    "ADD COLUMN breakout_15m boolean, "
    "ADD COLUMN support_line_sol numeric(28, 10), "
    "ADD COLUMN support_line_slope numeric(12, 6), "
    "ADD COLUMN higher_lows boolean, "
    "ADD COLUMN distance_to_support_pct numeric(9, 6), "
    "ADD COLUMN line_points smallint, "
    "ADD COLUMN line_reason text, "
    "ADD COLUMN hype_score numeric(9, 6), "
    "ADD COLUMN hype_reason text"
)


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_FEATURE_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_meme_features_1m_support_line_is_null_with_a_reason",
        "line_points IS NULL OR (support_line_sol IS NULL) = (line_reason IS NOT NULL)",
    ),
    (
        "ck_meme_features_1m_support_group_is_absent_together",
        "line_points IS NULL OR ((support_line_sol IS NULL) = (support_line_slope IS NULL) "
        "AND (support_line_sol IS NULL) = (higher_lows IS NULL) "
        "AND (support_line_sol IS NULL) = (distance_to_support_pct IS NULL))",
    ),
    (
        "ck_meme_features_1m_line_reason_is_a_known_label",
        f"line_reason IS NULL OR line_reason IN ({_labels(LINE_REASONS_0026)})",
    ),
    (
        "ck_meme_features_1m_window_extremes_are_absent_together",
        "(high_15m_sol IS NULL) = (low_15m_sol IS NULL)",
    ),
    (
        "ck_meme_features_1m_line_points_are_not_negative",
        "line_points IS NULL OR line_points >= 0",
    ),
    (
        "ck_meme_features_1m_hype_is_null_without_both_sources",
        "line_points IS NULL OR (hype_score IS NULL) = "
        "coalesce(hype_reason = 'no_tape_no_board', false)",
    ),
    (
        "ck_meme_features_1m_hype_reason_is_a_known_label",
        f"hype_reason IS NULL OR hype_reason IN ({_labels(HYPE_REASONS_0026)})",
    ),
    (
        "ck_meme_features_1m_hype_score_is_a_fraction",
        "hype_score IS NULL OR (hype_score >= 0 AND hype_score <= 1)",
    ),
)
"""``hype_reason = 'partial'`` sits next to a **non-null** score by the brief's
own rule (one of the two sources spoke), so the biconditional is against the
one reason that means "no score", not against "any reason"."""

_ADD_BET_COLUMNS = (
    "ALTER TABLE meme_paper_bets "
    "ADD COLUMN parent_bet_id uuid, "
    "ADD COLUMN leg text NOT NULL DEFAULT 'single'"
)
_BET_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    (
        "fk_meme_paper_bets_parent_bet_id_meme_paper_bets",
        "FOREIGN KEY (parent_bet_id) REFERENCES meme_paper_bets (id)",
    ),
    ("ck_meme_paper_bets_leg_is_a_known_label", f"CHECK (leg IN ({_labels(LEGS_0026)}))"),
    (
        "ck_meme_paper_bets_a_scale_leg_names_its_probe",
        "CHECK ((leg = 'scale') = (parent_bet_id IS NOT NULL))",
    ),
)
_BET_INDEX = (
    "CREATE INDEX ix_meme_paper_bets_parent_bet_id ON meme_paper_bets (parent_bet_id) "
    "WHERE parent_bet_id IS NOT NULL"
)

_TRENDLINE_PARAMS = (
    '"gate_key": "a_linha_manda", "gate_version": 1, '
    '"exit_key": "alvo_2x_trailing_30_tempo_15m_linha", "exit_version": 1, '
    '"min_age_s": 300, "max_age_s": 600, "min_progress_pct": "2", "max_progress_pct": "50", '
    '"max_participation_pct": "1", "require_creator_not_net_seller": true, '
    '"require_higher_lows": true, "require_breakout_15m": true, '
    '"min_distance_to_support_pct": "0", "max_distance_to_support_pct": "0.25", '
    '"size_sol": "0.05", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900, '
    '"max_loss_pct": "50", "exit_on_line_break": true, "line_break_snapshots": 2, '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.05", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 3, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""EXP-M2, "a linha manda": everything ``meme_paper_v0`` asks (age raised to
≥ 5 min so a line can exist, progress 2–50 %, participation ≤ 1 %, creator not
a net seller) **and** ``higher_lows`` **and** ``breakout_15m`` **and** the
distance to support in [0, 0,25]; 0,05 SOL; exits 2×, trailing 30 %, 900 s,
the line closed below for 2 snapshots, migration, creator dump. The 50 % loss
floor is EXP-M1's, carried over — the brief names no other."""

_HYPE_PROBE_PARAMS = (
    '"gate_key": "sonda_de_hype", "gate_version": 1, '
    '"exit_key": "alvo_3x_trailing_40_tempo_10m", "exit_version": 1, '
    '"min_age_s": 30, "max_age_s": 300, "min_progress_pct": "0", "max_progress_pct": "100", '
    '"require_progress": false, "max_participation_pct": "1", '
    '"require_creator_not_net_seller": true, "min_hype_score": "0.6", '
    '"max_dev_share": "0.10", "dev_share_unknown_allowed": true, "max_snipers": 2, '
    '"size_sol": "0.01", "target_x": "3", "trailing_pct": "40", "max_hold_s": 600, '
    '"max_loss_pct": "50", "scale_size_sol": "0.04", "scale_gate": "trendline_v0/1", '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.04", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 5, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""EXP-M3, "semi-comprado por hype": age 30 s–5 min (before a line can exist),
``hype_score ≥ 0,6``, ``dev_share ≤ 0,10`` **or** unknown with a reason,
``snipers ≤ 2``, creator not a net seller (unknown refuses), participation
≤ 1 %; progress is not a criterion (the brief lists none and a 30-second-old
curve rarely has a denominator yet). The probe is 0,01 SOL (a fifth of the
size) with time stop 600 s, trailing 40 %, target 3×; the second leg is
0,04 SOL, opened only while the probe is open and ``trendline_v0/1`` is
satisfied for the same mint (``max_sol_per_bet`` = 0,04, exposure per mint
0,05 = probe + scale). Ceilings: wallet 2,0 SOL, day loss 0,20 SOL, at most
five open probes (a scale leg rides on its probe's slot)."""

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{TRENDLINE_RULE_SET_ID}', 'trendline_v0', '1', 'research_only',
   '{{{_TRENDLINE_PARAMS}}}'::jsonb,
   'hunter_indicators.meme.rules:evaluate_entry+evaluate_exit', 'EXP-M2', 'active'),
  ('{HYPE_PROBE_RULE_SET_ID}', 'hype_probe_v0', '1', 'research_only',
   '{{{_HYPE_PROBE_PARAMS}}}'::jsonb,
   'hunter_indicators.meme.rules:evaluate_entry+evaluate_exit', 'EXP-M3', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants

_UNSEED = (
    "DELETE FROM meme_rule_sets WHERE id IN "  # noqa: S608 - this module's own frozen ids
    f"('{TRENDLINE_RULE_SET_ID}', '{HYPE_PROBE_RULE_SET_ID}')"
)


def add_line_columns() -> None:
    """The thirteen columns and their eight CHECKs (``NOT VALID`` + ``VALIDATE``)."""
    op.execute(_ADD_FEATURE_COLUMNS)
    for name, predicate in _FEATURE_CHECKS:
        op.execute(
            f"ALTER TABLE meme_features_1m ADD CONSTRAINT {name} CHECK ({predicate}) NOT VALID"
        )
        op.execute(f"ALTER TABLE meme_features_1m VALIDATE CONSTRAINT {name}")


def drop_line_columns() -> None:
    for name, _predicate in reversed(_FEATURE_CHECKS):
        op.execute(f"ALTER TABLE meme_features_1m DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE meme_features_1m "
        + ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in FEATURE_COLUMNS_0026)
    )


def add_bet_legs() -> None:
    """``parent_bet_id`` and ``leg`` on the bets, the self-reference, the two
    CHECKs and the partial index."""
    op.execute(_ADD_BET_COLUMNS)
    for name, clause in _BET_CONSTRAINTS:
        op.execute(f"ALTER TABLE meme_paper_bets ADD CONSTRAINT {name} {clause}")
    op.execute(_BET_INDEX)


def drop_bet_legs() -> None:
    op.execute("DROP INDEX IF EXISTS ix_meme_paper_bets_parent_bet_id")
    for name, _clause in reversed(_BET_CONSTRAINTS):
        op.execute(f"ALTER TABLE meme_paper_bets DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE meme_paper_bets "
        + ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in BET_COLUMNS_0026)
    )


def seed_line_rule_sets() -> None:
    """The two arms of T4.10. Idempotent on ``(name, version)``."""
    op.execute(_SEED)


def unseed_line_rule_sets() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str, str], ...] = (
    (
        "meme_paper_bets",
        "WHERE leg <> 'single' OR parent_bet_id IS NOT NULL",
        "bets carry a leg (a probe or its second leg) - dropping the column would turn a "
        "semi-bought probe and its scale into two unrelated single bets",
    ),
    (
        "meme_features_1m",
        "WHERE line_points IS NOT NULL",
        "feature rows carry the lines and the hype a fold drew - dropping them would "
        "silently turn measured lines into absent ones",
    ),
    (
        "meme_proposals",
        f"WHERE rule_set_id IN ('{TRENDLINE_RULE_SET_ID}', '{HYPE_PROBE_RULE_SET_ID}')",
        "proposals reference the seeded trendline_v0/hype_probe_v0 sets - the seed cannot "
        "be removed under them",
    ),
    (
        "meme_paper_bets",
        f"WHERE rule_set_id IN ('{TRENDLINE_RULE_SET_ID}', '{HYPE_PROBE_RULE_SET_ID}')",
        "bets reference the seeded trendline_v0/hype_probe_v0 sets - the seed cannot be "
        "removed under them",
    ),
)


def refuse_a_downgrade_that_would_lose_a_line_or_a_leg() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, predicate, why in _GUARDED:
        safe_why = why.replace("'", "''")
        # The predicate is quoted twice: bare in the COUNT, and inside the HINT's
        # string literal — where its own quotes (``leg <> 'single'``) must double.
        safe_predicate = predicate.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
