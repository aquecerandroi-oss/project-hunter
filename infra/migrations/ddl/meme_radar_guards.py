"""The two triggers of ``0021_meme_radar`` and its downgrade guard.

Split from ``ddl/meme_radar.py`` for the 350-line budget
(``infra/scripts/check_file_size.py``), the same cut ``execution.py`` (§18.10) and
``seed_reference.py`` (§28.7) took: the *shape* of the schema is there, the
*locks* on it are here.

Both triggers exist because a grant cannot express what has to be true:

- ``hunter_worker`` needs ``UPDATE`` on ``meme_tokens`` (a token's lifecycle
  genuinely moves after discovery) and ``UPDATE`` carries every column, so the
  grant alone would let a later, poorer observation overwrite a richer earlier
  one — ``NULL`` over a name, a second ``migrated_at``, a rewritten
  ``created_at``. ``meme_tokens_identity_is_written_once`` makes ``NULL -> value``
  legal exactly once and any other change of a known value illegal, **for every
  role including the owner**, which is a stronger lock than any ``REVOKE`` (the
  ``feature_baselines_immutable`` argument, §17.2);
- ``hunter_worker`` needs ``DELETE`` on ``meme_tokens`` because retention cannot
  prune it by dropping a partition (its key is the mint). A bug in the collector
  must not be able to erase the discovery history the radar's own rates are
  counted against, so the deletion is gated by a declared transaction marker —
  ``SET LOCAL app.meme_retention = 'on'`` — exactly as ``feature_baselines``
  gates its own retention with ``app.baseline_retention`` (§17.2). The marker is
  **isolation, not authorization** (§18.8's correction: a ``SET LOCAL`` anyone can
  write authenticates nobody); what it buys is that deleting is an act rather than
  an accident, and it is transaction-scoped, therefore safe behind the pooler.
"""

from __future__ import annotations

from alembic import op

WRITE_ONCE_COLUMNS_0021: tuple[str, ...] = (
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
    "total_supply",
    "pool",
    "mayhem_enabled",
    "completed_at",
    "migrated_at",
    "migrated_pool",
    "first_seen_source",
    "first_seen_at",
)
"""Identity and first-observation stamps. ``NULL -> value`` once; never a rewrite.

``mayhem_enabled`` is here because eligibility is decided **at creation** on chain
(A4.1b §5: ``create_v2.is_mayhem_mode``), so a second answer is a disagreement
between sources and not news. The consequence is declared rather than hidden: the
schema keeps the first answer and *refuses* the second, so reconciling a conflict
is the collector's job (compare before writing, report it) — the upsert writes
these columns with ``COALESCE`` and therefore never trips the trigger on the happy
path.

Deliberately **absent**, i.e. freely mutable: ``mayhem_mode``, ``mayhem_state``
(the agent moves through ``active``/``paused``/``completed`` by design — that is
the state this radar exists to watch), ``last_seen_at`` and ``updated_at``.
"""

_MUTABLE_NOTE = "mayhem_mode, mayhem_state, last_seen_at, updated_at"

_WRITE_ONCE_FUNCTION = "meme_tokens_identity_is_written_once"
_RETENTION_FUNCTION = "meme_tokens_retention_is_declared"

RETENTION_MARKER = "app.meme_retention"
"""Transaction-scoped, read with ``NULLIF(current_setting(..., true), '')`` — the
pooler-safe form every marker in this schema uses (§15.4, §17.2, §18.10)."""


def _write_once_branch(column: str) -> str:
    """One refusal per column: a known value may not become a different one."""
    return (
        f"IF OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"RAISE EXCEPTION USING MESSAGE = "
        f"'PROJECT HUNTER: meme_tokens.{column} is written once and this UPDATE would "
        f"change an already observed value for mint ' || OLD.mint, "
        f"HINT = 'upsert identity with COALESCE(existing, new); only "
        f"{_MUTABLE_NOTE} may move after discovery'; END IF; "
    )


def create_meme_token_guards() -> None:
    """Install both triggers. Idempotent: replace the function, recreate the trigger."""
    branches = "".join(_write_once_branch(column) for column in WRITE_ONCE_COLUMNS_0021)
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_WRITE_ONCE_FUNCTION}() RETURNS trigger AS $$ "
        f"BEGIN {branches} RETURN NEW; END $$ LANGUAGE plpgsql"
    )
    op.execute(f"DROP TRIGGER IF EXISTS {_WRITE_ONCE_FUNCTION} ON meme_tokens")
    op.execute(
        f"CREATE TRIGGER {_WRITE_ONCE_FUNCTION} BEFORE UPDATE ON meme_tokens "
        f"FOR EACH ROW EXECUTE FUNCTION {_WRITE_ONCE_FUNCTION}()"
    )
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_RETENTION_FUNCTION}() RETURNS trigger AS $$ BEGIN "
        f"IF NULLIF(current_setting('{RETENTION_MARKER}', true), '') IS DISTINCT FROM 'on' THEN "
        f"RAISE EXCEPTION USING MESSAGE = "
        f"'PROJECT HUNTER: meme_tokens rows are discovery history and may not be deleted "
        f"without declaring retention', "
        f"HINT = 'SET LOCAL {RETENTION_MARKER} = ''on'' in the same transaction'; END IF; "
        f"RETURN OLD; END $$ LANGUAGE plpgsql"
    )
    op.execute(f"DROP TRIGGER IF EXISTS {_RETENTION_FUNCTION} ON meme_tokens")
    op.execute(
        f"CREATE TRIGGER {_RETENTION_FUNCTION} BEFORE DELETE ON meme_tokens "
        f"FOR EACH ROW EXECUTE FUNCTION {_RETENTION_FUNCTION}()"
    )


def drop_meme_token_guards() -> None:
    """Triggers and functions go; the table drop would take the triggers anyway,
    but leaving the two functions behind would leave ``0020`` with two dangling
    objects named after a table that no longer exists."""
    op.execute(f"DROP TRIGGER IF EXISTS {_WRITE_ONCE_FUNCTION} ON meme_tokens")
    op.execute(f"DROP TRIGGER IF EXISTS {_RETENTION_FUNCTION} ON meme_tokens")
    op.execute(f"DROP FUNCTION IF EXISTS {_WRITE_ONCE_FUNCTION}()")
    op.execute(f"DROP FUNCTION IF EXISTS {_RETENTION_FUNCTION}()")


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_tokens",
        "discovery rows - the universe of creations every graduation and rug rate is "
        "counted against, and it is not recomputable: the PumpPortal feed is ephemeral "
        "and the REST mirror only lists what is recent",
    ),
    (
        "meme_curve_snapshots",
        "curve observations - nobody serves the state a curve had at a past instant, so "
        "these rows are the only copy",
    ),
    (
        "meme_features_1m",
        "folded minutes - the snapshots they were derived from expire on the same "
        "90-day window, so the fold is not reproducible after that",
    ),
    ("meme_trades", "decoded trades with their per-operation Mayhem attribution"),
    (
        "meme_ingest_gaps",
        "accounted holes - a window nobody was listening to cannot be rediscovered later, "
        "and losing it turns a known gap into apparent continuity",
    ),
)
"""Every table gets a guard, and ``meme_trades`` gets one although it has no
producer in this slice: the guard is about what a *populated* database would lose,
and on every database of today each of the five counts zero — which is exactly why
the round trip in ``test_migrations.py`` passes without exporting anything."""


def refuse_a_downgrade_that_would_lose_meme_rows() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, why in _GUARDED:
        safe_why = why.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table}) TO ... before reversing, and understand "
            f"that the meme radar restarts with no history'; END IF; END $$;"
        )
