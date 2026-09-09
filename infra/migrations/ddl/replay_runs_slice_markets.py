"""``0018_replay_runs_slice_markets`` — a slice is a window **and** a market set.

``0013`` (§25) made the receipt of a replay durable and keyed it on
``UNIQUE (run_id, window_from, window_to)``. That key names a *window*, and the
unit it was meant to name is a **slice** — which is a window and the markets
that window was dispatched over. T3.62 measured the difference: one cohort per
version, four market slices inside each window, and
``ON CONFLICT (run_id, window_from, window_to) DO NOTHING`` kept the first of
each four and silently dropped the other three. **8 receipts for 32 runs**;
``replay_runs`` reported ``mkts = 4, bars = 5760, signals = 11`` for work that
was 16 markets, 47 616 bars and 147 decisions. Nothing failed, nothing logged
above ``info``, and the full receipt survived only in ``system_events`` (30-day
retention, §1.3) and in a JSONL that exists if somebody kept the file — that is,
in the two places ``0013`` exists precisely because they are not durable.

**The fix is a fourth column in the key, not a wider one.** ``markets_digest``
is the SHA-256 of the sorted market keys of the slice; adding it to
``uq_replay_runs_slice`` can only *relax* the old key (it is a strict superset),
so no receipt already stored can start colliding — which is why this revision
needs no upgrade guard about the key at all.

**Why a digest and not the ``markets`` array in the key.** ``text[]`` equality
is order-sensitive, so the same four markets dispatched in another order would
be a second slice of work that already has a receipt; and a UNIQUE over a
variable-length array is a key whose size nobody bounds. The digest is derived
from the *sorted* list, so order cannot fabricate a slice.

**Backfilled from the row itself, never from a sentinel.** ``markets text[] NOT
NULL`` has been on the table since ``0013``, so every stored receipt already
carries exactly the input the digest is computed from: the backfill is
derivation, not invention — the ``0002`` boundary (backfill what the existing
columns *imply*; refuse what they merely suggest). No ``'legacy'`` placeholder
exists anywhere, and ``ck_replay_runs_markets_digest_is_a_sha256`` makes one
unrepresentable.

**A copy that can disagree with its source is worse than no copy** (§18.2). The
digest is a copy of something the same row already holds, so
``replay_runs_digest_names_the_markets`` (``BEFORE INSERT OR UPDATE``) computes
it and:

- **fills it in** when the writer left it ``NULL`` — every writer that predates
  this revision keeps working and gets the right digest, and a receipt is never
  lost to a deploy ordering;
- **refuses** when the writer sent one that is not the digest of ``NEW.markets``
  — a wrong digest is exactly the failure this revision exists to end, because
  two different market slices that share a wrong digest collide again.

Everything here is frozen as of ``0018``, the rule every module in this package
states for its own: :data:`MARKETS_DIGEST_PATTERN_0018` and :func:`digest_sql`
are **copies** of ``hunter_core.domain.digests``, never imports.

Described in ``docs/DATABASE.md`` §30.
"""

from __future__ import annotations

from alembic import op

TABLE = "replay_runs"
DIGEST_COLUMN = "markets_digest"
MARKETS_COLUMN = "markets"

UNIQUE_NAME = "uq_replay_runs_slice"
"""The name does not change, and that is deliberate: it has always meant "the
key of a slice", and this revision corrects what a slice *is* rather than
introducing a second name for it. Every log line, error message and note that
already cites ``uq_replay_runs_slice`` keeps pointing at the right constraint.
"""

SLICE_KEY_0013: tuple[str, ...] = ("run_id", "window_from", "window_to")
"""What ``0013`` made unique — restored, if it can be, by the downgrade."""

SLICE_KEY_0018: tuple[str, ...] = (*SLICE_KEY_0013, DIGEST_COLUMN)
"""A strict superset of ``0013``'s, which is why no stored row can start
colliding and why there is no upgrade guard for the key."""

MARKETS_DIGEST_PATTERN_0018 = "^[0-9a-f]{64}$"
"""Frozen copy of ``hunter_core.domain.digests.MARKETS_DIGEST_PATTERN``.

Lower-case hex SHA-256 and nothing else, so ``'legacy'``, ``''`` and ``'none'``
are all refused by the database rather than by a convention: a receipt that
claims a digest it does not have would put two different market slices back on
one key, which is the bug this revision closes.
"""

DIGEST_TRIGGER = "replay_runs_digest_names_the_markets"
DIGEST_FUNCTION = DIGEST_TRIGGER

CK_DIGEST_SHAPE = "ck_replay_runs_markets_digest_is_a_sha256"
CK_MARKETS_NAMED = "ck_replay_runs_markets_has_no_unnamed_member"


def digest_sql(markets_expression: str) -> str:
    """The canonical digest, in SQL, over any expression of type ``text[]``.

    One function written twice — this and
    ``hunter_core.domain.digests.markets_digest`` — because the backfill and the
    trigger run inside the database and the writer runs outside it. Copied and
    never imported, for the reason this package always gives; the pair is
    compared over the same lists by
    ``test_0018_the_python_digest_and_the_sql_expression_are_one_function``.

    Three details are the contract, not the implementation:

    - ``ORDER BY m COLLATE "C"`` — byte order, which for UTF-8 is code-point
      order, which is what Python's :func:`sorted` gives. Sorting under the
      database's default collation would make the digest depend on
      ``lc_collate``: the same market list would hash differently on two
      clusters, and a receipt written by one would look like new work to the
      other;
    - ``chr(10)`` as the separator — ``("a","bc")`` and ``("ab","c")`` are two
      market sets and must not share a digest. Written as ``chr(10)`` rather
      than an escaped literal so the string means the same thing in this file,
      in the trigger body and in a psql session;
    - ``convert_to(..., 'UTF8')`` — the digest is over bytes, and which bytes is
      not left to the server encoding.
    """
    return (
        "encode(sha256(convert_to(array_to_string(ARRAY("  # noqa: S608
        f'SELECT m FROM unnest({markets_expression}) AS m ORDER BY m COLLATE "C"'
        "), chr(10)), 'UTF8')), 'hex')"
    )


def _refuse(offenders_sql: str, message: str, hint: str) -> None:
    """Count, name and refuse — the guard shape §17.7 fixes for every revision.

    The apostrophes are doubled before the string reaches SQL, the way ``0017``
    does it: a hint that reads naturally in English is a hint with a quote in it
    sooner or later, and the failure mode is a syntax error inside a ``DO``
    block that nobody can read.
    """
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM ({offenders_sql}) AS offending; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {message.replace(chr(39), chr(39) * 2)}', "
        f"HINT = '{hint.replace(chr(39), chr(39) * 2)}'; END IF; END $$;"
    )


_UNNAMED_MARKET_SQL = (
    f"SELECT 1 FROM {TABLE} WHERE array_position({MARKETS_COLUMN}, NULL::text) IS NOT NULL"  # noqa: S608
)
_UNNAMED_MARKET_MESSAGE = (
    "replay_runs rows carry a NULL member in markets - the digest is built by joining the "
    "sorted keys, and a NULL member is dropped by that join, so two different slices would "
    "hash to the same value and collide on the very key this revision widens"
)
_UNNAMED_MARKET_HINT = (
    "export those rows (COPY (SELECT * FROM replay_runs WHERE array_position(markets, "
    "NULL::text) IS NOT NULL) TO ...) and decide which market the NULL was: no column that "
    "remains can say, so the migration will not guess"
)


def refuse_an_upgrade_over_an_unnamed_market() -> None:
    """The one thing the digest cannot be honest about, refused before it exists.

    ``array_to_string`` drops a NULL member, so ``{a, NULL}`` and ``{a}`` would
    share a digest — an ambiguity inside a UNIQUE key. The CHECK installed by
    :func:`add_digest_column` makes that unrepresentable from here on; this
    guard is what stands in front of it, counting the offenders and naming the
    export instead of dying inside the ``ALTER TABLE`` with a constraint
    violation that names no way out (the ``0016`` argument, §28.3). Only the
    replay CLI writes this table and it builds every key as
    ``f"{exchange}:{symbol}"``, so on every database today it counts zero.
    """
    _refuse(_UNNAMED_MARKET_SQL, _UNNAMED_MARKET_MESSAGE, _UNNAMED_MARKET_HINT)


def add_digest_column() -> None:
    """Add it nullable, derive every stored row, then make it ``NOT NULL``.

    In that order because it is the only honest one: a ``DEFAULT`` would have to
    invent a digest for markets it cannot see, and a nullable column left
    nullable would let a future writer skip the key. The backfill reads
    ``markets``, which ``0013`` has stored ``NOT NULL`` since day one — this is
    derivation of what the row already says, never a sentinel.
    """
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN {DIGEST_COLUMN} text")
    op.execute(
        f"UPDATE {TABLE} SET {DIGEST_COLUMN} = {digest_sql(MARKETS_COLUMN)} "  # noqa: S608
        f"WHERE {DIGEST_COLUMN} IS NULL"
    )
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN {DIGEST_COLUMN} SET NOT NULL")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {CK_DIGEST_SHAPE} "
        f"CHECK ({DIGEST_COLUMN} ~ '{MARKETS_DIGEST_PATTERN_0018}')"
    )
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {CK_MARKETS_NAMED} "
        f"CHECK (array_position({MARKETS_COLUMN}, NULL::text) IS NULL)"
    )


def drop_digest_column() -> None:
    """``DROP COLUMN`` takes ``ck_replay_runs_markets_digest_is_a_sha256`` with
    it; the CHECK on ``markets`` is on another column and has to be named."""
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CK_MARKETS_NAMED}")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {DIGEST_COLUMN}")


def install_digest_trigger() -> None:
    """Derive the digest when it is absent; refuse it when it disagrees.

    The precedent is ``portfolio_currency_anchor_matches_observation`` (§18.2):
    a copy that can disagree with its source is worse than no copy. Filling in a
    ``NULL`` is not the same as overwriting a value — it is the ``0002``
    backfill boundary applied per row, and it is what keeps every writer that
    predates this revision (the API's own test fixtures, an operator's ``INSERT``)
    correct instead of broken.
    """
    op.execute(f"""
CREATE FUNCTION {DIGEST_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    DECLARE computed text;
    BEGIN
        computed := {digest_sql(f"NEW.{MARKETS_COLUMN}")};
        IF NEW.{DIGEST_COLUMN} IS NULL THEN
            NEW.{DIGEST_COLUMN} := computed;
        ELSIF NEW.{DIGEST_COLUMN} <> computed THEN
            RAISE EXCEPTION USING
                MESSAGE = 'replay_runs.{DIGEST_COLUMN} does not name its own markets: '
                    || NEW.{DIGEST_COLUMN} || ' was written, ' || computed
                    || ' is the digest of ' || array_to_string(NEW.{MARKETS_COLUMN}, ', '),
                HINT = 'the digest is derived, never chosen: leave it NULL and the database '
                    || 'computes it, or send hunter_core.domain.digests.markets_digest(markets)';
        END IF;
        RETURN NEW;
    END;
$$
""")
    op.execute(
        f"CREATE TRIGGER {DIGEST_TRIGGER} BEFORE INSERT OR UPDATE ON {TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {DIGEST_FUNCTION}()"
    )


def drop_digest_trigger() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {DIGEST_TRIGGER} ON {TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {DIGEST_FUNCTION}()")


def replace_slice_key() -> None:
    """Swap ``uq_replay_runs_slice`` for the four-column key, same name.

    ``ACCESS EXCLUSIVE`` on ``replay_runs`` for the duration of one index build
    over a table of tens of rows per day and no retention — the same order of
    magnitude as the window ``0012`` opens (§24.7), not a new class of risk. The
    table has one writer, the replay CLI, and it is not running during a deploy.
    """
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {UNIQUE_NAME}")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {UNIQUE_NAME} UNIQUE ({', '.join(SLICE_KEY_0018)})"
    )


def restore_slice_key() -> None:
    """The ``0013`` key, put back only after :func:`refuse_a_downgrade_that_would_merge_two_slices`."""
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {UNIQUE_NAME}")
    op.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {UNIQUE_NAME} UNIQUE ({', '.join(SLICE_KEY_0013)})"
    )


_COLLISION_SQL = f"SELECT 1 FROM {TABLE} GROUP BY {', '.join(SLICE_KEY_0013)} HAVING count(*) > 1"  # noqa: S608
_COLLISION_MESSAGE = (
    "windows in replay_runs hold more than one market slice - restoring the 0013 key would "
    "fail on them, and the only way to satisfy it is to delete receipts of replays that "
    "really ran, which is the evidence 0013 exists to keep"
)
_COLLISION_HINT = (
    "export them first (COPY (SELECT * FROM replay_runs r WHERE EXISTS (SELECT 1 FROM "
    "replay_runs o WHERE o.run_id = r.run_id AND o.window_from = r.window_from AND "
    "o.window_to = r.window_to AND o.id <> r.id)) TO ...) and decide which slice of each "
    "window is the one that survives; the migration will not choose"
)


def refuse_a_downgrade_that_would_merge_two_slices() -> None:
    """§17.7 again: reversing is allowed, losing evidence is not.

    The ``0013`` key is *narrower*, so restoring it over a database that has
    already recorded more than one market slice per window is not reversible at
    all — Postgres would refuse the constraint, and the only way to satisfy it
    would be to delete receipts of replays that really ran. The guard counts the
    offending windows and refuses first, naming the export, rather than dying
    inside ``ADD CONSTRAINT`` with a message that names no way out (§28.3).

    Dropping the *column* loses nothing and is not guarded: the digest is
    derived from ``markets``, which stays, so ``0018`` can be re-applied and
    every value comes back byte for byte. That is the difference between this
    guard and ``0013``'s — one protects a receipt, the other protects nothing.
    """
    _refuse(_COLLISION_SQL, _COLLISION_MESSAGE, _COLLISION_HINT)
