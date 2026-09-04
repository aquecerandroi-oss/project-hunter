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
:mod:`ddl.tables`, and partition children get nothing at all (see
``harden_partition_sql``, applied when each child is created).

**What keeps a table added later from inheriting anything is a test, not DDL.**
The first fix here also wrote ``ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE
ALL ON TABLES FROM hunter_app, hunter_worker``, which reads like a standing
guarantee and is in fact a no-op: default privileges for a role other than the
creating one start out empty, so revoking from them removes nothing, and the
statement does not survive as a rule that a future ``GRANT`` has to defeat. The
real guarantee is
``test_schema_privileges.test_the_grant_lists_cover_every_table_exactly_once``,
which compares the four frozen grant classes against the live ``pg_class`` and
fails on any table that is in none of them or in two — so a table added by a
later revision cannot reach production unclassified.
"""

from __future__ import annotations

from alembic import op

from ddl.tables import (
    ALL_TABLES,
    APP_NO_DELETE_TABLES,
    APP_READ_ONLY_TABLES,
    APP_WRITE_TABLES,
    APPEND_ONLY_TABLES,
    WORKER_DELETE_TABLES,
    WORKER_WRITE_TABLES,
)
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

_ROLES = (APP_ROLE, WORKER_ROLE)
_FULL_DML = "SELECT, INSERT, UPDATE, DELETE"


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
    for table in APP_NO_DELETE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
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
    # the one privilege the API is denied: removing a tenant or a person
    for table in WORKER_DELETE_TABLES:
        op.execute(f"GRANT DELETE ON {table} TO {WORKER_ROLE}")


def revoke_privileges() -> None:
    """Reverse :func:`grant_privileges`. The roles themselves survive a downgrade."""
    for role in _ROLES:
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
