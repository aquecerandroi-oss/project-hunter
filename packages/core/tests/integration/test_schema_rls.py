"""Row Level Security really isolates tenants — DATABASE.md §1.2, SECURITY.md §3.

The container's own role is a superuser, and superusers bypass RLS even when it
is FORCEd, so every assertion here runs after ``SET LOCAL ROLE hunter_app`` —
the role the API actually uses, which has no ``BYPASSRLS``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

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


class Tenant:
    """One organization with a workspace and a single portfolio."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.org_id = uuid7()
        self.workspace_id = uuid7()
        self.portfolio_id = uuid7()

    @property
    def portfolio_name(self) -> str:
        return f"pf-{self.slug}"


@asynccontextmanager
async def app_session(
    factory: async_sessionmaker[AsyncSession], org_id: uuid.UUID
) -> AsyncGenerator[AsyncSession]:
    """``tenant_session`` with the ``hunter_app`` role assumed for the transaction."""
    async with tenant_session(factory, org_id) as session:
        await session.execute(_AS_APP)
        yield session


async def _create_tenant(engine: AsyncEngine, tenant: Tenant) -> None:
    """Insert the tenant as the superuser owner, which RLS does not constrain."""
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
            {"id": tenant.org_id, "slug": tenant.slug},
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


async def test_rls_is_enabled_and_forced_on_every_tenant_table(schema_engine: AsyncEngine) -> None:
    """The migration's frozen tenant list, the models and the database all agree."""
    frozen: tuple[str, ...] = migration_ddl("security").TENANT_TABLES

    assert set(frozen) == set(tenant_tables()), (
        "a model gained or lost organization_id without a migration updating "
        "ddl.security.TENANT_TABLES"
    )
    async with schema_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relrowsecurity AND c.relforcerowsecurity"
            )
        )
        secured = {row[0] for row in result}
    assert set(tenant_tables()) == secured


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
