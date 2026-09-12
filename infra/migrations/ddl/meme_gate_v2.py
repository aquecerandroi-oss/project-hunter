"""``0030_meme_gate_v2`` — the honest scoreboard, the 15-second series and the
flow gate (T4.16; Everton, 12/09/2026 14:0x BRT: "aparecendo bastante proposta
mas estamos perdendo todas; não está analisando direito? estamos muito lentos?").

**``meme_paper_bets`` gains ``outcome_quality``** (``measured`` |
``indeterminate``, default ``measured``), ``outcome_quality_reason`` and
``outcome_quality_at``. An ``indeterminate`` close is one the instrument could
not price (``rug_no_snapshot``: no photo to sell into inside the window — on
12/09 five of them closed at −1 R while the coin's market cap thirty minutes
later equalled the entry's; −5 of the day's −7,67 R were the radar blinking,
not the market). The row keeps its numbers; the sums stop counting it. The
three CHECKs: a known label; ``indeterminate`` only on a ``closed`` bet; an
``indeterminate`` outcome names its reason and its instant, a ``measured``
one carries neither. **No backfill**: the audited script
(``infra/scripts/meme_reclassify_indeterminate.py --apply --reason``) is the
only way a past row is reclassified, and it leaves a ``system_events`` row.

**``meme_lab_scoreboard_v1`` is rewritten** (dropped and recreated under the
same name and grants): ``wins``, ``pnl_sol``, ``pnl_usd``, ``unpriced_usd``,
``r_sum`` and the drawdown are summed over **measured** closes only, and a new
column ``indeterminate`` counts the rest. The observed-wallet arm of ``0027``
is byte for byte the same with ``0 AS indeterminate``.

**``meme_features_15s``** — the 15-second series of the young mints (monthly
``RANGE`` on ``as_of``, ``MEME_INITIAL_MONTHS_0030``, retention 7 days in
``partition_retention.py``): read-only for ``hunter_app``, append-only for
``hunter_worker``, children hardened like ``0021``'s. Every value/reason pair
is a biconditional CHECK (``hunter_core.db.models.meme_features_15s``).

**The seed** plants ``flow_v2/1`` and ``hype_probe_v0/2``
(``ddl/meme_gate_v2_seed.py``). It retires **nothing**: ``meme_paper_v0/1``
and ``hype_probe_v0/1`` are retired by the audited ``infra/scripts/meme_rule_set.py
--deprecate``, with the verdict appended to EXP-M1/EXP-M3 — an operator's act
with a reason on record, not a side effect of a deploy.

**Upgrade guard: none, and that is an assertion** — a defaulted column, a
new table, a view recreated, ``ON CONFLICT DO NOTHING``. **The downgrade
refuses** while a bet is ``indeterminate`` (dropping the column would turn
it back into a −1 R the market never produced), while ``meme_features_15s``
holds a row (the series is evidence), or while a proposal or a bet references
the seeded sets.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_v2_seed import SEED_0030, SEEDED_IDS_SQL_0030, UNSEED_0030
from ddl.meme_gate_v2_view import SCOREBOARD_0030
from ddl.meme_lab_views import MEME_LAB_SCOREBOARD_VIEW
from ddl.meme_wallets import recreate_scoreboard_0027
from hunter_core.db.models import APP_ROLE, WORKER_ROLE, create_partition_sql

BET_COLUMNS_0030: tuple[str, ...] = (
    "outcome_quality",
    "outcome_quality_reason",
    "outcome_quality_at",
)
OUTCOME_QUALITIES_0030: tuple[str, ...] = ("measured", "indeterminate")

MEME_GATE_TABLES_0030: tuple[str, ...] = ("meme_features_15s",)
MEME_GATE_APP_READ_ONLY_TABLES: tuple[str, ...] = MEME_GATE_TABLES_0030
MEME_GATE_WORKER_APPEND_TABLES: tuple[str, ...] = MEME_GATE_TABLES_0030
MEME_PARTITIONED_TABLES_0030: tuple[str, ...] = MEME_GATE_TABLES_0030
MEME_INITIAL_MONTHS_0030: tuple[tuple[int, int], ...] = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
)
"""Hardcoded for ``0001``'s reason: a migration replayed at any future date
must produce the same schema. Later months are ``create_partitions.py``'s."""


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_ADD_BET_COLUMNS = (
    "ALTER TABLE meme_paper_bets "
    "ADD COLUMN outcome_quality text NOT NULL DEFAULT 'measured', "
    "ADD COLUMN outcome_quality_reason text, "
    "ADD COLUMN outcome_quality_at timestamptz"
)
_BET_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "ck_meme_paper_bets_outcome_quality_is_a_known_label",
        f"outcome_quality IN ({_labels(OUTCOME_QUALITIES_0030)})",
    ),
    (
        "ck_meme_paper_bets_an_indeterminate_bet_is_closed",
        "outcome_quality = 'measured' OR status = 'closed'",
    ),
    (
        "ck_meme_paper_bets_an_indeterminate_outcome_names_its_reason",
        "(outcome_quality = 'indeterminate') = (outcome_quality_reason IS NOT NULL) "
        "AND (outcome_quality = 'indeterminate') = (outcome_quality_at IS NOT NULL)",
    ),
)

_FEATURES_15S = """
CREATE TABLE meme_features_15s (
    as_of timestamptz NOT NULL,
    mint text NOT NULL,
    features_version text NOT NULL,
    snapshot_observed_at timestamptz,
    snapshot_source text,
    snapshots_120s smallint NOT NULL,
    age_s integer,
    mcap_sol numeric(28, 10),
    mcap_delta_60s numeric(28, 10),
    mcap_slope_60s numeric(12, 6),
    window_reason text,
    curve_progress_pct numeric(9, 6),
    progress_delta_60s numeric(9, 6),
    progress_rising boolean,
    progress_reason text,
    holders integer,
    holders_prev integer,
    holders_rising boolean,
    holders_reason text,
    buys_60s integer,
    sells_60s integer,
    unique_buyers_60s integer,
    net_sol_flow_60s numeric(28, 10),
    curve_volume_60s_sol numeric(28, 10),
    tape_reason text,
    creator_net_seller boolean,
    creator_net_seller_reason text,
    dev_share numeric(9, 6),
    dev_share_reason text,
    snipers integer,
    snipers_reason text,
    computed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_features_15s PRIMARY KEY (as_of, mint, features_version),
    CONSTRAINT ck_meme_features_15s_a_market_cap_names_its_photo
        CHECK ((mcap_sol IS NULL) = (snapshot_observed_at IS NULL)
               AND (mcap_sol IS NULL) = (snapshot_source IS NULL)),
    CONSTRAINT ck_meme_features_15s_window_is_null_with_a_reason
        CHECK ((mcap_delta_60s IS NULL) = (window_reason IS NOT NULL)
               AND (mcap_delta_60s IS NULL) = (mcap_slope_60s IS NULL)),
    CONSTRAINT ck_meme_features_15s_progress_delta_is_null_with_a_reason
        CHECK ((progress_delta_60s IS NULL) = (progress_reason IS NOT NULL)
               AND (progress_delta_60s IS NULL) = (progress_rising IS NULL)),
    CONSTRAINT ck_meme_features_15s_holders_trend_is_null_with_a_reason
        CHECK ((holders_rising IS NULL) = (holders_reason IS NOT NULL)
               AND (holders_rising IS NULL) = (holders_prev IS NULL)),
    CONSTRAINT ck_meme_features_15s_tape_is_null_with_a_reason
        CHECK ((buys_60s IS NULL) = (tape_reason IS NOT NULL)
               AND (buys_60s IS NULL) = (sells_60s IS NULL)
               AND (buys_60s IS NULL) = (unique_buyers_60s IS NULL)
               AND (buys_60s IS NULL) = (net_sol_flow_60s IS NULL)
               AND (buys_60s IS NULL) = (curve_volume_60s_sol IS NULL)),
    CONSTRAINT ck_meme_features_15s_creator_net_seller_is_null_with_a_reason
        CHECK ((creator_net_seller IS NULL) = (creator_net_seller_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_15s_dev_share_is_null_with_a_reason
        CHECK ((dev_share IS NULL) = (dev_share_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_15s_snipers_is_null_with_a_reason
        CHECK ((snipers IS NULL) = (snipers_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_15s_counts_are_not_negative
        CHECK (snapshots_120s >= 0 AND (age_s IS NULL OR age_s >= 0)
               AND (holders IS NULL OR holders >= 0)
               AND (holders_prev IS NULL OR holders_prev >= 0)
               AND (snipers IS NULL OR snipers >= 0)
               AND (buys_60s IS NULL OR buys_60s >= 0)
               AND (sells_60s IS NULL OR sells_60s >= 0)
               AND (unique_buyers_60s IS NULL OR unique_buyers_60s >= 0)
               AND (curve_volume_60s_sol IS NULL OR curve_volume_60s_sol >= 0)),
    CONSTRAINT ck_meme_features_15s_dev_share_is_a_fraction
        CHECK (dev_share IS NULL OR (dev_share >= 0 AND dev_share <= 1)),
    CONSTRAINT ck_meme_features_15s_provenance_is_not_empty
        CHECK (char_length(features_version) > 0 AND char_length(mint) > 0)
) PARTITION BY RANGE (as_of)
"""
_FEATURES_15S_INDEX = (
    "CREATE INDEX ix_meme_features_15s_mint_as_of ON meme_features_15s (mint, as_of)"
)


def add_outcome_quality() -> None:
    """The three columns and their three CHECKs; no backfill by design."""
    op.execute(_ADD_BET_COLUMNS)
    for name, predicate in _BET_CHECKS:
        op.execute(f"ALTER TABLE meme_paper_bets ADD CONSTRAINT {name} CHECK ({predicate})")


def drop_outcome_quality() -> None:
    for name, _predicate in reversed(_BET_CHECKS):
        op.execute(f"ALTER TABLE meme_paper_bets DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE meme_paper_bets "
        + ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in BET_COLUMNS_0030)
    )


def create_meme_features_15s() -> None:
    """The parent, its index, the initial months (hardened) and the grants."""
    op.execute(_FEATURES_15S)
    op.execute(_FEATURES_15S_INDEX)
    for table in MEME_PARTITIONED_TABLES_0030:
        for year, month in MEME_INITIAL_MONTHS_0030:
            op.execute(create_partition_sql(table, year, month))
            child = f"{table}_{year:04d}_{month:02d}"
            op.execute(f"REVOKE ALL ON {child} FROM {APP_ROLE}, {WORKER_ROLE}")
    for table in MEME_GATE_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_GATE_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def drop_meme_features_15s() -> None:
    """A parent takes its partitions with it."""
    for table in reversed(MEME_GATE_TABLES_0030):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def replace_scoreboard_with_outcome_quality() -> None:
    op.execute(f"DROP VIEW IF EXISTS {MEME_LAB_SCOREBOARD_VIEW}")
    op.execute(SCOREBOARD_0030)
    op.execute(f"GRANT SELECT ON {MEME_LAB_SCOREBOARD_VIEW} TO {APP_ROLE}, {WORKER_ROLE}")


def restore_scoreboard_0027() -> None:
    op.execute(f"DROP VIEW IF EXISTS {MEME_LAB_SCOREBOARD_VIEW}")
    recreate_scoreboard_0027()


def seed_gate_v2_rule_sets() -> None:
    """The two arms of EXP-M5. Idempotent on ``(name, version)``; retires nothing."""
    op.execute(SEED_0030)


def unseed_gate_v2_rule_sets() -> None:
    op.execute(UNSEED_0030)


_GUARDED: tuple[tuple[str, str, str], ...] = (
    (
        "meme_paper_bets",
        "WHERE outcome_quality = 'indeterminate'",
        "bets were reclassified indeterminate - dropping the column would turn them back into "
        "a -1 R the market never produced",
    ),
    (
        "meme_features_15s",
        "",
        "the 15-second series holds rows - the photos the flow gate judged are evidence",
    ),
    (
        "meme_proposals",
        f"WHERE rule_set_id IN {SEEDED_IDS_SQL_0030}",
        "proposals reference the seeded flow_v2/hype_probe_v0/2 sets - the seed cannot be "
        "removed under them",
    ),
    (
        "meme_paper_bets",
        f"WHERE rule_set_id IN {SEEDED_IDS_SQL_0030}",
        "bets reference the seeded flow_v2/hype_probe_v0/2 sets - the seed cannot be removed "
        "under them",
    ),
)


def refuse_a_downgrade_that_would_lose_an_outcome_or_the_series() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, predicate, why in _GUARDED:
        safe_why = why.replace("'", "''")
        # The predicate is quoted twice: bare in the COUNT, and inside the HINT's
        # string literal — where its own quotes (``= 'indeterminate'``) must double.
        safe_predicate = predicate.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
