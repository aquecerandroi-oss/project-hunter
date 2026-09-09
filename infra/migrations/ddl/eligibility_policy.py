"""``0017_eligibility_policy`` — the context a version is allowed to decide in.

T3.52: the hourly regime series (T3.43, ``market_regimes`` with
``scope = 'btc'`` and ``classifier_version = 'regime_hourly_v1'``) exists and
nothing reads it at decision time. Making a version refuse to decide outside the
regime it was built for is **not** a parameter: no ``parameters_schema`` frozen
by any activated version declares it, the strategy code in
``hunter_core.strategies`` never reads it, and adding it to
``default_parameters`` would make ``params_hash`` split experiments the code
cannot tell apart. It is a property of the *row*, like ``purpose`` (``0010``)
— so it is a column.

``eligibility_policy jsonb NULL``. ``NULL`` is the whole history: every version
that exists today decides in every regime, and that is honestly what ``NULL``
means here ("no policy"), not a missing value. No backfill, no upgrade guard —
the same assertion ``0010`` and ``0016`` make (DATABASE.md §22, §28.4).

**The trigger is replaced, not duplicated** — fourth time this technique is used
(``0009`` over ``0007``, ``0010`` over ``0002``, ``0012`` over ``0010``). Every
module in this package is frozen as of its own revision, so this one copies the
column list of the revision that installed the function **that is actually in
the database** — ``ddl.replication`` (``0012``) — adds ``eligibility_policy``,
and drops + recreates the same two triggers against the same function name. The
downgrade calls ``ddl.replication``'s own creator back: reverting to ``0016``
means having the trigger ``0012`` describes.

**Freezing it is the point.** A policy that could change after activation would
silently change what every already-measured cohort of that version meant: the
same ``strategy_version_id`` would name "decides in SIDEWAYS" for the signals of
Monday and "decides anywhere" for the signals of Tuesday, with nothing in the
ledger able to tell the two apart. Changing a gate is a new version, exactly
like changing a parameter (SHADOW-LAB.md §1).

**No ``GRANT`` here, and that is the interesting part.** ``0010`` revoked
``hunter_worker``'s table-level ``INSERT``/``UPDATE`` on ``strategy_versions``
and re-granted both **column by column**, naming the columns that existed then
(``WORKER_COLUMNS_EXCEPT_PURPOSE``). A column added afterwards is therefore
outside every grant this table has: only the owner connection
(``DATABASE_URL_MIGRATIONS``, which is what ``infra/scripts/derive_variant.py``
uses) can write it. That is the privilege this policy needs, and it costs no
DDL — it is the shape ``0010`` deliberately left behind.

**No index.** The column is never a predicate: it is read with the row it
belongs to, by ``hunter_strategy_worker.catalogue.load_version_roster``, which
already scans the handful of ``active`` versions. DATABASE.md §1 forbids JSONB
for "fields that will be filtered frequently"; this one is filtered never.

**Lock.** ``ADD COLUMN`` with no default and no rewrite takes ``ACCESS
EXCLUSIVE`` on ``strategy_versions`` for the duration of a catalogue update
(Postgres 11+ does not rewrite the table for a nullable column without a
default), over a table of a few dozen rows. The trigger swap takes the same
lock, for the same instant. No maintenance window.
"""

from __future__ import annotations

from alembic import op

POLICY_COLUMN = "eligibility_policy"

_FROZEN_COLUMNS_0017: tuple[str, ...] = (
    "strategy_id",
    "version",
    "code_ref",
    "parameters_schema",
    "default_parameters",
    "params_format",
    "activated_at",
    "purpose",
    "replication_parent_id",
    "replication_index",
    POLICY_COLUMN,
)
"""``ddl.replication._FROZEN_COLUMNS_0012`` — the list the *current* head
installs, not ``0010``'s — plus ``eligibility_policy``. Copied, not imported,
for the reason every module in this package gives: the database's contract must
not silently follow a later edit to another revision.

**Building on ``0012`` and not on ``0010`` is the whole of it.** ``0012`` had
already widened this same function to cover ``replication_parent_id`` and
``replication_index``; a revision that copied ``0010``'s list would *narrow* the
trigger back and let a sibling be re-pointed at another parent after activation,
silently re-attributing an experiment whose signals are already on record. The
first draft of this module did exactly that and
``test_0012_freezes_the_lineage_but_leaves_the_marker_writable`` caught it —
which is the reason that test exists.

``promising_at``/``promising_by`` stay out, for ``0012``'s own reason: they are
written *after* activation by definition."""

FREEZE_FUNCTION = "shadow_freeze_strategy_version"
UPDATE_TRIGGER = "strategy_versions_freeze_update"
DELETE_TRIGGER = "strategy_versions_freeze_delete"


def _freeze_function_sql() -> str:
    """``ddl.replication._freeze_function_sql`` over the wider list.

    The body is copied for the same reason the list is: this revision installs
    *this* function, and a later edit to another revision's module must not
    change what ``0017`` put in the database.
    """
    checks = "\n".join(
        f"        IF NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"changed := changed || '{column}'::text; END IF;"
        for column in _FROZEN_COLUMNS_0017
    )
    return f"""
CREATE FUNCTION {FREEZE_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    DECLARE changed text[] := ARRAY[]::text[];
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'strategy_versions ' || OLD.id
                    || ' is frozen after activation: an activated version cannot be deleted',
                HINT = 'deprecate it instead; shadow signals point at this row';
        END IF;
{checks}
        IF cardinality(changed) > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'strategy_versions ' || OLD.id
                    || ' is frozen after activation: ' || array_to_string(changed, ', ')
                    || ' cannot change',
                HINT = 'create a new strategy_version; status, changelog, '
                    || 'promising_at and deprecated_at stay mutable';
        END IF;
        RETURN NEW;
    END;
$$
"""


def add_policy_column() -> None:
    """The column. Nullable, no default, no backfill: ``NULL`` is what every
    existing row already honestly is — no gate."""
    op.execute(f"ALTER TABLE strategy_versions ADD COLUMN {POLICY_COLUMN} jsonb")


def drop_policy_column() -> None:
    op.execute(f"ALTER TABLE strategy_versions DROP COLUMN {POLICY_COLUMN}")


def replace_strategy_version_freeze() -> None:
    """Widen ``0012``'s freeze trigger to cover ``eligibility_policy`` — drop and
    recreate, never ``CREATE OR REPLACE``, so the function and the two triggers
    stay one object with one history (§20.3, §22.2)."""
    op.execute(f"DROP TRIGGER IF EXISTS {DELETE_TRIGGER} ON strategy_versions")
    op.execute(f"DROP TRIGGER IF EXISTS {UPDATE_TRIGGER} ON strategy_versions")
    op.execute(f"DROP FUNCTION IF EXISTS {FREEZE_FUNCTION}()")
    op.execute(_freeze_function_sql())
    op.execute(
        f"CREATE TRIGGER {UPDATE_TRIGGER} BEFORE UPDATE ON strategy_versions "
        f"FOR EACH ROW WHEN (OLD.activated_at IS NOT NULL) "
        f"EXECUTE FUNCTION {FREEZE_FUNCTION}()"
    )
    op.execute(
        f"CREATE TRIGGER {DELETE_TRIGGER} BEFORE DELETE ON strategy_versions "
        f"FOR EACH ROW WHEN (OLD.activated_at IS NOT NULL) "
        f"EXECUTE FUNCTION {FREEZE_FUNCTION}()"
    )


def restore_replication_freeze() -> None:
    """Downgrade: put ``0012``'s own trigger back by calling its own creator,
    the way ``0012``'s downgrade calls ``0010``'s and ``0010``'s calls
    ``0002``'s (§22.2, §24). Reverting to ``0016`` means having the trigger
    ``0012`` describes — the lineage columns still frozen, and no idea what an
    ``eligibility_policy`` is."""
    from ddl.replication import replace_strategy_version_freeze as restore

    restore()


_DOWNGRADE_GUARD_SQL = "SELECT 1 FROM strategy_versions WHERE eligibility_policy IS NOT NULL"
_DOWNGRADE_GUARD_MESSAGE = (
    "strategy_versions carry an eligibility_policy - dropping the column silently widens "
    "them back to deciding in every market regime, and which regime each one was built for "
    "is not derivable from any column that remains"
)
_DOWNGRADE_GUARD_HINT = (
    "export the affected strategy_versions ids and their eligibility_policy before "
    "reversing, and understand what it costs: a version that only decides in SIDEWAYS "
    "starts deciding everywhere, with no ledger entry saying so"
)


def refuse_a_downgrade_that_would_lose_a_policy() -> None:
    """§17.7: reversing is allowed, losing a distinction is not — the same guard
    ``0010`` and ``0016`` install for the distinction each of them creates."""
    safe_message = _DOWNGRADE_GUARD_MESSAGE.replace("'", "''")
    safe_hint = _DOWNGRADE_GUARD_HINT.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM ({_DOWNGRADE_GUARD_SQL}) AS offending; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
        f"HINT = '{safe_hint}'; END IF; END $$;"
    )
