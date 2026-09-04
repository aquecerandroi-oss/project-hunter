"""Row Level Security really isolates tenants — DATABASE.md §1.2, SECURITY.md §3.

The container's own role is a superuser, and superusers bypass RLS even when it
is FORCEd, so every assertion here runs after ``SET LOCAL ROLE hunter_app`` —
the role the API actually uses, which has no ``BYPASSRLS``.

The T04 cross-review found four holes this module now closes:

- partition children of a tenant parent had no RLS of their own, and Postgres
  does not consult the parent's policies for a query naming the child;
- ``portfolio_equity_snapshots``, ``agent_stats``, ``backtest_results``,
  ``backtest_trades`` and ``kill_switch_transitions`` had no ``organization_id``
  at all, so a tenant's money and its kill-switch history were global;
- ``organizations`` and ``users`` had no policies, so any tenant could read and
  edit any other tenant's organization row and enumerate its members;
- a system-scope audit row could not be written, because ``tenant_isolation``
  refused a NULL ``organization_id``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hunter_core.db.models import tenant_tables
from hunter_core.db.session import create_session_factory, get_session, tenant_session
from hunter_core.domain.types import uuid7

from .conftest import migration_ddl

pytestmark = pytest.mark.integration

_AS_APP = text("SET LOCAL ROLE hunter_app")
_RLS_DENIED = "row-level security"
_SNAPSHOT_TS = datetime(2026, 10, 2, tzinfo=UTC)

_SET_CURRENT_USER = text("SELECT set_config('app.current_user', :user_id, true)")


class Tenant:
    """One organization with a member, a workspace, a portfolio and its curve."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.org_id = uuid7()
        self.user_id = uuid7()
        self.workspace_id = uuid7()
        self.portfolio_id = uuid7()

    @property
    def portfolio_name(self) -> str:
        return f"pf-{self.slug}"


@asynccontextmanager
async def app_session(
    factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> AsyncGenerator[AsyncSession]:
    """``tenant_session`` with the ``hunter_app`` role assumed for the transaction.

    ``app.current_user`` is the second setting T06 will set alongside
    ``app.current_org``: it is what lets a person read their own ``users`` row
    before (or outside) any organization context. ``tenant_session`` itself is
    unchanged — it still only sets ``app.current_org``.
    """
    async with tenant_session(factory, org_id) as session:
        if user_id is not None:
            await session.execute(_SET_CURRENT_USER, {"user_id": str(user_id)})
        await session.execute(_AS_APP)
        yield session


async def _create_tenant(engine: AsyncEngine, tenant: Tenant) -> None:
    """Insert the tenant as the superuser owner, which RLS does not constrain."""
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO users (id, external_auth_id, email) VALUES (:id, :ext, :email)"),
            {
                "id": tenant.user_id,
                "ext": f"clerk-{tenant.slug}",
                "email": f"{tenant.slug}@example.test",
            },
        )
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
            {"id": tenant.org_id, "slug": tenant.slug},
        )
        await connection.execute(
            text(
                "INSERT INTO organization_members (organization_id, user_id, role, status) "
                "VALUES (:org, :user, 'OWNER', 'active')"
            ),
            {"org": tenant.org_id, "user": tenant.user_id},
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, :name, 'explore')"
            ),
            {"id": tenant.workspace_id, "org": tenant.org_id, "name": f"ws-{tenant.slug}"},
        )
        await connection.execute(
            text(
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, initial_capital)"
                " VALUES (:id, :org, :ws, :name, 10000)"
            ),
            {
                "id": tenant.portfolio_id,
                "org": tenant.org_id,
                "ws": tenant.workspace_id,
                "name": tenant.portfolio_name,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, "
                "resolution, ts, cash, equity, exposure_notional, unrealized_pnl, "
                "realized_pnl_cum, peak_equity) "
                "VALUES (:org, :pf, '1h', :ts, 1, 1, 0, 0, 0, 1)"
            ),
            {"org": tenant.org_id, "pf": tenant.portfolio_id, "ts": _SNAPSHOT_TS},
        )
        await connection.execute(
            text(
                "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, action) "
                "VALUES (:id, :ts, :org, 'system', 'tenant.created')"
            ),
            {"id": uuid7(), "ts": _SNAPSHOT_TS, "org": tenant.org_id},
        )


@pytest_asyncio.fixture
async def tenants(schema_engine: AsyncEngine) -> AsyncIterator[tuple[Tenant, Tenant]]:
    """Two organizations with one portfolio each, plus one system risk preset.

    ``hunter_app`` is granted to the test's login role so ``SET LOCAL ROLE`` is
    allowed — the same grant a deployment makes once.
    """
    preset_id = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_app TO CURRENT_USER"))
        await connection.execute(
            text(
                "INSERT INTO risk_profiles (id, organization_id, name, preset, limits) "
                "VALUES (:id, NULL, 'Balanced', 'balanced', '{}'::jsonb) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": preset_id},
        )
    org_a = Tenant(f"org-a-{uuid.uuid4().hex[:8]}")
    org_b = Tenant(f"org-b-{uuid.uuid4().hex[:8]}")
    await _create_tenant(schema_engine, org_a)
    await _create_tenant(schema_engine, org_b)
    try:
        yield org_a, org_b
    finally:
        async with schema_engine.begin() as connection:
            for tenant in (org_a, org_b):
                await connection.execute(
                    text("DELETE FROM organizations WHERE id = :id"), {"id": tenant.org_id}
                )
                await connection.execute(
                    text("DELETE FROM users WHERE id = :id"), {"id": tenant.user_id}
                )
                await connection.execute(
                    text("DELETE FROM audit_logs WHERE organization_id = :id"),
                    {"id": tenant.org_id},
                )


@pytest.fixture
def factory(schema_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(schema_engine)


async def test_each_org_sees_only_its_own_portfolio(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    org_a, org_b = tenants

    async with app_session(factory, org_a.org_id) as session:
        result = await session.execute(text("SELECT name FROM portfolios"))
        assert [row[0] for row in result] == [org_a.portfolio_name]

    async with app_session(factory, org_b.org_id) as session:
        result = await session.execute(text("SELECT name FROM portfolios"))
        assert [row[0] for row in result] == [org_b.portfolio_name]


async def test_without_current_org_the_policy_returns_nothing(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """No ``app.current_org`` means zero rows — never "all rows"."""
    org_a, org_b = tenants
    assert org_a.org_id != org_b.org_id
    async with get_session(factory) as session, session.begin():
        await session.execute(_AS_APP)
        assert await session.scalar(text("SELECT count(*) FROM portfolios")) == 0


async def test_insert_with_another_orgs_id_fails_the_with_check(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    org_a, org_b = tenants
    with pytest.raises(ProgrammingError, match=_RLS_DENIED):
        async with app_session(factory, org_a.org_id) as session:
            await session.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, "
                    "initial_capital) VALUES (:id, :org, :ws, 'smuggled', 1)"
                ),
                {"id": uuid7(), "org": org_b.org_id, "ws": org_b.workspace_id},
            )


async def test_rls_is_forced_on_every_relation_that_holds_tenant_data(
    schema_engine: AsyncEngine,
) -> None:
    """The frozen lists, the models and the database all agree — partitions included.

    The set is stated over ``pg_class`` **without** filtering ``relispartition``,
    which is the whole point: ``audit_logs_2026_09`` carries ``organization_id``
    and so must carry RLS, and before this fix it did not.
    """
    security = migration_ddl("security")
    frozen: tuple[str, ...] = security.TENANT_TABLES
    self_scoped: tuple[str, ...] = security.SELF_SCOPED_TABLES

    assert set(frozen) == set(tenant_tables()), (
        "a model gained or lost organization_id without a migration updating "
        "ddl.tables.TENANT_TABLES"
    )
    async with schema_engine.connect() as connection:
        with_org = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND a.attname = 'organization_id' AND NOT a.attisdropped"
            )
        )
        tenant_relations = {row[0] for row in with_org}
        secured_rows = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relrowsecurity AND c.relforcerowsecurity"
            )
        )
        secured = {row[0] for row in secured_rows}

    partitions = {name for name in tenant_relations if name not in frozen}
    assert partitions, "no tenant partition children were checked"
    assert secured == tenant_relations | set(self_scoped)


async def test_every_tenant_partition_child_carries_its_own_policy(
    schema_engine: AsyncEngine,
) -> None:
    """A policy on the parent does not reach a query that names the child."""
    async with schema_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid "
                "WHERE n.nspname = 'public' AND c.relispartition "
                "AND c.relkind IN ('r', 'p') "
                "AND a.attname = 'organization_id' AND NOT a.attisdropped"
            )
        )
        children = [row[0] for row in result]
        assert children

        missing: list[str] = []
        for child in children:
            has_policy = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE schemaname = 'public' AND tablename = :t "
                    "AND policyname = 'tenant_isolation'"
                ),
                {"t": child},
            )
            if not has_policy:
                missing.append(child)
    assert missing == [], f"partition children without tenant_isolation: {missing}"


async def test_reading_a_partition_directly_still_only_shows_the_current_org(
    schema_engine: AsyncEngine, tenants: tuple[Tenant, Tenant]
) -> None:
    """The reviewer's second probe, against the child rather than the parent.

    ``hunter_app`` cannot reach a partition at all any more (see
    ``test_schema_privileges.py``), so the probe runs as an ordinary role that is
    granted ``SELECT`` on the child alone. Without a policy on the child it would
    see both organizations' audit rows; with one it sees only its own.
    """
    org_a, org_b = tenants
    probe = f"rls_probe_{uuid.uuid4().hex[:8]}"
    async with schema_engine.begin() as connection:
        await connection.execute(text(f"CREATE ROLE {probe} NOSUPERUSER NOINHERIT"))
        await connection.execute(text(f"GRANT {probe} TO CURRENT_USER"))
        await connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {probe}"))
        await connection.execute(text(f"GRANT SELECT ON audit_logs_2026_10 TO {probe}"))
    try:
        async with schema_engine.connect() as connection:
            await connection.begin()
            await connection.execute(
                text("SELECT set_config('app.current_org', :org, true)"),
                {"org": str(org_a.org_id)},
            )
            await connection.execute(text(f"SET LOCAL ROLE {probe}"))
            rows = await connection.execute(text("SELECT organization_id FROM audit_logs_2026_10"))
            visible = {row[0] for row in rows}
            await connection.rollback()
        assert visible == {org_a.org_id}
        assert org_b.org_id not in visible
    finally:
        async with schema_engine.begin() as connection:
            await connection.execute(text(f"REVOKE ALL ON audit_logs_2026_10 FROM {probe}"))
            await connection.execute(text(f"REVOKE USAGE ON SCHEMA public FROM {probe}"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {probe}"))


async def test_equity_snapshots_are_not_readable_across_tenants(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """The review's finding: the equity curve had no ``organization_id`` at all."""
    org_a, org_b = tenants

    async with app_session(factory, org_a.org_id) as session:
        mine = await session.scalar(
            text("SELECT count(*) FROM portfolio_equity_snapshots WHERE portfolio_id = :pf"),
            {"pf": org_a.portfolio_id},
        )
        theirs = await session.scalar(
            text("SELECT count(*) FROM portfolio_equity_snapshots WHERE portfolio_id = :pf"),
            {"pf": org_b.portfolio_id},
        )
    assert mine == 1
    assert theirs == 0


async def test_an_organization_cannot_read_or_edit_another(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """``organizations`` is policed on its own ``id``, having no ``organization_id``."""
    org_a, org_b = tenants

    async with app_session(factory, org_a.org_id) as session:
        visible = await session.execute(text("SELECT id FROM organizations"))
        assert [row[0] for row in visible] == [org_a.org_id]

        updated = await session.execute(
            text("UPDATE organizations SET name = 'hijacked' WHERE id = :id"),
            {"id": org_b.org_id},
        )
        assert updated.rowcount == 0


async def test_an_organization_cannot_list_another_organizations_users(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """``users`` is reachable through co-membership of the current organization."""
    org_a, org_b = tenants

    async with app_session(factory, org_a.org_id, org_a.user_id) as session:
        emails = await session.execute(text("SELECT id FROM users"))
        visible = {row[0] for row in emails}

    assert org_a.user_id in visible
    assert org_b.user_id not in visible


async def test_a_user_can_read_their_own_row_without_an_organization(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """``app.current_user`` is what makes "me" resolvable before any org is chosen."""
    org_a, org_b = tenants

    async with app_session(factory, org_b.org_id, org_a.user_id) as session:
        visible = await session.execute(
            text("SELECT id FROM users WHERE id = ANY(:ids)"),
            {"ids": [org_a.user_id, org_b.user_id]},
        )
        rows = {row[0] for row in visible}

    # co-membership shows org B's member; app.current_user adds exactly one more
    assert rows == {org_a.user_id, org_b.user_id}

    async with app_session(factory, org_b.org_id) as session:
        without_setting = await session.execute(
            text("SELECT id FROM users WHERE id = ANY(:ids)"),
            {"ids": [org_a.user_id, org_b.user_id]},
        )
        rows_without = {row[0] for row in without_setting}

    assert rows_without == {org_b.user_id}


async def test_the_app_can_write_a_system_scope_audit_row(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """Sign-up, webhooks and cron audit outside any tenant — and must be able to.

    ``tenant_isolation``'s ``WITH CHECK`` refuses a NULL ``organization_id``, so
    without ``audit_system_scope`` the audit trail silently lost exactly the
    events that happen with no organization in context.
    """
    org_a, org_b = tenants

    async with app_session(factory, org_a.org_id) as session:
        await session.execute(
            text(
                "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, action) "
                "VALUES (:id, :ts, NULL, 'system', 'system.boot')"
            ),
            {"id": uuid7(), "ts": _SNAPSHOT_TS},
        )
        cross_tenant = await session.scalar(
            text("SELECT count(*) FROM audit_logs WHERE organization_id = :org"),
            {"org": org_b.org_id},
        )
    assert cross_tenant == 0


async def test_the_platform_kill_switch_is_readable_by_every_tenant(
    schema_engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    tenants: tuple[Tenant, Tenant],
) -> None:
    """A ``system`` transition affects everyone, so everyone may see it; an
    organization-scope one belongs to that organization alone.
    """
    org_a, org_b = tenants
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions "
                "(id, organization_id, scope, from_state, to_state, actor_type) "
                "VALUES (:id, NULL, 'system', 'ACTIVE', 'WARNING', 'system')"
            ),
            {"id": uuid7()},
        )
        await connection.execute(
            text(
                "INSERT INTO kill_switch_transitions "
                "(id, organization_id, scope, scope_id, from_state, to_state, actor_type) "
                "VALUES (:id, :org, 'organization', :org, 'ACTIVE', 'EMERGENCY', 'user')"
            ),
            {"id": uuid7(), "org": org_b.org_id},
        )

    async with app_session(factory, org_a.org_id) as session:
        result = await session.execute(
            text("SELECT scope, organization_id FROM kill_switch_transitions")
        )
        rows = [(row[0], row[1]) for row in result]

    assert ("system", None) in rows
    assert all(organization != org_b.org_id for _scope, organization in rows)


async def test_system_risk_presets_are_readable_but_never_writable(
    factory: async_sessionmaker[AsyncSession], tenants: tuple[Tenant, Tenant]
) -> None:
    """``organization_id IS NULL`` presets are visible to every org, read-only —
    the app copies one into the org at onboarding, it never edits the original.
    """
    org_a, _ = tenants
    async with app_session(factory, org_a.org_id) as session:
        visible = await session.scalar(
            text("SELECT count(*) FROM risk_profiles WHERE organization_id IS NULL")
        )
        assert visible == 1

    with pytest.raises(ProgrammingError, match=_RLS_DENIED):
        async with app_session(factory, org_a.org_id) as session:
            await session.execute(
                text(
                    "INSERT INTO risk_profiles (id, organization_id, name, preset, limits) "
                    "VALUES (:id, NULL, 'sneaky', 'custom', '{}'::jsonb)"
                ),
                {"id": uuid7()},
            )
