"""``0032_meme_activity`` — the tape by batch (T4.2g): ``POST
/v1/coins/market-activity/batch`` in place of the per-mint tape Cloudflare
caps at ~20 requests per 60 s per IP.

**The fact that motivated it** (T4.2f, measured): the per-mint tape covers
~40 % of the gate's rows a minute from one IP, and the flow gate
(``flow_v2/1``, EXP-M5) refused ~100 of ~110 young coins a tick as
``buyers_unknown``/``sells_ratio_unknown``/``flow_not_polled``. The batch
route counts 50 coins per request (its validator's ceiling, measured on
12/09 20:24 UTC): three requests a minute cover the whole tracked set inside
the same budget, and the per-mint tape keeps the rest for the open bets and
the ``graduating`` board.

**``meme_market_activity_1m``** — one row per coin per window per minute
(monthly ``RANGE`` on ``end_time``, ``MEME_INITIAL_MONTHS_0032``, retention
30 days in ``partition_retention.py``): the counts and USD volumes as the
route said them, the SOL volumes derived with the quote that derived them
beside them (``NULL`` together without a quote), ``empty = true`` for a
window the route answered ``null`` for when the same cycle filled that window
for another coin. Read-only for ``hunter_app``, append-only for
``hunter_worker``, children hardened like ``0021``'s
(``hunter_core.db.models.meme_activity``).

**Three columns on both feature series** (``meme_features_1m``,
``meme_features_15s``): ``tape_source`` (``swap_api_trades`` |
``activity_1m``), ``tape_window_s``, ``tape_as_of`` — where the tape numbers
of the row came from and the instant its window ended, ``NULL`` together and
``NULL`` on every row folded before this revision (the ``line_points IS
NULL`` argument of ``0026``: an old row claims no provenance it did not have).
One CHECK per series says all of it: a source names its window and instant,
is a known label, and implies a tape (``buys_1m``/``buys_60s`` not null); the
converse is not enforced, so old rows stay legal.

**Upgrade guard: none, and that is an assertion** — a new table, nullable
columns, no backfill. **The downgrade refuses** while the activity table holds
a row or a feature row was folded from the batch (``tape_source =
'activity_1m'``): dropping the label would leave those numbers looking like
the per-mint tape, whose buyers exclude the creator and whose creator columns
are real — evidence of what the gate judged (§17.7).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE, create_partition_sql

MEME_ACTIVITY_TABLES_0032: tuple[str, ...] = ("meme_market_activity_1m",)
MEME_ACTIVITY_APP_READ_ONLY_TABLES: tuple[str, ...] = MEME_ACTIVITY_TABLES_0032
MEME_ACTIVITY_WORKER_APPEND_TABLES: tuple[str, ...] = MEME_ACTIVITY_TABLES_0032
MEME_PARTITIONED_TABLES_0032: tuple[str, ...] = MEME_ACTIVITY_TABLES_0032
MEME_INITIAL_MONTHS_0032: tuple[tuple[int, int], ...] = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
)
"""Hardcoded for ``0001``'s reason: a migration replayed at any future date
must produce the same schema. Later months are ``create_partitions.py``'s."""

TAPE_SOURCE_COLUMNS_0032: tuple[str, ...] = ("tape_source", "tape_window_s", "tape_as_of")
TAPE_SOURCES_0032: tuple[str, ...] = ("swap_api_trades", "activity_1m")
FEATURE_SERIES_0032: tuple[tuple[str, str], ...] = (
    ("meme_features_1m", "buys_1m"),
    ("meme_features_15s", "buys_60s"),
)
"""The two series that gain the columns, and the tape count a source implies."""

_ACTIVITY = """
CREATE TABLE meme_market_activity_1m (
    end_time timestamptz NOT NULL,
    mint text NOT NULL,
    window_name text NOT NULL,
    window_s integer NOT NULL,
    received_at timestamptz NOT NULL,
    source text NOT NULL DEFAULT 'swap_api:market-activity/batch',
    empty boolean NOT NULL DEFAULT false,
    num_txs integer NOT NULL,
    buys integer NOT NULL,
    sells integer NOT NULL,
    unique_users integer NOT NULL,
    unique_buyers integer NOT NULL,
    unique_sellers integer NOT NULL,
    volume_usd numeric(28, 10) NOT NULL,
    buy_volume_usd numeric(28, 10) NOT NULL,
    sell_volume_usd numeric(28, 10) NOT NULL,
    price_change_pct numeric(28, 10),
    sol_usd numeric(28, 10),
    sol_usd_observed_at timestamptz,
    buy_volume_sol numeric(28, 10),
    sell_volume_sol numeric(28, 10),
    CONSTRAINT pk_meme_market_activity_1m PRIMARY KEY (end_time, mint, window_name),
    CONSTRAINT ck_meme_market_activity_1m_window_is_a_known_label
        CHECK (window_name IN ('1m', '5m', '1h', '6h', '24h')),
    CONSTRAINT ck_meme_market_activity_1m_window_has_a_length CHECK (window_s > 0),
    CONSTRAINT ck_meme_market_activity_1m_counts_are_not_negative
        CHECK (num_txs >= 0 AND buys >= 0 AND sells >= 0 AND unique_users >= 0
               AND unique_buyers >= 0 AND unique_sellers >= 0),
    CONSTRAINT ck_meme_market_activity_1m_volumes_are_not_negative
        CHECK (volume_usd >= 0 AND buy_volume_usd >= 0 AND sell_volume_usd >= 0),
    CONSTRAINT ck_meme_market_activity_1m_sol_figures_name_their_quote
        CHECK ((sol_usd IS NULL) = (sol_usd_observed_at IS NULL)
               AND (sol_usd IS NULL) = (buy_volume_sol IS NULL)
               AND (sol_usd IS NULL) = (sell_volume_sol IS NULL)),
    CONSTRAINT ck_meme_market_activity_1m_quote_is_positive CHECK (sol_usd IS NULL OR sol_usd > 0),
    CONSTRAINT ck_meme_market_activity_1m_an_empty_window_is_all_zeros
        CHECK (NOT empty OR (num_txs = 0 AND buys = 0 AND sells = 0 AND volume_usd = 0)),
    CONSTRAINT ck_meme_market_activity_1m_provenance_is_not_empty
        CHECK (char_length(mint) > 0 AND char_length(source) > 0)
) PARTITION BY RANGE (end_time)
"""
_ACTIVITY_INDEX = (
    "CREATE INDEX ix_meme_market_activity_1m_mint_end_time "
    "ON meme_market_activity_1m (mint, end_time)"
)


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def create_meme_market_activity() -> None:
    """The parent, its index, the initial months (hardened) and the grants."""
    op.execute(_ACTIVITY)
    op.execute(_ACTIVITY_INDEX)
    for table in MEME_PARTITIONED_TABLES_0032:
        for year, month in MEME_INITIAL_MONTHS_0032:
            op.execute(create_partition_sql(table, year, month))
            child = f"{table}_{year:04d}_{month:02d}"
            op.execute(f"REVOKE ALL ON {child} FROM {APP_ROLE}, {WORKER_ROLE}")
    for table in MEME_ACTIVITY_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_ACTIVITY_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def drop_meme_market_activity() -> None:
    """A parent takes its partitions with it."""
    for table in reversed(MEME_ACTIVITY_TABLES_0032):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def _checks(table: str, count_column: str) -> tuple[tuple[str, str], ...]:
    """One CHECK per series: a source names its window and instant, is a known
    label, and implies a tape (``hunter_core.db.models.meme_features``). The
    name stays under Postgres's 63-character identifier limit on purpose:
    a truncated name is a name ``alembic check`` cannot match."""
    return (
        (
            f"ck_{table}_tape_source_is_consistent",
            "(tape_source IS NULL) = (tape_window_s IS NULL) "
            "AND (tape_source IS NULL) = (tape_as_of IS NULL) "
            f"AND (tape_source IS NULL OR tape_source IN ({_labels(TAPE_SOURCES_0032)})) "
            f"AND (tape_source IS NULL OR {count_column} IS NOT NULL)",
        ),
    )


def add_tape_source_columns() -> None:
    """Three nullable columns on each series and their CHECKs; no backfill."""
    for table, count_column in FEATURE_SERIES_0032:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN tape_source text, "
            "ADD COLUMN tape_window_s integer, ADD COLUMN tape_as_of timestamptz"
        )
        for name, predicate in _checks(table, count_column):
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({predicate})")


def drop_tape_source_columns() -> None:
    for table, count_column in reversed(FEATURE_SERIES_0032):
        for name, _predicate in reversed(_checks(table, count_column)):
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(
            f"ALTER TABLE {table} "
            + ", ".join(f"DROP COLUMN IF EXISTS {column}" for column in TAPE_SOURCE_COLUMNS_0032)
        )


_GUARDED: tuple[tuple[str, str, str], ...] = (
    (
        "meme_market_activity_1m",
        "",
        "the batch route's counts are the source behind the minute's tape columns",
    ),
    (
        "meme_features_1m",
        "WHERE tape_source = 'activity_1m'",
        "minutes folded from the batch route would lose the label that says their "
        "buyers count the creator and their creator columns are unknown",
    ),
    (
        "meme_features_15s",
        "WHERE tape_source = 'activity_1m'",
        "instants folded from the batch route would lose the label that says their "
        "buyers count the creator and their creator columns are unknown",
    ),
)


def refuse_a_downgrade_that_would_lose_the_activity() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, predicate, why in _GUARDED:
        safe_why = why.replace("'", "''")
        safe_predicate = predicate.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
