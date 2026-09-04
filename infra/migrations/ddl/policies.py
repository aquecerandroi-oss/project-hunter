"""Row Level Security policies — DATABASE.md §1.2/§15.4, SECURITY.md §3.

RLS is enabled *and forced* on every relation that holds a tenant's data, so
even the table owner is filtered. Three shapes exist:

**Tenant tables** (``TENANT_TABLES``) — ``tenant_isolation`` on
``organization_id = current_setting('app.current_org', true)::uuid``, both
``USING`` and ``WITH CHECK``. Partition children of a tenant parent get the same
policy of their own, because Postgres does not consult the parent's policies for
a query that names the child (see ``harden_partition_sql``).

**Self-scoped tables** (``SELF_SCOPED_TABLES``) — ``organizations`` has no
``organization_id``; its tenant key is its own ``id``. ``users`` is neither:
a user belongs to no organization in particular, so it is visible through
co-membership of the current organization, plus one policy for the caller's own
row keyed on a second setting, ``app.current_user``.

**Exceptions on top of ``tenant_isolation``** — the seeded system risk presets,
the system-scope audit row, and the platform-wide kill switch. Each is one named
policy with the narrowest possible predicate, and each is documented where it is
created.

Two settings, then, and T06 must set both:

- ``app.current_org`` — the organization the request acts for;
- ``app.current_user`` — the ``users.id`` of the caller (never the Clerk id).

Both are read as ``NULLIF(current_setting(name, true), '')::uuid``: NULL when
absent, and ``NULL = anything`` is NULL, which RLS treats as "no row" — so a
session that forgets to set them sees nothing rather than everything. The
``NULLIF`` is what keeps that true on the *second* transaction of a pooled
connection, where the GUC comes back as an empty string rather than unset.
"""

from __future__ import annotations

from alembic import op

from ddl.tables import SELF_SCOPED_TABLES, TENANT_TABLES
from hunter_core.db.models import AUDIT_SYSTEM_POLICY, ORG_MATCH, ORG_SETTING, TENANT_POLICY

USER_SETTING = "NULLIF(current_setting('app.current_user', true), '')::uuid"
"""The caller, or NULL. ``NULLIF`` for the same reason as ``ORG_SETTING`` —
a GUC that has been ``SET LOCAL`` once comes back as ``''``, not unset."""

SYSTEM_PRESET_READ_POLICY = "system_presets_readable"
SYSTEM_PRESET_WRITE_POLICY = "system_presets_manageable"
KILL_SWITCH_SYSTEM_POLICY = "system_scope_readable"
USER_MEMBERSHIP_POLICY = "user_visible_to_co_members"
USER_SELF_POLICY = "user_reads_own_row"
ORGANIZATION_POLICY = TENANT_POLICY

# S608: the only interpolation is ORG_SETTING, a module constant defined above.
# No value from outside this file — let alone from a request — reaches this DDL;
# the tenant id enters at *runtime*, through the GUC the predicate reads.
_CO_MEMBERSHIP = (
    "EXISTS (SELECT 1 FROM organization_members m "  # noqa: S608
    f"WHERE m.user_id = users.id AND m.organization_id = {ORG_SETTING})"
)
_SELF = f"id = {USER_SETTING}"


def _force(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _unforce(table: str) -> None:
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _tenant_policies() -> None:
    """``tenant_isolation`` on everything carrying ``organization_id``."""
    for table in TENANT_TABLES:
        _force(table)
        op.execute(
            f"CREATE POLICY {TENANT_POLICY} ON {table} USING ({ORG_MATCH}) WITH CHECK ({ORG_MATCH})"
        )


def _risk_profile_policies() -> None:
    """The seeded system presets — ``organization_id IS NULL``.

    Every organization copies one at onboarding, so they must be readable by all;
    ``tenant_isolation`` alone would hide them. Read-only for the app: its
    ``WITH CHECK`` stays strictly tenant-scoped, so it can never create or edit a
    preset.

    ``system_presets_manageable`` is what lets the *seed* write them. Under
    ``FORCE ROW LEVEL SECURITY`` even the table owner is filtered, so
    ``infra/scripts/seed.py`` running as an ordinary (``NOSUPERUSER``) owner —
    which is what a managed Postgres gives you — inserted zero preset rows and
    said it had seeded three. The policy is granted to the migrating role only,
    and is bounded to exactly the rows that have no organization.
    """
    op.execute(
        f"CREATE POLICY {SYSTEM_PRESET_READ_POLICY} ON risk_profiles "
        f"FOR SELECT USING (organization_id IS NULL)"
    )
    op.execute(
        f"CREATE POLICY {SYSTEM_PRESET_WRITE_POLICY} ON risk_profiles TO CURRENT_USER "
        f"USING (organization_id IS NULL) WITH CHECK (organization_id IS NULL)"
    )


def _append_only_scope_policies() -> None:
    """System-scope rows in the two append-only tenant tables.

    ``audit_logs``: a system action has no organization, and CLAUDE.md requires
    every meaningful mutation to be audited — including the ones the API performs
    outside a tenant context (sign-up, webhook, cron). Without this the insert is
    silently refused by ``tenant_isolation``'s ``WITH CHECK`` and the audit trail
    quietly loses exactly the events nobody is watching. ``FOR INSERT`` only:
    reading other tenants' rows stays impossible.

    ``kill_switch_transitions``: the platform-wide switch affects every tenant,
    so every tenant may read that it moved. ``FOR SELECT`` only, and the CHECK
    constraint guarantees a ``system`` row has no organization to leak.
    """
    op.execute(
        f"CREATE POLICY {AUDIT_SYSTEM_POLICY} ON audit_logs "
        f"FOR INSERT WITH CHECK (organization_id IS NULL)"
    )
    op.execute(
        f"CREATE POLICY {KILL_SWITCH_SYSTEM_POLICY} ON kill_switch_transitions "
        f"FOR SELECT USING (scope = 'system')"
    )


def _self_scoped_policies() -> None:
    """``organizations`` and ``users`` — RLS without an ``organization_id``."""
    _force("organizations")
    op.execute(
        f"CREATE POLICY {ORGANIZATION_POLICY} ON organizations "
        f"USING (id = {ORG_SETTING}) WITH CHECK (id = {ORG_SETTING})"
    )
    _force("users")
    op.execute(f"CREATE POLICY {USER_MEMBERSHIP_POLICY} ON users USING ({_CO_MEMBERSHIP})")
    op.execute(f"CREATE POLICY {USER_SELF_POLICY} ON users USING ({_SELF}) WITH CHECK ({_SELF})")


def enable_row_level_security() -> None:
    """Enable, force and police every relation that belongs to a tenant."""
    _tenant_policies()
    _risk_profile_policies()
    _append_only_scope_policies()
    _self_scoped_policies()


def disable_row_level_security() -> None:
    """Drop the policies and turn RLS back off (tables are dropped afterwards)."""
    for policy, table in (
        (SYSTEM_PRESET_READ_POLICY, "risk_profiles"),
        (SYSTEM_PRESET_WRITE_POLICY, "risk_profiles"),
        (AUDIT_SYSTEM_POLICY, "audit_logs"),
        (KILL_SWITCH_SYSTEM_POLICY, "kill_switch_transitions"),
        (USER_MEMBERSHIP_POLICY, "users"),
        (USER_SELF_POLICY, "users"),
        (ORGANIZATION_POLICY, "organizations"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    for table in SELF_SCOPED_TABLES:
        _unforce(table)
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY} ON {table}")
        _unforce(table)
