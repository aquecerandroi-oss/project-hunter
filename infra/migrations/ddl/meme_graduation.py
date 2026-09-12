"""``0024_meme_graduation`` — what "graduated" means, frozen in the schema.

The plantão's run 5 (12/09/2026 05:51 BRT) measured that the REST ``complete =
true`` is not a graduation: of 140 "complete" coins, 77 carried
``real_sol_reserves = 0`` and 72 were absent from the site's ``graduated``
board — and a migrated curve's SOL has left for the pool, so a zero reserve is
seen on real graduations too. Astra's must-fixes: keep the indicators separate;
a zero reserve classifies nothing. ``meme_tokens`` therefore gains **four
separate completion stamps**, written once each —

| column | the first photo that… | writer |
|---|---|---|
| ``rest_complete_seen_at`` | said ``complete = true`` (REST/RPC) | ``curve_rows.py`` |
| ``curve_filled_seen_at`` | held ≥ the fill threshold derived from ``/global-params`` | ``curve_rows.py`` |
| ``graduated_board_seen_at`` | listed the mint on the ``graduated`` board | ``boards.py`` |
| ``pool_created_at`` + ``pool_created_source`` | reported a pool (``gd`` or ``migrate``), and who | ``boards.py``, ``risk.py``, ``discovery.py`` |

— and ``completed_at`` **stops being an observation and becomes a reduction**:
the earliest of the four, minus a REST ``complete`` whose photo carried no SOL
(``services/meme-worker/hunter_meme_worker/graduation.py``). It leaves the
write-once list and gains a rule of its own in the trigger: it may only move
*earlier* (the indexer's ``gd`` is retrospective), never later, never to NULL.

**The denominator gains its provenance**: ``progress_denominator_source`` is
``observed_virgin`` (the ``0021`` rule) or ``global_params`` (T4.2d: a standard
curve seen mid-life takes the record in force at its creation), biconditional
with ``initial_real_token_reserves``; unknown is ``NULL`` on both.

**The backfill is from evidence, never from a guess**: ``rest_complete_seen_at``
from the snapshots that said ``complete``; ``graduated_board_seen_at`` from the
board minutes; ``pool_created_at`` from the ``migrate`` frames this radar held
as ``migrated_at`` (first: the discovery socket is what heard them) else from
the earliest ``gd`` of any board row, with that row's source;
``progress_denominator_source = observed_virgin`` for every denominator held
today (the virgin photo was its only writer); ``completed_at`` recomputed by
the reducer's rule. ``curve_filled_seen_at`` is **not** backfilled: the threshold
needs the record, which a migration does not read — the series starts at the
deploy, and the matrix says so by counting.

**Two views**: ``meme_radar_features_v1`` is replaced with the six columns
appended (``CREATE OR REPLACE``, grants kept), and ``meme_graduation_matrix_v1``
turns the M-D1/M-D2 diagnostic into a panel: per Brasília day of the earliest
signal, how many mints carry 1/2/3/4 signals, which pairs disagree, how many
are ``completed`` and how many are REST-only-and-unclassified (the 77).
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_RADAR_VIEW = "meme_radar_features_v1"
MEME_GRADUATION_VIEW = "meme_graduation_matrix_v1"

GRADUATION_COLUMNS_0024: tuple[str, ...] = (
    "rest_complete_seen_at",
    "curve_filled_seen_at",
    "graduated_board_seen_at",
    "pool_created_at",
    "pool_created_source",
    "progress_denominator_source",
)
"""The six columns this revision adds to ``meme_tokens``, frozen."""

POOL_SOURCES_0024: tuple[str, ...] = (
    "pumpportal_ws",
    "trenches_ws",
    "indexer_rest:/boards",
    "indexer_rest:/in-memory-coin",
)
DENOMINATOR_SOURCES_0024: tuple[str, ...] = ("observed_virgin", "global_params")

WRITE_ONCE_COLUMNS_0024: tuple[str, ...] = (
    "mint",
    "name",
    "symbol",
    "uri",
    "creator",
    "created_at",
    "bonding_curve",
    "initial_virtual_sol_reserves",
    "initial_virtual_token_reserves",
    "initial_real_token_reserves",
    "progress_denominator_source",
    "total_supply",
    "pool",
    "mayhem_enabled",
    "rest_complete_seen_at",
    "curve_filled_seen_at",
    "graduated_board_seen_at",
    "pool_created_at",
    "pool_created_source",
    "migrated_at",
    "migrated_pool",
    "first_seen_source",
    "first_seen_at",
)
"""``0021``'s list minus ``completed_at`` (now reduced, with its own branch below)
plus the six of this revision. ``NULL -> value`` once; never a rewrite."""

_TRIGGER = "meme_tokens_identity_is_written_once"
_MUTABLE_NOTE = "mayhem_mode, mayhem_state, last_seen_at, updated_at"

_ADD_COLUMNS = tuple(
    f"ALTER TABLE meme_tokens ADD COLUMN {column} {kind}"
    for column, kind in (
        ("rest_complete_seen_at", "timestamptz"),
        ("curve_filled_seen_at", "timestamptz"),
        ("graduated_board_seen_at", "timestamptz"),
        ("pool_created_at", "timestamptz"),
        ("pool_created_source", "text"),
        ("progress_denominator_source", "text"),
    )
)


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_CHECKS = (
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_pool_names_its_source "
    "CHECK ((pool_created_at IS NULL) = (pool_created_source IS NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_pool_source_is_a_known_label "
    f"CHECK (pool_created_source IS NULL OR pool_created_source IN ({_labels(POOL_SOURCES_0024)}))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_a_denominator_names_its_source "
    "CHECK ((initial_real_token_reserves IS NULL) = (progress_denominator_source IS NULL))",
    "ALTER TABLE meme_tokens ADD CONSTRAINT ck_meme_tokens_denominator_source_is_a_known_label "
    "CHECK (progress_denominator_source IS NULL OR progress_denominator_source IN "
    f"({_labels(DENOMINATOR_SOURCES_0024)}))",
)
_CHECK_NAMES = (
    "ck_meme_tokens_a_pool_names_its_source",
    "ck_meme_tokens_pool_source_is_a_known_label",
    "ck_meme_tokens_a_denominator_names_its_source",
    "ck_meme_tokens_denominator_source_is_a_known_label",
)

_BACKFILL = (
    # The photo that said complete — the only writer of completed_at until now.
    "UPDATE meme_tokens t SET rest_complete_seen_at = s.first_complete "
    "FROM (SELECT mint, min(observed_at) AS first_complete FROM meme_curve_snapshots "
    "      WHERE complete GROUP BY mint) s "
    "WHERE s.mint = t.mint AND t.rest_complete_seen_at IS NULL",
    # First presence on the graduated board.
    "UPDATE meme_tokens t SET graduated_board_seen_at = b.first_seen "
    "FROM (SELECT mint, min(first_seen_in_board_at) AS first_seen FROM meme_board_observations "
    "      WHERE board = 'graduated' GROUP BY mint) b "
    "WHERE b.mint = t.mint AND t.graduated_board_seen_at IS NULL",
    # The pool: the migrate frame this radar heard, else the earliest gd of any board row.
    "UPDATE meme_tokens SET pool_created_at = migrated_at, pool_created_source = 'pumpportal_ws' "
    "WHERE migrated_at IS NOT NULL AND pool_created_at IS NULL",
    "UPDATE meme_tokens t SET pool_created_at = g.graduated_at, pool_created_source = g.source "
    "FROM (SELECT DISTINCT ON (mint) mint, graduated_at, source FROM meme_board_observations "
    "      WHERE graduated_at IS NOT NULL ORDER BY mint, graduated_at, observed_at) g "
    "WHERE g.mint = t.mint AND t.pool_created_at IS NULL",
    # Every denominator held today came from a virgin photo (0021's only rule).
    "UPDATE meme_tokens SET progress_denominator_source = 'observed_virgin' "
    "WHERE initial_real_token_reserves IS NOT NULL AND progress_denominator_source IS NULL",
    # completed_at by the reducer's rule: the earliest signal, a REST complete
    # counting only when its photo carried SOL. LEAST of all NULLs is NULL — the
    # 77 REST-only zero-reserve coins become unclassified, which they are.
    "UPDATE meme_tokens t SET completed_at = LEAST(t.curve_filled_seen_at, "
    "  t.graduated_board_seen_at, t.pool_created_at, "
    "  (SELECT min(s.observed_at) FROM meme_curve_snapshots s "
    "   WHERE s.mint = t.mint AND s.complete AND s.real_sol_reserves > 0)) "
    "WHERE t.completed_at IS NOT NULL OR t.rest_complete_seen_at IS NOT NULL "
    "   OR t.graduated_board_seen_at IS NOT NULL OR t.pool_created_at IS NOT NULL",
)

_RADAR_VIEW_0024 = f"""
CREATE OR REPLACE VIEW {MEME_RADAR_VIEW} AS
SELECT f.mint, f.end_time, f.features_version, f.curve_progress_pct, f.progress_reason,
       f.mcap_sol, f.curve_reason, f.unique_buyers, f.unique_buyers_reason, f.buy_sell_ratio,
       f.buy_sell_ratio_reason, f.top10_share, f.top10_share_reason, f.creator_sold,
       f.creator_sold_reason, f.age_minutes, f.coverage, f.snapshot_observed_at,
       f.snapshot_source, t.name, t.symbol, t.creator, t.created_at AS token_created_at,
       t.pool, t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at,
       t.migrated_at, t.migrated_pool, t.first_seen_source, t.last_seen_at,
       t.rest_complete_seen_at, t.curve_filled_seen_at, t.graduated_board_seen_at,
       t.pool_created_at, t.pool_created_source, t.progress_denominator_source
FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
"""  # noqa: S608 - the only interpolation is this module's own frozen constant
"""``0021``'s projection with the six columns **appended**: ``CREATE OR REPLACE``
keeps the existing columns' names, types and order (a rule of Postgres, not a
convention) and keeps the grants."""

_RADAR_VIEW_0021 = f"""
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
"""``ddl/meme_radar.py``'s text, copied and frozen (never imported: the downgrade
must restore what ``0021`` shipped, not what a later edit of that module says).
A view cannot lose columns through ``CREATE OR REPLACE``, so the downgrade drops
and recreates it, then grants again."""

_MATRIX_VIEW = f"""
CREATE VIEW {MEME_GRADUATION_VIEW} AS
WITH signals AS (
    SELECT mint, completed_at,
           rest_complete_seen_at AS rest, curve_filled_seen_at AS filled,
           graduated_board_seen_at AS board, pool_created_at AS pool,
           LEAST(rest_complete_seen_at, curve_filled_seen_at,
                 graduated_board_seen_at, pool_created_at) AS first_signal_at,
           (rest_complete_seen_at IS NOT NULL)::int + (curve_filled_seen_at IS NOT NULL)::int
             + (graduated_board_seen_at IS NOT NULL)::int + (pool_created_at IS NOT NULL)::int
             AS signal_count
    FROM meme_tokens
    WHERE rest_complete_seen_at IS NOT NULL OR curve_filled_seen_at IS NOT NULL
       OR graduated_board_seen_at IS NOT NULL OR pool_created_at IS NOT NULL
)
SELECT (first_signal_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt,
       count(*) AS mints,
       count(*) FILTER (WHERE completed_at IS NOT NULL) AS completed,
       count(rest) AS rest_complete,
       count(filled) AS curve_filled,
       count(board) AS graduated_board,
       count(pool) AS pool_created,
       count(*) FILTER (WHERE signal_count = 1) AS signals_1,
       count(*) FILTER (WHERE signal_count = 2) AS signals_2,
       count(*) FILTER (WHERE signal_count = 3) AS signals_3,
       count(*) FILTER (WHERE signal_count = 4) AS signals_4,
       count(*) FILTER (WHERE (rest IS NULL) <> (filled IS NULL)) AS disagree_rest_filled,
       count(*) FILTER (WHERE (rest IS NULL) <> (board IS NULL)) AS disagree_rest_board,
       count(*) FILTER (WHERE (rest IS NULL) <> (pool IS NULL)) AS disagree_rest_pool,
       count(*) FILTER (WHERE (filled IS NULL) <> (board IS NULL)) AS disagree_filled_board,
       count(*) FILTER (WHERE (filled IS NULL) <> (pool IS NULL)) AS disagree_filled_pool,
       count(*) FILTER (WHERE (board IS NULL) <> (pool IS NULL)) AS disagree_board_pool,
       count(*) FILTER (WHERE rest IS NOT NULL AND completed_at IS NULL) AS rest_only_unclassified
FROM signals
GROUP BY 1
"""  # noqa: S608 - the only interpolation is this module's own frozen constant
"""One row per Brasília day of the *earliest* signal. No ORDER BY: the caller
asks for a day (the API asks for today's) and the scan is over ``meme_tokens``
rows that carry any stamp — a few hundred a day."""


def _write_once_branch(column: str) -> str:
    return (
        f"IF OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"RAISE EXCEPTION USING MESSAGE = "
        f"'PROJECT HUNTER: meme_tokens.{column} is written once and this UPDATE would "
        f"change an already observed value for mint ' || OLD.mint, "
        f"HINT = 'upsert identity with COALESCE(existing, new); only "
        f"{_MUTABLE_NOTE} may move after discovery'; END IF; "
    )


_COMPLETED_AT_BRANCH = (
    "IF OLD.completed_at IS NOT NULL AND (NEW.completed_at IS NULL "
    "OR NEW.completed_at > OLD.completed_at) THEN RAISE EXCEPTION USING MESSAGE = "
    "'PROJECT HUNTER: meme_tokens.completed_at is the earliest completion signal and may "
    "only move earlier for mint ' || OLD.mint, "
    "HINT = 'write completed_at as LEAST(existing, new); the four signals themselves "
    "are written once'; END IF; "
)


def add_graduation_columns() -> None:
    for statement in _ADD_COLUMNS:
        op.execute(statement)


def backfill_graduation_signals() -> None:
    """Evidence tables → stamps, with the ``0021`` trigger switched off for the
    one statement that must move ``completed_at`` to NULL (a REST-only zero-
    reserve coin is unclassified now) — the single moment the lock is lifted,
    in the revision that redefines what the column means."""
    op.execute(f"ALTER TABLE meme_tokens DISABLE TRIGGER {_TRIGGER}")
    for statement in _BACKFILL:
        op.execute(statement)
    op.execute(f"ALTER TABLE meme_tokens ENABLE TRIGGER {_TRIGGER}")


def add_graduation_checks() -> None:
    for statement in _CHECKS:
        op.execute(statement)


def drop_graduation_checks() -> None:
    for name in reversed(_CHECK_NAMES):
        op.execute(f"ALTER TABLE meme_tokens DROP CONSTRAINT IF EXISTS {name}")


def create_meme_token_guards_0024() -> None:
    """Replace the write-once function: the six stamps join the list,
    ``completed_at`` leaves it and gains the earliest-only branch."""
    branches = "".join(_write_once_branch(column) for column in WRITE_ONCE_COLUMNS_0024)
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_TRIGGER}() RETURNS trigger AS $$ "
        f"BEGIN {branches}{_COMPLETED_AT_BRANCH} RETURN NEW; END $$ LANGUAGE plpgsql"
    )


def create_graduation_views() -> None:
    op.execute(_RADAR_VIEW_0024)
    op.execute(_MATRIX_VIEW)
    op.execute(f"GRANT SELECT ON {MEME_GRADUATION_VIEW} TO {APP_ROLE}, {WORKER_ROLE}")


def restore_radar_view_0021() -> None:
    op.execute(f"DROP VIEW IF EXISTS {MEME_GRADUATION_VIEW}")
    op.execute(f"DROP VIEW IF EXISTS {MEME_RADAR_VIEW}")
    op.execute(_RADAR_VIEW_0021)
    op.execute(f"GRANT SELECT ON {MEME_RADAR_VIEW} TO {APP_ROLE}, {WORKER_ROLE}")


def drop_graduation_columns() -> None:
    for column in reversed(GRADUATION_COLUMNS_0024):
        op.execute(f"ALTER TABLE meme_tokens DROP COLUMN IF EXISTS {column}")


_GUARD_PREDICATE = (
    "WHERE rest_complete_seen_at IS NOT NULL OR curve_filled_seen_at IS NOT NULL "
    "OR graduated_board_seen_at IS NOT NULL OR pool_created_at IS NOT NULL "
    "OR progress_denominator_source = 'global_params'"
)


def refuse_a_downgrade_that_would_lose_a_completion_signal() -> None:
    """§17.7: a stamp is the first sighting of an event nobody serves again —
    count, name, stop. On every database of today it counts zero."""
    safe_predicate = _GUARD_PREDICATE.replace("'", "''")  # inside the HINT literal
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM meme_tokens {_GUARD_PREDICATE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_tokens rows carry a completion "
        f"signal or a global-params denominator - the first sighting of a graduation is not "
        f"re-observable', "
        f"HINT = 'COPY (SELECT * FROM meme_tokens {safe_predicate}) TO ... before reversing'; "
        f"END IF; END $$;"
    )
