"""The security surface of ``0001``, in one import — DATABASE.md §1.2.

Split across three modules so each stays readable, and re-exported here so the
revision (and the tests that assert against the frozen lists) has a single name
to reach for:

- :mod:`ddl.tables` — the frozen catalogue: which table is in which grant class,
  which tables carry ``organization_id``, which carry RLS without it;
- :mod:`ddl.grants` — the per-table ``GRANT``s and the default privileges;
- :mod:`ddl.policies` — the RLS policies.

The two roles are ``NOLOGIN``: a deployment grants them to the concrete login
role of its environment. ``hunter_worker`` gets ``BYPASSRLS`` because strategy,
execution and analytics scan every organization; the ``ALTER ROLE`` tolerates
insufficient privilege so the migration still applies on a managed Postgres
where the migrating role cannot grant that attribute — it raises a notice asking
for the one manual step instead of failing the deploy.
"""

from __future__ import annotations

from alembic import op

from ddl.grants import grant_privileges, revoke_privileges
from ddl.policies import disable_row_level_security, enable_row_level_security
from ddl.tables import (
    ALL_TABLES,
    APP_READ_ONLY_TABLES,
    APP_WRITE_TABLES,
    APPEND_ONLY_TABLES,
    SELF_SCOPED_TABLES,
    TENANT_TABLES,
    WORKER_WRITE_TABLES,
)
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

__all__ = [
    "ALL_TABLES",
    "APPEND_ONLY_TABLES",
    "APP_READ_ONLY_TABLES",
    "APP_ROLE",
    "APP_WRITE_TABLES",
    "SELF_SCOPED_TABLES",
    "TENANT_TABLES",
    "WORKER_ROLE",
    "WORKER_WRITE_TABLES",
    "create_roles",
    "disable_row_level_security",
    "enable_row_level_security",
    "grant_privileges",
    "revoke_privileges",
]


def create_roles() -> None:
    """Create both roles if they do not already exist.

    Postgres has no ``CREATE ROLE IF NOT EXISTS``; roles are cluster-wide, so
    another database in the same cluster may already have created them. The
    ``duplicate_object`` handler makes this idempotent without querying
    ``pg_roles``, and ``insufficient_privilege`` is tolerated for the managed
    case where the migrating role may not create roles at all.
    """
    for role in (APP_ROLE, WORKER_ROLE):
        op.execute(
            f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; "
            f"EXCEPTION WHEN duplicate_object THEN "
            f"RAISE NOTICE 'role {role} already exists'; "
            f"WHEN insufficient_privilege THEN "
            f"RAISE NOTICE 'cannot create role {role}; create it with a superuser role'; "
            f"END $$;"
        )
    op.execute(
        f"DO $$ BEGIN ALTER ROLE {WORKER_ROLE} BYPASSRLS; "
        f"EXCEPTION WHEN insufficient_privilege THEN "
        f"RAISE NOTICE 'could not set BYPASSRLS on {WORKER_ROLE}; "
        f"grant it manually with a superuser role'; END $$;"
    )
