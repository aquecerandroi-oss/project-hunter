"""The DDL ``0002_shadow_lab`` owns beyond ``op.create_table`` — SHADOW-LAB.md §1.

Two things Alembic's autogenerate cannot express, kept here for the same reason
:mod:`ddl.tables` and :mod:`ddl.policies` exist: the revision file stays
readable, and the frozen lists have one home.

**The freeze trigger.** A ``strategy_version`` is a scientific instrument: the
Shadow Lab's numbers only mean something if the version that produced them still
says what it said when it produced them. So the *first activation* freezes
everything that identifies or determines the experiment, in every status
(active, deprecated, reactivated), and un-activating it — ``SET activated_at =
NULL`` — is itself one of the frozen changes. ``status``, ``changelog`` and
``deprecated_at`` stay mutable, because those describe the version's lifecycle,
not its content. ``DELETE`` is refused for the same reason ``UPDATE`` is: an
activated row that can be deleted can be re-inserted with the same id and
different parameters, and every signal already pointing at it would silently
change meaning.

**Grants for the two new system tables.** ``ddl.tables``' four classes are frozen
as of ``0001``; these are this revision's addition to them, and
``test_schema_privileges.py`` unions the two so every table stays classified
exactly once.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

SHADOW_APP_READ_ONLY_TABLES: tuple[str, ...] = ("shadow_episodes", "shadow_outbox")
"""``SELECT`` for ``hunter_app``, like every other global/system table.

The Lab API reads shadow state; the strategy-worker is its **only** writer
(SHADOW-LAB.md §10), so nothing a request handler can reach may write here.
"""

SHADOW_WORKER_WRITE_TABLES: tuple[str, ...] = ("shadow_episodes", "shadow_outbox")
"""``INSERT``/``UPDATE``/``DELETE`` for ``hunter_worker``."""

SHADOW_SEQUENCES: tuple[str, ...] = ("shadow_outbox_id_seq",)
"""``shadow_outbox.id`` is ``BIGSERIAL``: without ``USAGE`` on its sequence the
worker's ``INSERT`` fails with "permission denied for sequence", which no table
grant would have revealed. It is the first sequence in the schema — every other
primary key is an application-generated UUID v7."""

_FROZEN_COLUMNS: tuple[str, ...] = (
    "strategy_id",
    "version",
    "code_ref",
    "parameters_schema",
    "default_parameters",
    "params_format",
    "activated_at",
)
"""Everything the first activation freezes (SHADOW-LAB.md §1)."""

FREEZE_FUNCTION = "shadow_freeze_strategy_version"
UPDATE_TRIGGER = "strategy_versions_freeze_update"
DELETE_TRIGGER = "strategy_versions_freeze_delete"


def _freeze_function_sql() -> str:
    checks = "\n".join(
        f"        IF NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"changed := changed || '{column}'::text; END IF;"
        for column in _FROZEN_COLUMNS
    )
    # ``RAISE ... USING MESSAGE`` instead of a format string on purpose: the
    # ``%`` placeholders of ``RAISE EXCEPTION 'x %', y`` would have to survive
    # SQLAlchemy's percent handling on their way to the server, and a mangled
    # error message is exactly the thing nobody notices until the day it matters.
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


def create_strategy_version_freeze() -> None:
    """Freeze activated strategy versions against ``UPDATE`` and ``DELETE``."""
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


def drop_strategy_version_freeze() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {DELETE_TRIGGER} ON strategy_versions")
    op.execute(f"DROP TRIGGER IF EXISTS {UPDATE_TRIGGER} ON strategy_versions")
    op.execute(f"DROP FUNCTION IF EXISTS {FREEZE_FUNCTION}()")


def grant_shadow_privileges() -> None:
    """Read for the API, write for the worker — and nothing on the sequence for the API."""
    for table in SHADOW_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in SHADOW_WORKER_WRITE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {WORKER_ROLE}")
    for sequence in SHADOW_SEQUENCES:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {WORKER_ROLE}")


def revoke_shadow_privileges() -> None:
    for sequence in SHADOW_SEQUENCES:
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM {WORKER_ROLE}")
    for table in {*SHADOW_APP_READ_ONLY_TABLES, *SHADOW_WORKER_WRITE_TABLES}:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}, {WORKER_ROLE}")
