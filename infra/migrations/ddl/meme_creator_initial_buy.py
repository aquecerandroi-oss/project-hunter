"""Schema pieces of ``0048_meme_creator_initial_buy`` (T4.45): the creator's own
buy **at creation**, two nullable columns plus the write-once trigger extended
to cover them.

Why this datum and not the one we already had: every other reading of the
creator's holding — ``devHoldingsPercent`` on ``meme_risk_snapshots`` /
``meme_features_1m`` — is a **current** photograph whose first sample landed
+114 to +419 s after the coin existed (T4.28g §2.3, measured 16/09/2026). A
current photograph cannot tell "the dev still holds his allocation" from "the
dev already dumped it all": both read as *what he has now*. Comparing the
creator's on-chain balance against the allocation recorded **at the create
instant** can, and that is the only honest way to answer check 10
(``creator_behaviour``) at decision time.

The unit is **tokens**, the same as ``initial_real_token_reserves`` — proven by
the frame's own arithmetic (``1 073 000 000 - initialBuy ==
vTokensInBondingCurve``, ``hunter_exchanges.pumpfun.normalize``), so nothing
downstream has to carry a second convention.

No backfill here — and none in a script either: see the revision's docstring.

Upgrade guard: none, the columns are new and every existing row starts at
``NULL``. The downgrade refuses while any row carries a value (§17.7): the
PumpPortal ``create`` frame is a free channel with **no replay**, so an
allocation observed once at creation cannot be observed again.
"""

from __future__ import annotations

from alembic import op

__all__ = [
    "WRITE_ONCE_COLUMNS_FULL_0047",
    "WRITE_ONCE_COLUMNS_FULL_0048",
    "add_creator_initial_buy_columns",
    "create_meme_token_guards_0048",
    "drop_creator_initial_buy_columns",
    "refuse_a_downgrade_that_would_lose_the_creators_initial_buy",
    "restore_meme_token_guards_0047",
]

COLUMNS: tuple[str, ...] = ("creator_initial_tokens", "creator_initial_sol")

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
"""``ddl/meme_graduation.py``'s list, **copied not imported** — the same reason
``ddl/meme_bonding_curve_raw.py`` gives: a later edit of another revision's
constant must not silently change what this one restores on a downgrade."""

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

WRITE_ONCE_COLUMNS_FULL_0047: tuple[str, ...] = (
    *WRITE_ONCE_COLUMNS_0024,
    *WRITE_ONCE_COLUMNS_0041,
    "bonding_curve_raw",
)
"""The function's shape immediately before this revision (``0047``) — what the
downgrade restores."""

WRITE_ONCE_COLUMNS_FULL_0048: tuple[str, ...] = (*WRITE_ONCE_COLUMNS_FULL_0047, *COLUMNS)
"""``0047``'s list plus this revision's two: the creator's allocation is a fact
of the creation instant, so a later observation may never rewrite it. That is
the whole guarantee the executor leans on — a value that could be overwritten by
a *current* reading would be the stale-photograph bug all over again."""

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

_NOT_NEGATIVE = "ck_meme_tokens_a_dev_buy_is_not_negative"


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


def add_creator_initial_buy_columns() -> None:
    """Two nullable ``numeric(28, 10)`` columns — the neighbours' type
    (``initial_real_token_reserves``), so the denominator and the creator's slice
    of it are comparable without a cast.

    The pair is deliberately **not** constrained to be written together: a
    thinner ``create`` frame may carry the tokens and not the SOL, and refusing
    that row would lose the very datum this revision exists for. Both are
    refused when **negative** — a negative allocation is a frame we do not
    understand, not a small number.
    """
    for column in COLUMNS:
        op.execute(f"ALTER TABLE meme_tokens ADD COLUMN {column} numeric(28, 10)")
    op.execute(
        f"ALTER TABLE meme_tokens ADD CONSTRAINT {_NOT_NEGATIVE} CHECK ("
        f"({COLUMNS[0]} IS NULL OR {COLUMNS[0]} >= 0) "
        f"AND ({COLUMNS[1]} IS NULL OR {COLUMNS[1]} >= 0))"
    )


def drop_creator_initial_buy_columns() -> None:
    op.execute(f"ALTER TABLE meme_tokens DROP CONSTRAINT IF EXISTS {_NOT_NEGATIVE}")
    for column in COLUMNS:
        op.execute(f"ALTER TABLE meme_tokens DROP COLUMN IF EXISTS {column}")


def create_meme_token_guards_0048() -> None:
    """Replace the write-once function: the creator's initial buy joins the list."""
    _install(WRITE_ONCE_COLUMNS_FULL_0048)


def restore_meme_token_guards_0047() -> None:
    """The downgrade's mirror: ``0047``'s function back **before** the columns it
    would otherwise still reference are dropped."""
    _install(WRITE_ONCE_COLUMNS_FULL_0047)


def refuse_a_downgrade_that_would_lose_the_creators_initial_buy() -> None:
    """§17.7: the ``create`` frame that carried this allocation is not replayable
    (PumpPortal's free channel has no history), and the on-chain alternative — a
    ``getTransaction`` of the creation signature — is a paid, rate-limited scan
    of a slot that may already be outside the RPC's retention. Dropping the
    column is therefore destructive, and a downgrade says so instead of doing it.
    """
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM meme_tokens WHERE {COLUMNS[0]} IS NOT NULL "
        f"OR {COLUMNS[1]} IS NOT NULL; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_tokens rows carry the "
        "creator''s initial buy - an allocation observed at the create instant is not "
        "re-observable', "
        f"HINT = 'COPY (SELECT mint, {COLUMNS[0]}, {COLUMNS[1]} FROM meme_tokens "
        f"WHERE {COLUMNS[0]} IS NOT NULL OR {COLUMNS[1]} IS NOT NULL) TO ... before reversing'; "
        "END IF; END $$;"
    )
