"""``0010_strategy_purpose`` — the wallet a signal may reach, named on the version.

T3.15/D10 (``.claude/state/decisions-delegated-2026-09-07.md``): the producer
only ever wrote ``research_only`` (``record.py:198,229``, cravado) and the two
consumers only ever accepted ``live``. Between the two, exactly one label was
missing — ``paper`` — and it is not a row-level choice, it is a column. One
column, one CHECK, and the same freeze technique ``0002_shadow_lab``
(:mod:`ddl.shadow`) built for ``code_ref``: this revision does not invent a
second mechanism, it widens the one that already exists.

**The trigger is replaced, not duplicated.** ``ddl.shadow`` is frozen as of its
own revision (its module docstring: "every list here is frozen") — a later
addition there would silently redefine what ``0002`` installed, the same trap
§16.5/§17.1 of DATABASE.md exist to avoid. So, exactly like ``0009_paper_geometry``
replaced ``0007``'s request-guard *body* (:mod:`ddl.paper_geometry`), this module
copies ``ddl.shadow``'s frozen column list, adds ``purpose``, and drops +
recreates the same two triggers against the same function name. The downgrade
goes the other way and calls ``ddl.shadow``'s own creator back: reverting to
``0009`` means having the trigger ``0002`` describes.

**Grants: read for both roles, write for nobody but the activation script.**
``strategy_versions`` was classified in ``0001`` (``ddl.tables.APP_READ_ONLY_TABLES``
and ``ddl.tables.WORKER_WRITE_TABLES``) — the API reads it and the table-level
grant nominally lets ``hunter_worker`` write it, a privilege the worker's own
code never exercises: every row this schema has ever had, activated or draft,
was written through ``DATABASE_URL_MIGRATIONS`` (the migration/owner connection
``infra/scripts/seed.py`` and ``infra/scripts/activate_strategy_version.py`` use),
never through the application roles. ``purpose`` decides which wallet, if any, a
signal may reach, so it does not inherit that latent grant by accident.

**Measured, not assumed: a column-level ``REVOKE`` cannot narrow a table-level
``GRANT``.** Postgres checks column access as the *union* of the table ACL and
the column ACL — a column grant only ever *widens* what a narrower table grant
allows (exactly what ``0007_paper_roles`` used it for: ``portfolio_risk_state``
had no table-level ``UPDATE``, and a column grant added just ``updated_at``).
Revoking ``UPDATE (purpose)`` from a role that already holds table-level
``UPDATE`` — which ``hunter_worker`` does, since ``0001`` — is a no-op, proven
against a real Postgres 16 before this line was written the other way. So this
revision does what actually narrows: it revokes ``hunter_worker``'s table-level
``INSERT``/``UPDATE`` on ``strategy_versions`` outright and re-grants both, at
the column level, for every column *except* ``purpose`` — restoring exactly the
privilege ``0001`` gave everywhere else, and refusing it only where the wallet
label lives. Omitting ``purpose`` from an ``INSERT``'s column list still uses
its ``DEFAULT`` without needing the privilege (Postgres: a default only needs
the privilege when the caller *names* the column), so nothing that relies on
the default breaks. ``hunter_app`` already has no INSERT/UPDATE on this table at
all (read-only since ``0001``), so there is nothing to narrow on that side.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import WORKER_ROLE

PURPOSE_COLUMN = "purpose"
PURPOSE_CHECK = "ck_strategy_versions_purpose_is_a_known_label"
PURPOSE_VALUES: tuple[str, ...] = ("research_only", "paper", "live")
"""``hunter_core.strategies.envelope.PURPOSE_RESEARCH_ONLY`` /
``PURPOSE_PAPER`` and ``hunter_core.admission.sources.PURPOSE_LIVE`` — spelled
out here rather than imported, for the same reason every CHECK in this package
writes its allow-list out (``ddl/paper_geometry.py``'s module docstring): the
database's contract must not silently follow a later edit to the Python
constants.
"""
PURPOSE_DEFAULT = "research_only"

_FROZEN_COLUMNS_0010: tuple[str, ...] = (
    "strategy_id",
    "version",
    "code_ref",
    "parameters_schema",
    "default_parameters",
    "params_format",
    "activated_at",
    "purpose",
)
"""``ddl.shadow._FROZEN_COLUMNS`` plus ``purpose`` — copied, not imported (see
the module docstring)."""

FREEZE_FUNCTION = "shadow_freeze_strategy_version"
UPDATE_TRIGGER = "strategy_versions_freeze_update"
DELETE_TRIGGER = "strategy_versions_freeze_delete"


def _freeze_function_sql() -> str:
    checks = "\n".join(
        f"        IF NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"changed := changed || '{column}'::text; END IF;"
        for column in _FROZEN_COLUMNS_0010
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
                HINT = 'create a new strategy_version; status, changelog and '
                    || 'deprecated_at stay mutable';
        END IF;
        RETURN NEW;
    END;
$$
"""


def add_purpose_column() -> None:
    """The column, its CHECK and its honest backfill.

    Every existing row is, and has only ever been, ``research_only`` — there is
    no upgrade guard here for the same reason ``0009`` needed none (§21.4):
    ``DEFAULT 'research_only'`` backfills what every row already honestly is.
    """
    allowed = ", ".join(f"'{value}'" for value in PURPOSE_VALUES)
    op.execute(
        f"ALTER TABLE strategy_versions ADD COLUMN {PURPOSE_COLUMN} text "
        f"NOT NULL DEFAULT '{PURPOSE_DEFAULT}'"
    )
    op.execute(
        "ALTER TABLE strategy_versions ADD CONSTRAINT "
        f"{PURPOSE_CHECK} CHECK ({PURPOSE_COLUMN} IN ({allowed}))"
    )


def drop_purpose_column() -> None:
    op.execute(f"ALTER TABLE strategy_versions DROP CONSTRAINT IF EXISTS {PURPOSE_CHECK}")
    op.execute(f"ALTER TABLE strategy_versions DROP COLUMN {PURPOSE_COLUMN}")


def replace_strategy_version_freeze() -> None:
    """Widen ``0002``'s freeze trigger to cover ``purpose`` — drop and recreate,
    never ``CREATE OR REPLACE``, so the function and the two triggers stay one
    object with one history (the same shape ``0008``'s audited-move guards used,
    §20.3)."""
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


def restore_shadow_freeze() -> None:
    """Downgrade: put ``0002``'s own trigger back, verbatim.

    Calls ``ddl.shadow``'s own drop/create rather than repeating their bodies —
    reverting to ``0009`` means having the trigger ``0002`` describes, the same
    principle ``0009``'s downgrade used for the request guard (§21.2)."""
    from ddl.shadow import create_strategy_version_freeze, drop_strategy_version_freeze

    drop_strategy_version_freeze()
    create_strategy_version_freeze()


WORKER_COLUMNS_EXCEPT_PURPOSE: tuple[str, ...] = (
    "id",
    "strategy_id",
    "version",
    "status",
    "parameters_schema",
    "default_parameters",
    "code_ref",
    "params_format",
    "changelog",
    "created_at",
    "activated_at",
    "deprecated_at",
)
"""Every ``strategy_versions`` column as of ``0009`` — frozen here, like every
other list in this package, rather than read from the ORM at migration time.
This is the *other* side of the narrowing: everything ``hunter_worker`` may
still write, unchanged from what ``0001`` granted."""


def revoke_purpose_write() -> None:
    """Only the activation script (the migration/owner connection) writes
    ``purpose``. A column-level ``REVOKE`` alone cannot do this — see the
    module docstring — so this takes the table-level grant back outright and
    re-grants every other column, restoring exactly what ``0001`` gave
    ``hunter_worker`` everywhere but here. ``hunter_app`` never had table-level
    INSERT/UPDATE on ``strategy_versions`` (read-only since ``0001``), so there
    is nothing to narrow on that side."""
    columns = ", ".join(WORKER_COLUMNS_EXCEPT_PURPOSE)
    op.execute(f"REVOKE INSERT, UPDATE ON strategy_versions FROM {WORKER_ROLE}")
    op.execute(
        f"GRANT INSERT ({columns}), UPDATE ({columns}) ON strategy_versions TO {WORKER_ROLE}"
    )


def restore_purpose_write() -> None:
    """Downgrade: back to the one table-level grant ``0001`` made."""
    columns = ", ".join(WORKER_COLUMNS_EXCEPT_PURPOSE)
    op.execute(
        f"REVOKE INSERT ({columns}), UPDATE ({columns}) ON strategy_versions FROM {WORKER_ROLE}"
    )
    op.execute(f"GRANT INSERT, UPDATE ON strategy_versions TO {WORKER_ROLE}")


_DOWNGRADE_GUARD_SQL = "SELECT 1 FROM strategy_versions WHERE purpose <> 'research_only'"
_DOWNGRADE_GUARD_MESSAGE = (
    "strategy_versions carry a purpose other than research_only - dropping the column "
    "erases the distinction between shadow evidence and a coorte that may reach the "
    "paper wallet, which is not derivable from any column that remains"
)
_DOWNGRADE_GUARD_HINT = (
    "export the affected strategy_versions ids before reversing, and understand what it "
    "costs: every non-research_only row becomes indistinguishable from shadow evidence"
)


def refuse_a_downgrade_that_would_lose_a_purpose() -> None:
    """§17.7: reversing is allowed, losing a distinction is not — same pattern
    as ``0009``'s two guards (:func:`ddl.paper_geometry.refuse_a_downgrade_that_would_lose_a_request_or_hide_dust`)."""
    safe_message = _DOWNGRADE_GUARD_MESSAGE.replace("'", "''")
    safe_hint = _DOWNGRADE_GUARD_HINT.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM ({_DOWNGRADE_GUARD_SQL}) AS offending; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
        f"HINT = '{safe_hint}'; END IF; END $$;"
    )
