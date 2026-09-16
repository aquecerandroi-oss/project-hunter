"""Schema pieces of ``0047_meme_bonding_curve_raw`` (T4.39): one nullable
column plus the write-once trigger extended to cover it.

Split from the migration itself, the shape every ``ddl/meme_*`` module in this
schema takes. The write-once column lists are **copied, not imported** from
``ddl/meme_social.py`` — the same reasoning that module's own docstring gives
for copying ``ddl/meme_graduation.py``'s list rather than reaching across
revisions: a later edit of ``meme_social.py`` must not silently change what
this revision restores on a downgrade.
"""

from __future__ import annotations

from alembic import op

__all__ = [
    "WRITE_ONCE_COLUMNS_FULL_0041",
    "WRITE_ONCE_COLUMNS_FULL_0047",
    "add_bonding_curve_raw_column",
    "create_meme_token_guards_0047",
    "drop_bonding_curve_raw_column",
    "refuse_a_downgrade_that_would_lose_bonding_curve_raw",
    "restore_meme_token_guards_0041",
]

COLUMN = "bonding_curve_raw"

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
"""``ddl/meme_graduation.py``'s list, copied — see module docstring."""

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
"""``ddl/meme_social.py``'s nine identity columns, copied."""

WRITE_ONCE_COLUMNS_FULL_0041 = (*WRITE_ONCE_COLUMNS_0024, *WRITE_ONCE_COLUMNS_0041)
"""The function's shape immediately before this revision — what the downgrade
restores."""

WRITE_ONCE_COLUMNS_FULL_0047 = (*WRITE_ONCE_COLUMNS_FULL_0041, COLUMN)
"""``0041``'s full list plus this revision's one column: the raw sighting a
Mayhem ``create`` frame carried, kept exactly as first observed."""

_TRIGGER = "meme_tokens_identity_is_written_once"
_MUTABLE_NOTE = (
    "mayhem_mode, mayhem_state, last_seen_at, updated_at, "
    "twitter_reuse_count, twitter_reuse_observed_at"
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


def _install(columns: tuple[str, ...]) -> None:
    branches = "".join(_write_once_branch(c) for c in columns)
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_TRIGGER}() RETURNS trigger AS $$ "
        f"BEGIN {branches}{_COMPLETED_AT_BRANCH} RETURN NEW; END $$ LANGUAGE plpgsql"
    )


def add_bonding_curve_raw_column() -> None:
    op.execute(f"ALTER TABLE meme_tokens ADD COLUMN {COLUMN} text")


def drop_bonding_curve_raw_column() -> None:
    op.execute(f"ALTER TABLE meme_tokens DROP COLUMN IF EXISTS {COLUMN}")


def create_meme_token_guards_0047() -> None:
    """Replace the write-once function: ``bonding_curve_raw`` joins the list."""
    _install(WRITE_ONCE_COLUMNS_FULL_0047)


def restore_meme_token_guards_0041() -> None:
    """The downgrade's mirror: put ``0041``'s function back **before** the
    column it would otherwise still reference is dropped."""
    _install(WRITE_ONCE_COLUMNS_FULL_0041)


def refuse_a_downgrade_that_would_lose_bonding_curve_raw() -> None:
    """§17.7: a raw sighting is the only copy of a create frame's mismatch —
    once the frame is gone (PumpPortal's free channel has no replay), nobody
    can reconstruct what it originally said."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM meme_tokens WHERE {COLUMN} IS NOT NULL; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_tokens rows carry a "
        "bonding_curve_raw value - the first sighting of a create frame''s mismatch "
        "is not re-observable', "
        f"HINT = 'COPY (SELECT mint, {COLUMN} FROM meme_tokens WHERE {COLUMN} IS NOT NULL) "
        "TO ... before reversing'; END IF; END $$;"
    )
