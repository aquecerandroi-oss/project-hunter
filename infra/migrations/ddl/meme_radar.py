"""``0021_meme_radar`` — the pump.fun storage, frozen as of this revision.

Five tables, three of them monthly ``RANGE`` partitions, one view, two triggers
(``ddl/meme_radar_guards.py``) and grants by subtraction. **Global and RLS-free**
(DATABASE.md §1.1): an on-chain token belongs to the chain, not to an
organization — the shape ``markets``, ``market_regimes``, ``market_breadth`` and
``market_dispersion`` already have.

Every list here is **frozen as of ``0021``**, in the pattern of ``ddl/tables.py``,
``ddl/shadow.py``, ``ddl/breadth.py`` and ``ddl/dispersion.py``: a revision must
describe the schema as of that revision, so a table added to the models later must
not silently change what ``0021`` creates. ``test_migrations.py`` unions these
tuples with the earlier ones and proves the partition of the schema stays exact.

**The DDL is written out literally instead of assembled from the models.** Same
reason every module in this package states: a later edit to
``hunter_core.db.models.meme`` must not change what this revision put in the
database. ``alembic check`` is what keeps the two in step.

**Why three of the five are partitioned**, with the arithmetic written down
(§1.3's threshold is 1 M rows/year):

| table | ceiling | why |
|---|---|---|
| ``meme_curve_snapshots`` | 60 rows/min = ~31 M/year | the free REST budget *is* 60 req/60 s, so this is the physical ceiling of the poller |
| ``meme_features_1m`` | 120 mints × 1 440 min = ~63 M/year | one row per tracked mint per closed minute at the default cap |
| ``meme_trades`` | unbounded per transaction | no producer today (paid feed; the decoder is T4.2b), and §15.2 means partitioning later **rebuilds** the table — the cost this revision declines to defer |
| ``meme_tokens`` | ~40 k/day, pruned by row | the key is the mint, not an instant: it cannot be partitioned by month at all |
| ``meme_ingest_gaps`` | one row per hole | tens per day in the worst case |

This is a **deviation from the brief**, declared: the brief asked for two
partitioned tables (snapshots and trades) and left ``meme_features_1m``
unpartitioned. At 63 M rows/year it would be the largest unpartitioned table in
the schema by two orders of magnitude, and retention on it would have to be a
``DELETE`` of tens of millions of rows instead of a ``DROP`` — the exact
trade-off §1.3 makes for ``candles``.

Retention is **90 days, identical for graduated and non-graduated mints**
(``MEME_RETENTION_DAYS``, T4-MEME-RADAR.md §8 decision 2: Astra rejected keeping
only ``complete = true`` because selecting on success after the fact deletes the
controls). For the three partitioned tables it is executed by
``infra/scripts/prune_partitions.py`` dropping whole months, which is why neither
role has ``DELETE`` on them.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE, create_partition_sql

MEME_APP_READ_ONLY_TABLES: tuple[str, ...] = (
    "meme_curve_snapshots",
    "meme_features_1m",
    "meme_ingest_gaps",
    "meme_tokens",
    "meme_trades",
)
"""``SELECT`` for ``hunter_app`` on all five, and nothing else on any of them. The
radar is a screen; the API produces no observation (T4-MEME-RADAR.md §0: this
slice is read-only by construction, no order can be born from it)."""

MEME_WORKER_APPEND_TABLES: tuple[str, ...] = (
    "meme_curve_snapshots",
    "meme_features_1m",
    "meme_ingest_gaps",
    "meme_trades",
)
"""``SELECT``/``INSERT`` for ``hunter_worker`` — never ``UPDATE``, never
``DELETE``. A minute that was already folded is finished, and a hole that was
already accounted for stays accounted for: the ``replay_runs`` /
``market_breadth`` / ``market_dispersion`` shape (§25.4, §31). Immutability is a
**privilege**, not a trigger, because no legal ``UPDATE`` on these four exists.
Retention drops partitions as the table owner, so it needs no ``DELETE`` here."""

MEME_WORKER_UPSERT_TABLES: tuple[str, ...] = ("meme_tokens",)
"""``SELECT``/``INSERT``/``UPDATE``/``DELETE`` for ``hunter_worker``, and it is the
only table in this revision that gets more than append.

- ``UPDATE`` because a token's lifecycle genuinely moves after discovery
  (completion, migration, the Mayhem agent's state) — and what keeps that from
  becoming a rewrite of history is the trigger, not the grant:
  ``meme_tokens_identity_is_written_once`` refuses to change any already-known
  identity or stamp, **for every role including the owner**, which is a stronger
  lock than any ``REVOKE`` (the ``feature_baselines_immutable`` argument, §17.2).
- ``DELETE`` because this table is the one thing retention cannot prune by
  dropping a partition (its key is the mint), and ~40 k new mints/day is not a
  table anyone may keep forever. The precedent is
  ``ANALYSIS_WORKER_APPEND_TABLES`` (``feature_baselines``: ``SELECT``/
  ``INSERT``/``DELETE``, because baselines *are* pruned, §17.6) — and, as there,
  the deletion is gated by a declared marker
  (``SET LOCAL app.meme_retention = 'on'``, ``ddl/meme_radar_guards.py``) so that
  a bug in the collector cannot erase the discovery history its own numbers are
  counted against. Deleting is an act, not an accident."""

MEME_PARTITIONED_TABLES_0021: tuple[str, ...] = (
    "meme_curve_snapshots",
    "meme_features_1m",
    "meme_trades",
)
"""Monthly ``RANGE`` parents this revision adds to the six of ``0001``."""

MEME_INITIAL_MONTHS_0021: tuple[tuple[int, int], ...] = (
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
)
"""Hardcoded for ``0001``'s reason (``ddl/partitions.py``): a migration replayed
at any future date must produce the same schema, so its bounds may not depend on
the clock. Everything after December 2026 belongs to
``infra/scripts/create_partitions.py``, which keeps three months ahead and now
plans these three parents too, because it derives them from the models."""

MEME_RADAR_VIEW = "meme_radar_features_v1"
"""The API-facing read model, frozen in ``.claude/state/notes-T4.2.md`` §contrato
before this file existed so T4.3 could build in parallel."""

_TOKENS = """
CREATE TABLE meme_tokens (
    mint text NOT NULL,
    name text,
    symbol text,
    uri text,
    creator text,
    created_at timestamptz,
    bonding_curve text,
    initial_virtual_sol_reserves numeric(28, 10),
    initial_virtual_token_reserves numeric(28, 10),
    initial_real_token_reserves numeric(28, 10),
    total_supply numeric(28, 10),
    pool text,
    mayhem_enabled boolean,
    mayhem_mode text,
    mayhem_state text,
    completed_at timestamptz,
    migrated_at timestamptz,
    migrated_pool text,
    first_seen_source text NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_tokens PRIMARY KEY (mint),
    CONSTRAINT ck_meme_tokens_mayhem_state_is_a_known_label
        CHECK (mayhem_state IS NULL
               OR mayhem_state IN ('active', 'paused', 'completed', 'unknown')),
    CONSTRAINT ck_meme_tokens_mayhem_mode_is_a_known_label
        CHECK (mayhem_mode IS NULL OR mayhem_mode IN ('auto', 'manual', 'unknown')),
    CONSTRAINT ck_meme_tokens_a_disabled_token_has_no_agent_state
        CHECK (NOT (mayhem_enabled IS FALSE AND mayhem_state IS NOT NULL)),
    CONSTRAINT ck_meme_tokens_a_migration_names_its_destination
        CHECK (migrated_at IS NULL OR migrated_pool IS NOT NULL),
    CONSTRAINT ck_meme_tokens_an_observed_identity_is_not_empty
        CHECK ((name IS NULL OR char_length(name) > 0)
               AND (symbol IS NULL OR char_length(symbol) > 0)
               AND (creator IS NULL OR char_length(creator) > 0)
               AND (uri IS NULL OR char_length(uri) > 0)
               AND (pool IS NULL OR char_length(pool) > 0)),
    CONSTRAINT ck_meme_tokens_provenance_is_not_empty
        CHECK (char_length(first_seen_source) > 0 AND char_length(mint) > 0)
)
"""

_CURVE_SNAPSHOTS = """
CREATE TABLE meme_curve_snapshots (
    observed_at timestamptz NOT NULL,
    mint text NOT NULL,
    source text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    virtual_sol_reserves numeric(28, 10) NOT NULL,
    virtual_token_reserves numeric(28, 10) NOT NULL,
    real_sol_reserves numeric(28, 10) NOT NULL,
    real_token_reserves numeric(28, 10) NOT NULL,
    total_supply numeric(28, 10) NOT NULL,
    complete boolean NOT NULL,
    mcap_sol numeric(28, 10) GENERATED ALWAYS AS
        ((virtual_sol_reserves / NULLIF(virtual_token_reserves, 0)) * total_supply) STORED,
    slot bigint,
    commitment text,
    mayhem_enabled boolean,
    mayhem_state text,
    mayhem_mode text,
    CONSTRAINT pk_meme_curve_snapshots PRIMARY KEY (observed_at, mint, source),
    CONSTRAINT ck_meme_curve_snapshots_provenance_is_not_empty
        CHECK (char_length(mint) > 0 AND char_length(source) > 0),
    CONSTRAINT ck_meme_curve_snapshots_slot_is_not_negative CHECK (slot IS NULL OR slot >= 0)
) PARTITION BY RANGE (observed_at)
"""

_TRADES = """
CREATE TABLE meme_trades (
    block_time timestamptz NOT NULL,
    signature text NOT NULL,
    event_index smallint NOT NULL,
    mint text NOT NULL,
    slot bigint NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    outer_ix_index smallint,
    inner_ix_index smallint,
    trader text NOT NULL,
    side text NOT NULL,
    sol_lamports bigint NOT NULL,
    token_amount numeric(28, 10) NOT NULL,
    price numeric(28, 10) NOT NULL,
    quote_mint text NOT NULL,
    token_decimals smallint NOT NULL,
    commitment text NOT NULL,
    is_mayhem_agent boolean,
    source text NOT NULL,
    CONSTRAINT pk_meme_trades PRIMARY KEY (block_time, signature, event_index),
    CONSTRAINT ck_meme_trades_side_is_a_known_label CHECK (side IN ('buy', 'sell')),
    CONSTRAINT ck_meme_trades_commitment_is_a_known_label
        CHECK (commitment IN ('confirmed', 'finalized')),
    CONSTRAINT ck_meme_trades_event_index_is_not_negative CHECK (event_index >= 0),
    CONSTRAINT ck_meme_trades_instruction_indexes_are_not_negative
        CHECK ((outer_ix_index IS NULL OR outer_ix_index >= 0)
               AND (inner_ix_index IS NULL OR inner_ix_index >= 0)),
    CONSTRAINT ck_meme_trades_chain_counters_are_not_negative
        CHECK (slot >= 0 AND sol_lamports >= 0)
) PARTITION BY RANGE (block_time)
"""

_FEATURES = """
CREATE TABLE meme_features_1m (
    end_time timestamptz NOT NULL,
    mint text NOT NULL,
    features_version text NOT NULL,
    curve_progress_pct numeric(9, 6),
    progress_reason text,
    mcap_sol numeric(28, 10),
    curve_reason text,
    unique_buyers integer,
    unique_buyers_reason text,
    buy_sell_ratio numeric(18, 8),
    buy_sell_ratio_reason text,
    top10_share numeric(9, 6),
    top10_share_reason text,
    creator_sold boolean,
    creator_sold_reason text,
    age_minutes integer,
    coverage numeric(9, 6) NOT NULL,
    snapshot_observed_at timestamptz,
    snapshot_source text,
    computed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_features_1m PRIMARY KEY (end_time, mint, features_version),
    CONSTRAINT ck_meme_features_1m_mcap_is_null_with_a_reason
        CHECK ((mcap_sol IS NULL) = (curve_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_1m_progress_is_null_with_a_reason
        CHECK ((curve_progress_pct IS NULL) = (progress_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_1m_unique_buyers_is_null_with_a_reason
        CHECK ((unique_buyers IS NULL) = (unique_buyers_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_1m_buy_sell_ratio_is_null_with_a_reason
        CHECK ((buy_sell_ratio IS NULL) = (buy_sell_ratio_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_1m_top10_share_is_null_with_a_reason
        CHECK ((top10_share IS NULL) = (top10_share_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_1m_creator_sold_is_null_with_a_reason
        CHECK ((creator_sold IS NULL) = (creator_sold_reason IS NOT NULL)),
    CONSTRAINT ck_meme_features_1m_coverage_is_a_fraction
        CHECK (coverage >= 0 AND coverage <= 1),
    CONSTRAINT ck_meme_features_1m_age_is_not_negative
        CHECK (age_minutes IS NULL OR age_minutes >= 0),
    CONSTRAINT ck_meme_features_1m_buyers_are_not_negative
        CHECK (unique_buyers IS NULL OR unique_buyers >= 0),
    CONSTRAINT ck_meme_features_1m_ratio_is_not_negative
        CHECK (buy_sell_ratio IS NULL OR buy_sell_ratio >= 0),
    CONSTRAINT ck_meme_features_1m_top10_share_is_a_fraction
        CHECK (top10_share IS NULL OR (top10_share >= 0 AND top10_share <= 1)),
    CONSTRAINT ck_meme_features_1m_provenance_is_not_empty
        CHECK (char_length(features_version) > 0 AND char_length(mint) > 0)
) PARTITION BY RANGE (end_time)
"""

_GAPS = """
CREATE TABLE meme_ingest_gaps (
    id uuid NOT NULL,
    stream text NOT NULL,
    mint text,
    gap_start timestamptz NOT NULL,
    gap_end timestamptz NOT NULL,
    detected_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL,
    generation integer,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT pk_meme_ingest_gaps PRIMARY KEY (id),
    CONSTRAINT ck_meme_ingest_gaps_a_gap_is_a_window CHECK (gap_end > gap_start),
    CONSTRAINT ck_meme_ingest_gaps_a_gap_names_its_stream_and_reason
        CHECK (char_length(stream) > 0 AND char_length(reason) > 0),
    CONSTRAINT ck_meme_ingest_gaps_a_scoped_gap_names_a_mint
        CHECK (mint IS NULL OR char_length(mint) > 0),
    CONSTRAINT ck_meme_ingest_gaps_generation_is_not_negative
        CHECK (generation IS NULL OR generation >= 0)
)
"""

_INDEXES = (
    "CREATE INDEX ix_meme_tokens_created_at ON meme_tokens (created_at)",
    "CREATE INDEX ix_meme_tokens_first_seen_at ON meme_tokens (first_seen_at)",
    "CREATE INDEX ix_meme_curve_snapshots_mint_observed "
    "ON meme_curve_snapshots (mint, observed_at)",
    "CREATE INDEX ix_meme_trades_mint_block_time ON meme_trades (mint, block_time)",
    "CREATE INDEX ix_meme_features_1m_mint_end_time ON meme_features_1m (mint, end_time)",
    "CREATE INDEX ix_meme_ingest_gaps_stream_gap_start ON meme_ingest_gaps (stream, gap_start)",
)
"""Six, each with a read behind it. An index on a partitioned parent is created
on every partition, present and future, by Postgres itself — which is why the
monthly children need no index statement of their own."""

_VIEW = f"""
CREATE VIEW {MEME_RADAR_VIEW} AS
SELECT f.mint, f.end_time, f.features_version, f.curve_progress_pct, f.progress_reason,
       f.mcap_sol, f.curve_reason, f.unique_buyers, f.unique_buyers_reason, f.buy_sell_ratio,
       f.buy_sell_ratio_reason, f.top10_share, f.top10_share_reason, f.creator_sold,
       f.creator_sold_reason, f.age_minutes, f.coverage, f.snapshot_observed_at,
       f.snapshot_source, t.name, t.symbol, t.creator, t.created_at AS token_created_at,
       t.pool, t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at,
       t.migrated_at, t.migrated_pool, t.first_seen_source, t.last_seen_at
FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
"""  # noqa: S608 - the only interpolation is this module's own frozen constant
"""The read model, and deliberately **not** a projection that filters or orders:
the caller paginates, and its predicates descend to the month's partition
(``end_time``) or to the primary key (``mint``). A view that embedded
``max(end_time)`` would be a scan on every request — so "the last closed minute"
is a parameter of the API, not magic inside the view."""

_TABLES_IN_CREATION_ORDER = (_TOKENS, _CURVE_SNAPSHOTS, _TRADES, _FEATURES, _GAPS)


def create_meme_tables() -> None:
    """The five tables, their six indexes and the read model's view."""
    for statement in _TABLES_IN_CREATION_ORDER:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_VIEW)


def create_meme_partitions() -> None:
    """``MEME_INITIAL_MONTHS_0021`` under each partitioned parent, then harden.

    Hardening is a ``REVOKE ALL`` on the child and nothing more: these parents are
    global, so there is no policy to install (``harden_partition_sql``'s tenant
    half). Access goes through the parent, because Postgres checks a query that
    names a child against the child's own privileges (§1.3, §15.6).
    """
    for table in MEME_PARTITIONED_TABLES_0021:
        for year, month in MEME_INITIAL_MONTHS_0021:
            op.execute(create_partition_sql(table, year, month))
            child = f"{table}_{year:04d}_{month:02d}"
            op.execute(f"REVOKE ALL ON {child} FROM {APP_ROLE}, {WORKER_ROLE}")


def grant_meme_privileges() -> None:
    """Read for the API, append for the worker, upsert on the dimension only."""
    for table in MEME_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")
    for table in MEME_WORKER_UPSERT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON {MEME_RADAR_VIEW} TO {APP_ROLE}, {WORKER_ROLE}")


def drop_meme_tables() -> None:
    """The view first, then the parents — a parent takes its partitions with it."""
    op.execute(f"DROP VIEW IF EXISTS {MEME_RADAR_VIEW}")
    for table in reversed(
        (
            "meme_tokens",
            "meme_curve_snapshots",
            "meme_trades",
            "meme_features_1m",
            "meme_ingest_gaps",
        )
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
