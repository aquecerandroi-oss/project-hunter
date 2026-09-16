"""``0041_meme_social`` — the social identity pump.fun already carries, per
mint (T4.26).

**Why:** the funnel reads curve, flow, holders, snipers, dev and pedigree, but
discards the identity pump.fun already hands back on ``/coins/{mint}``
(``twitter?``, ``website?``, ``telegram?``, ``description``, ``metadata_uri``
— ``docs/PUMPFUN.md`` §1.3/§1.1) and the indexer's ``twitterReuseCount``
(``docs/PUMPFUN.md`` §3.1). Without it, the $TRUMP case's decisive signal —
"who announced, where, and how verifiable" — never reaches the machine. The
plantão measured (M-P17) that a ``twitter`` link pointing at a **post**
≤ 10 min before creation associates with the slow, organic cells, and (M-P33)
that clones reuse the same handle.

**Eleven columns on ``meme_tokens``**, all nullable (``NULL`` = not
observed): ``twitter``, ``telegram``, ``website``, ``description`` (≤ 2 000
chars, truncated with a marker by the collector — ``ddl.meme_social_checks``'s
CHECK is the backstop), ``twitter_kind`` (``profile`` | ``post`` |
``community`` | ``other``), ``twitter_post_id`` (a snowflake, present exactly
when ``twitter_kind = 'post'``), ``twitter_post_at`` (decoded from the
snowflake once, never re-derived), ``twitter_reuse_count`` +
``twitter_reuse_observed_at`` (the indexer's counter — **mutable**, unlike
every other column here: clones keep appearing after discovery) and
``social_observed_at`` + ``social_source`` (``pumpfun_rest`` | ``indexer_rest``
| ``metadata_uri``).

**Identity is written once**, the ``0021``/``0024`` rule extended: nine of the
eleven columns join ``WRITE_ONCE_COLUMNS_0041``; the two reuse-count columns
stay mutable, the same argument that keeps ``mayhem_mode``/``mayhem_state``
out of the write-once list.

The view ``meme_radar_features_v1`` is replaced with the nine identity columns
appended (grants kept); nothing is backfilled — no prior revision ever wrote
these fields, so every existing row starts at ``NULL`` and is filled by the
next observation, exactly as ``0021``'s own columns were on day one.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_social_checks import CHECK_NAMES_0041, CHECKS_0041
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_RADAR_VIEW = "meme_radar_features_v1"

SOCIAL_COLUMNS_0041: tuple[tuple[str, str], ...] = (
    ("twitter", "text"),
    ("telegram", "text"),
    ("website", "text"),
    ("description", "text"),
    ("twitter_kind", "text"),
    ("twitter_post_id", "bigint"),
    ("twitter_post_at", "timestamptz"),
    ("twitter_reuse_count", "integer"),
    ("twitter_reuse_observed_at", "timestamptz"),
    ("social_observed_at", "timestamptz"),
    ("social_source", "text"),
)
"""The eleven columns this revision adds to ``meme_tokens``, frozen."""

WRITE_ONCE_COLUMNS_0041: tuple[str, ...] = (
    "twitter",
    "telegram",
    "website",
    "description",
    "twitter_kind",
    "twitter_post_id",
    "twitter_post_at",
    "social_observed_at",
    "social_source",
)
"""Nine of the eleven — the reuse count and its stamp are deliberately absent,
the same argument that keeps ``mayhem_mode``/``mayhem_state`` mutable: a clone
can start reusing a handle long after this mint was discovered, so the newest
reading has to win."""

WRITE_ONCE_COLUMNS_0024 = (
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
"""``ddl/meme_graduation.py``'s ``WRITE_ONCE_COLUMNS_0024``, copied rather than
imported — the reason every such list in this schema is: a future edit of
``0024`` must not silently change what ``0041`` locks, and a downgrade must be
able to restore exactly this shape without reaching across revisions."""

WRITE_ONCE_COLUMNS_FULL_0041 = (*WRITE_ONCE_COLUMNS_0024, *WRITE_ONCE_COLUMNS_0041)
"""``0024``'s list plus this revision's nine. ``completed_at`` stays out,
reduced by its own ``LEAST``-only branch."""

_TRIGGER = "meme_tokens_identity_is_written_once"
_MUTABLE_NOTE = (
    "mayhem_mode, mayhem_state, last_seen_at, updated_at, "
    "twitter_reuse_count, twitter_reuse_observed_at"
)

_ADD_COLUMNS = tuple(
    f"ALTER TABLE meme_tokens ADD COLUMN {column} {kind}" for column, kind in SOCIAL_COLUMNS_0041
)

_COMPLETED_AT_BRANCH = (
    "IF OLD.completed_at IS NOT NULL AND (NEW.completed_at IS NULL "
    "OR NEW.completed_at > OLD.completed_at) THEN RAISE EXCEPTION USING MESSAGE = "
    "'PROJECT HUNTER: meme_tokens.completed_at is the earliest completion signal and may "
    "only move earlier for mint ' || OLD.mint, "
    "HINT = 'write completed_at as LEAST(existing, new); the four signals themselves "
    "are written once'; END IF; "
)


def _write_once_branch(column: str) -> str:
    return (
        f"IF OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"RAISE EXCEPTION USING MESSAGE = "
        f"'PROJECT HUNTER: meme_tokens.{column} is written once and this UPDATE would "
        f"change an already observed value for mint ' || OLD.mint, "
        f"HINT = 'upsert identity with COALESCE(existing, new); only "
        f"{_MUTABLE_NOTE} may move after discovery'; END IF; "
    )


def add_social_columns() -> None:
    for statement in _ADD_COLUMNS:
        op.execute(statement)


def add_social_checks() -> None:
    for statement in CHECKS_0041:
        op.execute(statement)


def drop_social_checks() -> None:
    for name in reversed(CHECK_NAMES_0041):
        op.execute(f"ALTER TABLE meme_tokens DROP CONSTRAINT IF EXISTS {name}")


def create_meme_token_guards_0041() -> None:
    """Replace the write-once function: the nine identity columns join the
    list; the reuse count and its stamp stay mutable."""
    branches = "".join(_write_once_branch(column) for column in WRITE_ONCE_COLUMNS_FULL_0041)
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_TRIGGER}() RETURNS trigger AS $$ "
        f"BEGIN {branches}{_COMPLETED_AT_BRANCH} RETURN NEW; END $$ LANGUAGE plpgsql"
    )


def restore_meme_token_guards_0024() -> None:
    """The downgrade's mirror: put the function back exactly as ``0024`` left
    it, **before** the nine columns it would otherwise still reference are
    dropped — a stale ``NEW.twitter`` in a live trigger body is a runtime
    error on the next observation, not a deploy-time one."""
    branches = "".join(_write_once_branch(column) for column in WRITE_ONCE_COLUMNS_0024)
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_TRIGGER}() RETURNS trigger AS $$ "
        f"BEGIN {branches}{_COMPLETED_AT_BRANCH} RETURN NEW; END $$ LANGUAGE plpgsql"
    )


_RADAR_VIEW_0041 = f"""
CREATE OR REPLACE VIEW {MEME_RADAR_VIEW} AS
SELECT f.mint, f.end_time, f.features_version, f.curve_progress_pct, f.progress_reason,
       f.mcap_sol, f.curve_reason, f.unique_buyers, f.unique_buyers_reason, f.buy_sell_ratio,
       f.buy_sell_ratio_reason, f.top10_share, f.top10_share_reason, f.creator_sold,
       f.creator_sold_reason, f.age_minutes, f.coverage, f.snapshot_observed_at,
       f.snapshot_source, t.name, t.symbol, t.creator, t.created_at AS token_created_at,
       t.pool, t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at,
       t.migrated_at, t.migrated_pool, t.first_seen_source, t.last_seen_at,
       t.rest_complete_seen_at, t.curve_filled_seen_at, t.graduated_board_seen_at,
       t.pool_created_at, t.pool_created_source, t.progress_denominator_source,
       t.twitter, t.telegram, t.website, t.description, t.twitter_kind,
       t.twitter_post_id, t.twitter_post_at, t.twitter_reuse_count,
       t.twitter_reuse_observed_at, t.social_observed_at, t.social_source
FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
"""  # noqa: S608 - the only interpolation is this module's own frozen constant
"""``0024``'s projection with the nine identity columns **appended** (the
reuse count and its stamp too — the desk reads them next to the rest);
``CREATE OR REPLACE`` keeps every existing column's name, type and order."""

_RADAR_VIEW_0024 = f"""
CREATE VIEW {MEME_RADAR_VIEW} AS
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
"""``ddl/meme_graduation.py``'s text, copied and frozen — the downgrade must
restore what ``0024`` shipped, never what a later edit of that module says.
``CREATE VIEW``, not ``CREATE OR REPLACE``: Postgres refuses to drop columns
from a view with ``REPLACE`` (``0021``'s own ``restore_radar_view_0021`` hits
the same wall and drops first), and this revision's whole point is dropping
nine columns the ``0041`` view added."""


def create_social_view() -> None:
    op.execute(_RADAR_VIEW_0041)


def restore_radar_view_0024() -> None:
    """Drop first: ``CREATE OR REPLACE`` cannot remove the nine columns this
    revision added, only ``0021``'s own precedent (drop, then recreate) can."""
    op.execute(f"DROP VIEW IF EXISTS {MEME_RADAR_VIEW}")
    op.execute(_RADAR_VIEW_0024)
    op.execute(f"GRANT SELECT ON {MEME_RADAR_VIEW} TO {APP_ROLE}, {WORKER_ROLE}")


def drop_social_columns() -> None:
    for column, _kind in reversed(SOCIAL_COLUMNS_0041):
        op.execute(f"ALTER TABLE meme_tokens DROP COLUMN IF EXISTS {column}")


_GUARD_PREDICATE = "WHERE social_observed_at IS NOT NULL OR twitter_reuse_count IS NOT NULL"


def refuse_a_downgrade_that_would_lose_a_social_read() -> None:
    """§17.7: a social read is the first sighting of an identity nobody serves
    again — count, name, stop."""
    safe_predicate = _GUARD_PREDICATE.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM meme_tokens {_GUARD_PREDICATE}; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_tokens rows carry a social read - "
        f"the first sighting of a coin''s identity is not re-observable', "
        f"HINT = 'COPY (SELECT * FROM meme_tokens {safe_predicate}) TO ... before reversing'; "
        f"END IF; END $$;"
    )
