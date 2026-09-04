"""Per-table grants for ``hunter_app`` and ``hunter_worker`` — DATABASE.md §1.2.

The first draft used ``GRANT ... ON ALL TABLES IN SCHEMA public`` and then
revoked what the append-only rule forbids. That is wrong twice over, and the
T04 cross-review proved both:

- ``ON ALL TABLES`` is evaluated once, over the tables that exist at that
  moment. The monthly partitions existed by then, so every ``audit_logs_YYYY_MM``
  received ``UPDATE``/``DELETE``, and the ``REVOKE`` on the *parent* did not
  reach them: Postgres checks a query naming a child against the child's own
  privileges. ``DELETE FROM audit_logs_2026_09`` was allowed for the API role.
- it grants full DML on everything, so ``hunter_app`` could rewrite the strategy
  catalogue, the plan entitlements and the feature flags — none of which any
  request handler writes.

So: every grant is named, table by table, from the frozen lists in
:mod:`ddl.tables`; partition children get nothing at all (see
``harden_partition_sql``, applied when each child is created); and
``ALTER DEFAULT PRIVILEGES`` states that a table added later inherits nothing
either, instead of relying on the next author to remember.
"""

from __future__ import annotations

from alembic import op

from ddl.tables import (
    ALL_TABLES,
    APP_READ_ONLY_TABLES,
    APP_WRITE_TABLES,
    APPEND_ONLY_TABLES,
    WORKER_WRITE_TABLES,
)
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

_ROLES = (APP_ROLE, WORKER_ROLE)
_FULL_DML = "SELECT, INSERT, UPDATE, DELETE"


def _default_privileges(action: str) -> None:
    """``GRANT``/``REVOKE`` nothing by default on anything created from here on."""
    roles = ", ".join(_ROLES)
    preposition = "TO" if action == "GRANT" else "FROM"
    for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"{action} ALL ON {kind} {preposition} {roles}"
        )


def grant_privileges() -> None:
    """Grant exactly what each role needs, one table at a time.

    Runs before ``create_initial_partitions()``: there is nothing here that
    depends on a partition existing, and the children are hardened at creation
    instead — so the ordering trap that produced the review finding cannot come
    back by someone moving a call.
    """
    for role in _ROLES:
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")

    # hunter_app — the API. Read the world, write only what a request owns.
    for table in APP_WRITE_TABLES:
        op.execute(f"GRANT {_FULL_DML} ON {table} TO {APP_ROLE}")
    for table in APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")

    # hunter_worker — the pipeline. Reads everything, writes its own surface.
    for table in ALL_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {WORKER_ROLE}")
    for table in WORKER_WRITE_TABLES:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {table} TO {WORKER_ROLE}")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"GRANT INSERT ON {table} TO {WORKER_ROLE}")

    _default_privileges("REVOKE")


def revoke_privileges() -> None:
    """Reverse :func:`grant_privileges`. The roles themselves survive a downgrade."""
    _default_privileges("REVOKE")
    for role in _ROLES:
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
