"""The DDL ``0003_analysis`` owns beyond ``op.create_table`` — DATABASE.md §17.

Same split as :mod:`ddl.shadow`: the revision file stays readable and the frozen
lists have one home. Five things live here.

**Immutability of ``feature_baselines``.** A baseline is evidence, not a cache.
The joint M2 decision requires that recomputing baselines tomorrow reproduce
today's score exactly, which is only true if a revision is written once and
never edited — so the trigger refuses every ``UPDATE``, for every role,
including the owner. ``DELETE`` is *not* refused outright, because retention has
to be able to expire revisions once nothing depends on them; it is refused
unless the caller declares itself with
``SET LOCAL app.baseline_retention = 'on'``. That marker is transaction-scoped,
which is what makes it safe behind the transaction pooler (the same mechanism
``app.current_org`` uses), and it means a bug in the scanner cannot delete the
evidence its own scores point at — deletion has to be an act, not an accident.

**Grants for the two new tables.** ``ddl.tables``' four classes are frozen as of
``0001`` and ``ddl.shadow``'s as of ``0002``; these are this revision's addition,
and ``test_schema_privileges.py`` unions all three so every table stays
classified exactly once. ``feature_baselines`` gets its own class:
``SELECT``/``INSERT``/``DELETE`` for the worker and **no ``UPDATE`` for anyone**,
so the trigger is the second lock on a door the grants already closed.

**Guards for a populated database.** Three new invariants (the expiry
biconditional, one open episode per market, one active anomaly per market and
type) cannot be derived for rows that already violate them. Following ``0002``'s
precedent, the migration counts the offenders and refuses with instructions
rather than guessing a backfill — inventing an ``expired_at`` would fabricate the
one timestamp the whole episode model is keyed on. On every consistent database
these are no-ops.

**Reversing ``ALTER TYPE ... ADD VALUE``.** Postgres cannot drop an enum label,
so the downgrade renames the type, rebuilds it from the labels ``0001`` froze,
retypes every column that uses it and drops the old type. It refuses first if any
row — including a history sample under an already-EXPIRED episode — still carries
a label that is about to disappear.

**Guards for the downgrade itself.** Reversing a schema is allowed; losing data
is not, and "the migration reversed cleanly" is exactly how that loss would be
reported. So the downgrade also refuses while an ``outbox_events`` row is still
pending (a publication the system owes, which dropping the table would erase
without a trace) or while a preserved sample still names a ``feature_baselines``
revision in its envelope (a score that would survive pointing at an explanation
that no longer exists).
"""

from __future__ import annotations

from collections.abc import Mapping

from alembic import op

from ddl.enums import ANALYSIS_ADDED_VALUES, INITIAL_ENUMS
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

ANALYSIS_APP_READ_ONLY_TABLES: tuple[str, ...] = ("feature_baselines", "outbox_events")
"""``SELECT`` for ``hunter_app``, like every other global/system table.

The API reads baselines to explain a score and reads the outbox to report queue
depth on ``/system``; the workers are the only writers (DATABASE.md §15.6 keeps
the API's write exception list empty on purpose).
"""

ANALYSIS_WORKER_WRITE_TABLES: tuple[str, ...] = ("outbox_events",)
"""``INSERT``/``UPDATE``/``DELETE`` for ``hunter_worker``.

The outbox is genuinely mutable: the dispatcher stamps ``dispatched_at``, counts
``attempts`` and records ``last_error``, and prunes what it has delivered.
"""

ANALYSIS_WORKER_APPEND_TABLES: tuple[str, ...] = ("feature_baselines",)
"""``SELECT``/``INSERT``/``DELETE`` for ``hunter_worker`` — and never ``UPDATE``.

A fifth grant class, and the reason it exists is the whole point of the table: a
baseline revision may be created and, once nothing depends on it, expired, but
it may never be *changed*. This is not the append-only class of
:data:`ddl.tables.APPEND_ONLY_TABLES` (which also forbids ``DELETE``, because an
audit trail is never pruned) — baselines are pruned, on the same schedule as the
samples that depend on them.
"""

ANALYSIS_SEQUENCES: tuple[str, ...] = ("outbox_events_id_seq",)
"""``outbox_events.id`` is ``BIGSERIAL``: without ``USAGE`` on its sequence the
worker's ``INSERT`` fails with "permission denied for sequence", which no table
grant would have revealed (the lesson ``shadow_outbox`` paid for in ``0002``)."""

IMMUTABLE_FUNCTION = "feature_baselines_immutable"
IMMUTABLE_TRIGGER = "feature_baselines_immutable"
RETENTION_SETTING = "app.baseline_retention"
"""``SET LOCAL app.baseline_retention = 'on'`` — the retention job's declaration.

Transaction-scoped, so it cannot leak to the next transaction on a pooled
connection, and read with ``current_setting(..., true)`` plus ``NULLIF`` for the
same reason the RLS policies do (DATABASE.md §15.4): behind the pooler a GUC
that has ever been set comes back as an empty string rather than NULL.
"""

_ENUM_COLUMNS: Mapping[str, tuple[tuple[str, str, str | None], ...]] = {
    "opportunity_status": (
        ("opportunities", "status", "NORMAL"),
        ("opportunity_history", "status", None),
    ),
    "anomaly_type": (("anomalies", "type", None),),
    "market_regime": (("market_regimes", "regime", None),),
}
"""``type -> ((table, column, server default or None), ...)``.

Every column that would have to be retyped to reverse an ``ADD VALUE``.
``opportunity_history`` is partitioned; ``ALTER TABLE ... ALTER COLUMN TYPE``
without ``ONLY`` recurses into its partitions, which is exactly what is wanted —
and is why the new index and CHECK are dropped *before* this runs, so no
expression is still bound to the type being replaced.
"""


def _added_labels(type_name: str) -> tuple[str, ...]:
    return tuple(label for name, label, _before in ANALYSIS_ADDED_VALUES if name == type_name)


def create_feature_baseline_immutability() -> None:
    """Refuse every ``UPDATE``, and every ``DELETE`` outside the retention job."""
    op.execute(f"""
CREATE FUNCTION {IMMUTABLE_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'feature_baselines ' || OLD.id
                    || ' is immutable: a baseline revision is never updated',
                HINT = 'insert a new revision with a later available_at; every score '
                    || 'records the baseline ids it used, so editing one rewrites the past';
        END IF;
        IF NULLIF(current_setting('{RETENTION_SETTING}', true), '') IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'feature_baselines ' || OLD.id
                    || ' may only be deleted by the retention job',
                HINT = 'the job declares itself with SET LOCAL {RETENTION_SETTING} = ''on'' '
                    || 'after proving no preserved sample still depends on the revision';
        END IF;
        RETURN OLD;
    END;
$$
""")
    op.execute(
        f"CREATE TRIGGER {IMMUTABLE_TRIGGER} BEFORE UPDATE OR DELETE ON feature_baselines "
        f"FOR EACH ROW EXECUTE FUNCTION {IMMUTABLE_FUNCTION}()"
    )


def drop_feature_baseline_immutability() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {IMMUTABLE_TRIGGER} ON feature_baselines")
    op.execute(f"DROP FUNCTION IF EXISTS {IMMUTABLE_FUNCTION}()")


def _refuse(count_sql: str, message: str, hint: str) -> None:
    """``RAISE EXCEPTION`` when ``count_sql`` finds anything, naming how many.

    ``USING MESSAGE`` rather than a ``%`` format string, for the reason
    ``ddl.shadow`` records: the placeholders of ``RAISE EXCEPTION 'x %', y`` have
    to survive SQLAlchemy's own percent handling on the way to the server, and a
    mangled error message is the thing nobody notices until it matters.
    """
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM ({count_sql}) AS offending; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {message}', "
        f"HINT = '{hint}'; END IF; END $$;"
    )


def refuse_rows_the_new_invariants_cannot_describe() -> None:
    """Stop the upgrade on data no derivation could honestly repair.

    ``0002`` set the precedent and the boundary: backfill what already-present
    columns *imply*, refuse what they merely suggest. All three of these are the
    second kind. On a database where the M2 scanner has never run — which is
    every database today — each one counts zero.
    """
    _refuse(
        "SELECT 1 FROM opportunities WHERE (status = 'EXPIRED') <> (expired_at IS NOT NULL)",
        "opportunities rows disagree with themselves about being expired "
        "(status = ''EXPIRED'' without expired_at, or the reverse); 0003_analysis "
        "will not invent the timestamp an episode expired at",
        "set expired_at to the real expiry for each EXPIRED row, or clear the "
        "status of the ones that never expired, and re-run the migration",
    )
    _refuse(
        "SELECT market_id FROM opportunities WHERE expired_at IS NULL "
        "GROUP BY market_id HAVING count(*) > 1",
        "markets carry more than one open opportunity; 0003_analysis makes an "
        "episode unique per market WHERE expired_at IS NULL and cannot choose "
        "which of them is the episode",
        "expire the superseded rows (status = ''EXPIRED'' with expired_at) and "
        "re-run the migration",
    )
    _refuse(
        "SELECT market_id, type FROM anomalies WHERE status = 'active' "
        "GROUP BY market_id, type HAVING count(*) > 1",
        "(market, anomaly type) pairs have more than one active anomaly; "
        "0003_analysis makes that pair unique while active",
        "resolve or expire the duplicates, keeping the one the detector is "
        "actually maintaining, and re-run the migration",
    )


_BASELINE_REFERENCES = (
    "SELECT 1 FROM opportunities WHERE "
    "jsonb_typeof(feature_snapshot -> 'baseline_ids') = 'array' "
    "AND jsonb_array_length(feature_snapshot -> 'baseline_ids') > 0 "
    "UNION ALL "
    "SELECT 1 FROM opportunity_history WHERE "
    "jsonb_typeof(envelope -> 'baseline_ids') = 'array' "
    "AND jsonb_array_length(envelope -> 'baseline_ids') > 0"
)
"""Preserved samples that name a baseline revision, in either envelope.

``jsonb_typeof`` first because ``jsonb_array_length`` raises on a non-array, and
a guard that errors on malformed data instead of reporting it is worse than no
guard.
"""


def refuse_a_downgrade_that_would_discard_durable_state() -> None:
    """Reversing a schema is allowed; losing evidence and obligations is not.

    The label guard below protects *meaning*; this protects *data*, and the two
    are different failures. Both scenarios are Astra's:

    - an ``outbox_events`` row with ``dispatched_at IS NULL`` is a publication the
      system still owes. Dropping the table succeeds, the deploy looks clean, and
      the event is simply never emitted — the exact loss the outbox exists to make
      impossible;
    - an opportunity whose envelope names a ``feature_baselines`` revision keeps
      its score and loses the evidence behind it. The row survives saying "this is
      why", pointing at nothing.

    Baselines that no preserved sample references are *not* guarded: they are
    recomputable from the feature snapshots, and refusing on them would make the
    downgrade impossible on any database the scanner has ever touched. That is
    accepted, recoverable loss, and it is written down here rather than
    discovered later.
    """
    _refuse(
        "SELECT 1 FROM outbox_events WHERE dispatched_at IS NULL",
        "outbox_events rows are still pending; dropping the table would discard "
        "publications the system owes, with no way to know they existed",
        "let the dispatcher drain the queue (dispatched_at IS NULL empties), then downgrade",
    )
    _refuse(
        _BASELINE_REFERENCES,
        "preserved samples name a feature_baselines revision in their envelope; "
        "dropping the table would leave those scores claiming an explanation that "
        "no longer exists",
        "export the referenced revisions, or expire the samples that depend on "
        "them, before downgrading",
    )


def refuse_rows_using_values_0003_added() -> None:
    """The downgrade's guard: no label may vanish under a row that uses it.

    Postgres has no ``ALTER TYPE ... DROP VALUE``, so reversing an ``ADD VALUE``
    means rebuilding the type — and a ``USING`` cast of a row that still says
    ``EXTENDED`` would fail deep inside the rebuild with "invalid input value for
    enum". Failing here instead says which rows and what to do. Note that
    ``opportunity_history`` is checked too: an episode that is EXPIRED today can
    still hold an EXTENDED sample from yesterday.
    """
    for type_name, columns in _ENUM_COLUMNS.items():
        labels = ", ".join(f"'{label}'" for label in _added_labels(type_name))
        selects = " UNION ALL ".join(
            # S608: every interpolated value is a constant of this module —
            # table and column come from ``_ENUM_COLUMNS``, the labels from
            # ``ANALYSIS_ADDED_VALUES``. Nothing from outside reaches it.
            f"SELECT 1 FROM {table} WHERE {column}::text IN ({labels})"  # noqa: S608
            for table, column, _default in columns
        )
        _refuse(
            selects,
            f"rows still use a {type_name} label that only 0003_analysis defines "
            f"({labels.replace(chr(39), chr(39) * 2)}); downgrading would delete the "
            f"meaning of those rows",
            "rewrite those rows to a label the previous revision defines, then downgrade",
        )


def restore_frozen_enum_labels() -> None:
    """Rebuild each altered type with the labels ``0001`` froze.

    Rename, recreate, retype every column, drop the old type. Defaults are
    dropped and restored around the retype because a default is stored already
    coerced to the old type and would block it.
    """
    for type_name, columns in _ENUM_COLUMNS.items():
        previous = f"{type_name}__pre0003"
        rendered = ", ".join(f"'{label}'" for label in INITIAL_ENUMS[type_name])
        op.execute(f"ALTER TYPE {type_name} RENAME TO {previous}")
        op.execute(f"CREATE TYPE {type_name} AS ENUM ({rendered})")
        for table, column, default in columns:
            if default is not None:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_name} "
                f"USING {column}::text::{type_name}"
            )
            if default is not None:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
        op.execute(f"DROP TYPE {previous}")


def grant_analysis_privileges() -> None:
    """Read for the API, write for the worker — and never ``UPDATE`` on a baseline."""
    for table in ANALYSIS_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in ANALYSIS_WORKER_WRITE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {WORKER_ROLE}")
    for table in ANALYSIS_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT, DELETE ON {table} TO {WORKER_ROLE}")
    for sequence in ANALYSIS_SEQUENCES:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {WORKER_ROLE}")


def revoke_analysis_privileges() -> None:
    for sequence in ANALYSIS_SEQUENCES:
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM {WORKER_ROLE}")
    for table in (
        *ANALYSIS_APP_READ_ONLY_TABLES,
        *ANALYSIS_WORKER_WRITE_TABLES,
        *ANALYSIS_WORKER_APPEND_TABLES,
    ):
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}, {WORKER_ROLE}")
