"""The one ``meme_tokens`` upsert statement, split out of ``repo.py`` for the
350-line budget — this module has exactly one export, ``UPSERT_TOKEN``, and
exists only because building that statement's text needs three separate
column lists first.
"""

from __future__ import annotations

from sqlalchemy import text

__all__ = ["UPSERT_TOKEN"]

IDENTITY_COLUMNS = (
    "name",
    "symbol",
    "uri",
    "creator",
    "created_at",
    "bonding_curve",
    "bonding_curve_raw",
    "initial_virtual_sol_reserves",
    "initial_virtual_token_reserves",
    # T4.45 (``0048``): facts of the creation instant, so write-once like the
    # reserves beside them - a later *current* reading of the dev's holdings
    # must never become the base the admission compares against.
    "creator_initial_tokens",
    "creator_initial_sol",
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
    # T4.26 (``0041``): nine of the eleven social columns — written once,
    # together (``WRITE_ONCE_COLUMNS_0041``, ``ddl/meme_social.py``).
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
"""Filled once; ``COALESCE(meme_tokens.<c>, excluded.<c>)`` keeps the first answer.
The same list the database freezes in ``ddl/meme_graduation.py``
(``WRITE_ONCE_COLUMNS_0024``) — copied, never imported, because
``infra/migrations`` is not importable from a service and because the contract of
the database must not follow a later edit of a Python constant. ``completed_at``
left this list in ``0024``: it is reduced, not observed (``repo.py``'s own
module docstring)."""

_ALL_TOKEN_COLUMNS = (
    "mint",
    "first_seen_source",
    "first_seen_at",
    "last_seen_at",
    "completed_at",
    *IDENTITY_COLUMNS,
    # T4.26: the two reuse-count columns are mutable (like ``mayhem_state``),
    # so they are inserted here but updated by their own COALESCE below, not
    # by the write-once loop over ``IDENTITY_COLUMNS``.
    "twitter_reuse_count",
    "twitter_reuse_observed_at",
)

UPSERT_TOKEN = text(
    # ``mayhem_mode``/``mayhem_state`` are mutable state, so they are not in the
    # write-once list — but they must be *inserted* (T4.2e: until then the
    # INSERT omitted them, ``excluded.mayhem_state`` was always NULL, the column
    # never held a value and ``_LOAD_TRACKED``'s "a paused agent keeps the mint"
    # never fired). The CASE is the CHECK ``a_disabled_token_has_no_agent_state``.
    f"INSERT INTO meme_tokens ({', '.join(_ALL_TOKEN_COLUMNS)}, mayhem_mode, mayhem_state) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _ALL_TOKEN_COLUMNS)}, :mayhem_mode, "
    "CASE WHEN :mayhem_enabled IS FALSE THEN NULL ELSE :mayhem_state END) "
    "ON CONFLICT (mint) DO UPDATE SET "
    + ", ".join(
        f"{column} = COALESCE(meme_tokens.{column}, excluded.{column})"
        for column in IDENTITY_COLUMNS
    )
    # The earliest of the four completion signals, across every observation.
    + ", completed_at = LEAST(meme_tokens.completed_at, excluded.completed_at)"
    # Mutable state: the newest observation wins, because that is what state means.
    + ", mayhem_mode = COALESCE(excluded.mayhem_mode, meme_tokens.mayhem_mode)"
    # And a token measured as *not* Mayhem carries no agent state: the CHECK
    # ``a_disabled_token_has_no_agent_state`` refuses that pair, and letting the
    # upsert build it would abort a whole collector cycle over a disagreement
    # between two sources. The conflict is reported by the caller, not written.
    + ", mayhem_state = CASE WHEN COALESCE(meme_tokens.mayhem_enabled, excluded.mayhem_enabled)"
    " IS FALSE THEN NULL ELSE COALESCE(excluded.mayhem_state, meme_tokens.mayhem_state) END"
    # T4.26: the indexer's reuse count is mutable too — a clone can start
    # reusing a handle long after this mint was discovered, so the newest
    # observation (when one arrived) wins, exactly like mayhem_mode.
    + ", twitter_reuse_count = COALESCE(excluded.twitter_reuse_count, meme_tokens.twitter_reuse_count)"
    + ", twitter_reuse_observed_at = COALESCE(excluded.twitter_reuse_observed_at, "
    "meme_tokens.twitter_reuse_observed_at)"
    + ", last_seen_at = GREATEST(meme_tokens.last_seen_at, excluded.last_seen_at)"
    + ", updated_at = now()"
)
