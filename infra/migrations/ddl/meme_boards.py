"""``0023_meme_boards_trades`` — the site's boards and the rug-risk reads, frozen.

Two new tables, both **global and RLS-free** (DATABASE.md §1.1) and both monthly
``RANGE`` parents (§1.3, the arithmetic written down):

| table | ceiling | why |
|---|---|---|
| ``meme_board_observations`` | 4 boards × ~50 rows × 1 440 min ≈ 100 M/year | one row per mint per board per **closed minute** (the last version seen in the minute, the patch count, the exposure interval) |
| ``meme_risk_snapshots`` | ≤ 1 read/mint/5 min over open bets + ``graduating`` ≈ 5 M/year | the 65-field ``/in-memory-coin`` object, raw, next to the few columns whose names state their meaning |

Both are pruned by dropping months (``infra/scripts/prune_partitions.py``,
``MEME_RETENTION_DAYS``), which is why neither role has ``DELETE``; grants are
``SELECT`` for ``hunter_app`` and ``SELECT``/``INSERT`` for ``hunter_worker`` —
the ``meme_curve_snapshots`` shape of ``0021``. Every list is **frozen as of
``0023``** and unioned by ``test_migrations.py``/``test_schema_privileges.py``.

The DDL is written out literally, never assembled from the models
(``ddl/meme_radar.py``'s rule); ``hunter_core.db.models.meme_boards`` mirrors
it and ``alembic check`` keeps the two in step. The columns ``0023`` adds to
``meme_features_1m`` and the one it relaxes on ``meme_trades`` live in
``ddl/meme_boards_guards.py`` with the downgrade guard (the 350-line cut).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE, create_partition_sql

MEME_BOARDS_APP_READ_ONLY_TABLES: tuple[str, ...] = (
    "meme_board_observations",
    "meme_risk_snapshots",
)
"""``SELECT`` for ``hunter_app`` and nothing else: the API renders exposure and
risk, it observes neither."""

MEME_BOARDS_WORKER_APPEND_TABLES: tuple[str, ...] = (
    "meme_board_observations",
    "meme_risk_snapshots",
)
"""``SELECT``/``INSERT`` for ``hunter_worker`` — never ``UPDATE``, never
``DELETE``: a closed minute of a board and a risk read are observations, and an
observation its writer may rewrite is not evidence (§25.4)."""

MEME_PARTITIONED_TABLES_0023: tuple[str, ...] = MEME_BOARDS_APP_READ_ONLY_TABLES
MEME_TABLES_0023: tuple[str, ...] = MEME_BOARDS_APP_READ_ONLY_TABLES

MEME_INITIAL_MONTHS_0023: tuple[tuple[int, int], ...] = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
)
"""The same four months ``0021`` planted, for the same reason: a migration
replayed on any future date must produce the same schema."""

_BOARD_OBSERVATIONS = """
CREATE TABLE meme_board_observations (
    observed_at timestamptz NOT NULL,
    board text NOT NULL,
    mint text NOT NULL,
    minute_end timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    mint_updated_at timestamptz,
    version bigint NOT NULL,
    position integer NOT NULL,
    patches integer NOT NULL DEFAULT 0,
    chain text,
    program text,
    platform text,
    quote_asset text,
    name text,
    symbol text,
    market_cap_usd numeric(28, 10),
    progress_pct numeric(9, 6),
    volume_sol numeric(28, 10),
    volume_usd numeric(28, 10),
    volume_5m_sol numeric(28, 10),
    volume_15m_sol numeric(28, 10),
    volume_1h_sol numeric(28, 10),
    volume_24h_sol numeric(28, 10),
    volume_5m_usd numeric(28, 10),
    volume_15m_usd numeric(28, 10),
    volume_1h_usd numeric(28, 10),
    volume_24h_usd numeric(28, 10),
    tx_5m integer,
    age_s integer,
    kol_count integer,
    snipers integer,
    is_mayhem boolean,
    mayhem_state text,
    has_social boolean,
    has_twitter boolean,
    has_website boolean,
    has_telegram boolean,
    graduated_at timestamptz,
    ath_market_cap_usd numeric(28, 10),
    buys integer,
    sells integer,
    txs integer,
    holders integer,
    top10_share numeric(9, 6),
    dev_share numeric(9, 6),
    cashback boolean,
    dev_wallet text,
    is_live boolean,
    participants integer,
    fees_sol numeric(28, 10),
    fees_usd numeric(28, 10),
    first_seen_in_board_at timestamptz NOT NULL,
    last_seen_in_board_at timestamptz NOT NULL,
    left_board_at timestamptz,
    exposure_censored boolean NOT NULL DEFAULT false,
    extra jsonb NOT NULL DEFAULT '{}'::jsonb,
    source text NOT NULL,
    CONSTRAINT pk_meme_board_observations PRIMARY KEY (observed_at, board, mint),
    CONSTRAINT ck_meme_board_observations_board_is_a_known_label
        CHECK (board IN ('new', 'graduating', 'graduated', 'movers')),
    CONSTRAINT ck_meme_board_observations_provenance_is_not_empty
        CHECK (char_length(mint) > 0 AND char_length(source) > 0),
    CONSTRAINT ck_meme_board_observations_position_is_not_negative CHECK (position >= 0),
    CONSTRAINT ck_meme_board_observations_patches_are_not_negative CHECK (patches >= 0),
    CONSTRAINT ck_meme_board_observations_exposure_is_an_interval
        CHECK (last_seen_in_board_at >= first_seen_in_board_at),
    CONSTRAINT ck_meme_board_observations_a_censored_exposure_has_no_exit
        CHECK (NOT (exposure_censored AND left_board_at IS NOT NULL))
) PARTITION BY RANGE (observed_at)
"""

_RISK_SNAPSHOTS = """
CREATE TABLE meme_risk_snapshots (
    observed_at timestamptz NOT NULL,
    mint text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL,
    program text,
    platform text,
    quote_mint text,
    quote_asset text,
    holders integer,
    top10_share numeric(9, 6),
    dev_share numeric(9, 6),
    snipers integer,
    sniper_share numeric(9, 6),
    bundled_share numeric(9, 6),
    progress_pct numeric(9, 6),
    graduated_at timestamptz,
    is_mayhem boolean,
    mayhem_state text,
    raw jsonb NOT NULL,
    CONSTRAINT pk_meme_risk_snapshots PRIMARY KEY (observed_at, mint),
    CONSTRAINT ck_meme_risk_snapshots_provenance_is_not_empty
        CHECK (char_length(mint) > 0 AND char_length(source) > 0),
    CONSTRAINT ck_meme_risk_snapshots_counts_are_not_negative
        CHECK ((holders IS NULL OR holders >= 0) AND (snipers IS NULL OR snipers >= 0))
) PARTITION BY RANGE (observed_at)
"""

_INDEXES = (
    "CREATE INDEX ix_meme_board_observations_mint_observed "
    "ON meme_board_observations (mint, observed_at)",
    "CREATE INDEX ix_meme_board_observations_minute_end_board "
    "ON meme_board_observations (minute_end, board)",
    "CREATE INDEX ix_meme_risk_snapshots_mint_observed ON meme_risk_snapshots (mint, observed_at)",
)
"""Three, each with a read behind it: a mint's exposure history, the board of a
closed minute (the features fold and the radar's "what was on the board when"),
and a mint's risk series. The PK prefix serves "the board at an instant"."""


def create_meme_boards_tables() -> None:
    for statement in (_BOARD_OBSERVATIONS, _RISK_SNAPSHOTS):
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)


def create_meme_boards_partitions() -> None:
    """``MEME_INITIAL_MONTHS_0023`` under both parents, hardened like ``0021``'s."""
    for table in MEME_PARTITIONED_TABLES_0023:
        for year, month in MEME_INITIAL_MONTHS_0023:
            op.execute(create_partition_sql(table, year, month))
            child = f"{table}_{year:04d}_{month:02d}"
            op.execute(f"REVOKE ALL ON {child} FROM {APP_ROLE}, {WORKER_ROLE}")


def grant_meme_boards_privileges() -> None:
    for table in MEME_BOARDS_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_BOARDS_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def drop_meme_boards_tables() -> None:
    """A parent takes its partitions with it."""
    for table in reversed(MEME_TABLES_0023):
        op.execute(f"DROP TABLE IF EXISTS {table}")
