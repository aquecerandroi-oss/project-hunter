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

Neither is written by a single ``FOR ALL`` policy, and the re-review is why.
A policy that covers every command over every row the caller can *see* turns a
directory listing into a write surface: co-membership made a colleague's
``external_auth_id`` editable (an account takeover), and ``organizations``
allowed a ``DELETE`` that cascades through every table the tenant owns. Both are
now stated one command at a time — see :func:`_organization_policies` and
:func:`_user_policies` — and the commands that are absent are absent on purpose.

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
ORGANIZATION_UPDATE_POLICY = "organization_updatable"
ORGANIZATION_BOOTSTRAP_POLICY = "organization_bootstrap"

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


def _organization_policies() -> None:
    """``organizations`` — read, rename, bootstrap. Never delete.

    One ``FOR ALL`` policy used to cover all four commands, which handed the API
    role a ``DELETE`` that cascades: every tenant table references
    ``organizations(id) ON DELETE CASCADE``, so a single statement would take the
    portfolios, orders, positions and fills with it. The commands are now
    separate policies, and the one that is missing is the point:

    - ``tenant_isolation`` (``FOR SELECT``) — a tenant sees its own row;
    - ``organization_updatable`` (``FOR UPDATE``) — and may rename it, change its
      plan or move its kill switch, ``WITH CHECK`` binding the new row to the
      same id so an update cannot re-parent it;
    - ``organization_bootstrap`` (``FOR INSERT``) — sign-up still has to create
      the row. The API mints the UUID v7 first and sets ``app.current_org`` to it
      before inserting, so the check is as tight as the others.

    ``DELETE`` has no policy at all, for anyone: with ``FORCE ROW LEVEL
    SECURITY`` that closes it to the table owner too, and it is reachable only
    through ``hunter_worker`` (``BYPASSRLS``, and the only role holding the
    ``DELETE`` grant) or a superuser — see :data:`ddl.tables.WORKER_DELETE_TABLES`.
    """
    _force("organizations")
    op.execute(
        f"CREATE POLICY {ORGANIZATION_POLICY} ON organizations "
        f"FOR SELECT USING (id = {ORG_SETTING})"
    )
    op.execute(
        f"CREATE POLICY {ORGANIZATION_UPDATE_POLICY} ON organizations "
        f"FOR UPDATE USING (id = {ORG_SETTING}) WITH CHECK (id = {ORG_SETTING})"
    )
    op.execute(
        f"CREATE POLICY {ORGANIZATION_BOOTSTRAP_POLICY} ON organizations "
        f"FOR INSERT WITH CHECK (id = {ORG_SETTING})"
    )


def _user_policies() -> None:
    """``users`` — a colleague is readable; only you may write your own row.

    ``user_visible_to_co_members`` is ``FOR SELECT``. It was ``FOR ALL``, and a
    policy that grants every command over every row of the current organization
    is an account takeover: any member could run
    ``UPDATE users SET external_auth_id = '<their own Clerk id>' WHERE id = <a
    colleague>`` and log in as them, or delete the row outright. Nothing needs
    that — a member list is a read.

    ``user_reads_own_row`` keeps ``USING``/``WITH CHECK`` on ``app.current_user``
    and is therefore the only write path into this table for the API: a person
    edits themselves, and nobody else.
    """
    _force("users")
    op.execute(
        f"CREATE POLICY {USER_MEMBERSHIP_POLICY} ON users FOR SELECT USING ({_CO_MEMBERSHIP})"
    )
    op.execute(f"CREATE POLICY {USER_SELF_POLICY} ON users USING ({_SELF}) WITH CHECK ({_SELF})")


def enable_row_level_security() -> None:
    """Enable, force and police every relation that belongs to a tenant."""
    _tenant_policies()
    _risk_profile_policies()
    _append_only_scope_policies()
    _organization_policies()
    _user_policies()


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
        (ORGANIZATION_UPDATE_POLICY, "organizations"),
        (ORGANIZATION_BOOTSTRAP_POLICY, "organizations"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    for table in SELF_SCOPED_TABLES:
        _unforce(table)
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY} ON {table}")
        _unforce(table)
