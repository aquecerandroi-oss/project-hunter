"""The security surface of ``0001``, in one import — DATABASE.md §1.2.

Split across three modules so each stays readable, and re-exported here so the
revision (and the tests that assert against the frozen lists) has a single name
to reach for:

- :mod:`ddl.tables` — the frozen catalogue: which table is in which grant class,
  which tables carry ``organization_id``, which carry RLS without it;
- :mod:`ddl.grants` — the per-table ``GRANT``s;
- :mod:`ddl.policies` — the RLS policies.

The two roles are ``NOLOGIN``: a deployment grants them to the concrete login
role of its environment. Both **must exist** when this revision finishes:
:func:`create_roles` tries to create them, tolerates not being allowed to, and
then checks ``pg_roles`` and fails the migration with the exact statements to run
by hand if either is missing. Only the ``BYPASSRLS`` attribute on
``hunter_worker`` — which strategy, execution and analytics need because they
scan every organization — degrades to a notice, because a schema that is
otherwise complete is still usable while an operator grants it.
"""

from __future__ import annotations

from alembic import op

from ddl.grants import grant_privileges, revoke_privileges
from ddl.policies import disable_row_level_security, enable_row_level_security
from ddl.tables import (
    ALL_TABLES,
    APP_NO_DELETE_TABLES,
    APP_READ_ONLY_TABLES,
    APP_WRITE_TABLES,
    APPEND_ONLY_TABLES,
    SELF_SCOPED_TABLES,
    TENANT_TABLES,
    WORKER_DELETE_TABLES,
    WORKER_WRITE_TABLES,
)
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

__all__ = [
    "ALL_TABLES",
    "APPEND_ONLY_TABLES",
    "APP_NO_DELETE_TABLES",
    "APP_READ_ONLY_TABLES",
    "APP_ROLE",
    "APP_WRITE_TABLES",
    "SELF_SCOPED_TABLES",
    "TENANT_TABLES",
    "WORKER_DELETE_TABLES",
    "WORKER_ROLE",
    "WORKER_WRITE_TABLES",
    "create_roles",
    "disable_row_level_security",
    "enable_row_level_security",
    "grant_privileges",
    "revoke_privileges",
]


_MANUAL_STEP = f"CREATE ROLE {APP_ROLE} NOLOGIN; CREATE ROLE {WORKER_ROLE} NOLOGIN BYPASSRLS;"


def create_roles() -> None:
    """Create both roles if they do not already exist, then prove that they do.

    Postgres has no ``CREATE ROLE IF NOT EXISTS``; roles are cluster-wide, so
    another database in the same cluster may already have created them. The
    ``duplicate_object`` handler makes the attempt idempotent, and
    ``insufficient_privilege`` is tolerated because on a managed Postgres the
    migrating role often may not create roles at all.

    Tolerating it *silently* was the bug the re-review found. Every ``GRANT`` and
    every ``TO CURRENT_USER`` policy after this point names these roles, so
    without them the migration fails a hundred statements later with
    ``role "hunter_app" does not exist`` — or, worse, someone reads the ``NOTICE``
    as a warning, and the schema is deployed with no application role and the API
    connecting as the owner, bypassing every grant the rest of this module
    writes. So the notice stands (it is what the operator needs to see), and then
    ``pg_roles`` is checked: if either role is genuinely absent the migration
    stops here, in one legible error, naming the two statements to run.
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
        # S608: the only interpolation is the two role-name constants and the
        # manual-step string, all defined in this file. No outside value reaches it.
        f"DO $$ DECLARE missing text; BEGIN "  # noqa: S608
        f"SELECT string_agg(r.name, ', ') INTO missing FROM "
        f"(VALUES ('{APP_ROLE}'), ('{WORKER_ROLE}')) AS r(name) "
        f"WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.name); "
        f"IF missing IS NOT NULL THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: required database role(s) missing: %', missing "
        f"USING HINT = 'the migrating role may not create roles on this server. "
        f"Run as a superuser, then re-run the migration: {_MANUAL_STEP}'; "
        f"END IF; END $$;"
    )
    op.execute(
        f"DO $$ BEGIN ALTER ROLE {WORKER_ROLE} BYPASSRLS; "
        f"EXCEPTION WHEN insufficient_privilege THEN "
        f"RAISE NOTICE 'could not set BYPASSRLS on {WORKER_ROLE}; "
        f"grant it manually with a superuser role'; END $$;"
    )
