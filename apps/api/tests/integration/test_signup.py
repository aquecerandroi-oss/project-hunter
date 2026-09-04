"""Sign-up: one request creates an entire, usable tenant.

``POST /api/v1/orgs`` is the only place a tenant comes into existence, and it
has to leave nothing half-built — an organization without an owner, or without
the risk profile onboarding copies from, is a state no later code knows how to
repair. These tests assert each of the five rows it writes, and that they are
all visible to the person who created them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.billing import Subscription
from hunter_core.db.models.identity import Organization, OrganizationMember, Workspace
from hunter_core.db.models.portfolios import RiskProfile
from hunter_core.db.models.system import AuditLog
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import MemberStatus, OrganizationRole, Plan, RiskPreset

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_sign_up_creates_organization_owner_workspace_profile_and_subscription(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    actor = await create_org(client, make_actor("founder"), "Acme Capital")
    assert actor.org_id is not None
    assert actor.user_id is not None

    async with tenant_session(session_factory, actor.org_id, actor.user_id) as session:
        organization = await session.get(Organization, actor.org_id)
        member = await session.get(OrganizationMember, (actor.org_id, actor.user_id))
        workspace = await session.get(Workspace, actor.workspace_id)
        profiles = (
            (
                await session.execute(
                    select(RiskProfile).where(RiskProfile.organization_id == actor.org_id)
                )
            )
            .scalars()
            .all()
        )
        subscription = (
            await session.execute(
                select(Subscription).where(Subscription.organization_id == actor.org_id)
            )
        ).scalar_one()

    assert organization is not None
    assert organization.slug == "acme-capital"
    assert organization.name == "Acme Capital"
    assert organization.plan is Plan.FREE

    assert member is not None
    assert member.role is OrganizationRole.OWNER
    assert member.status is MemberStatus.ACTIVE
    assert member.joined_at is not None

    assert workspace is not None
    assert workspace.name == "Acme Capital"
    assert workspace.default_risk_profile_id is not None

    # the Balanced system preset is copied, never referenced: the organization
    # must be able to tune its own limits without editing a shared row
    assert len(profiles) == 1
    assert profiles[0].preset is RiskPreset.BALANCED
    assert profiles[0].limits, "the copy must carry the seeded limits, not an empty dict"
    assert workspace.default_risk_profile_id == profiles[0].id

    assert subscription.plan is Plan.FREE


async def test_sign_up_writes_exactly_one_audit_row_with_the_actor_and_the_after_state(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    actor = await create_org(client, make_actor("auditor"), "Audited Org")
    assert actor.org_id is not None

    async with tenant_session(session_factory, actor.org_id, actor.user_id) as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "organization.created")
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    row = rows[0]
    assert row.organization_id == actor.org_id
    assert row.actor_id == actor.user_id
    assert row.actor_type == "user"
    assert row.entity_type == "organization"
    assert row.entity_id == actor.org_id
    assert row.after is not None
    assert row.after["slug"] == "audited-org"


async def test_two_organizations_of_the_same_name_get_distinct_slugs(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    first = await create_org(client, make_actor("slug-one"), "Duplicate Name")
    second = await create_org(client, make_actor("slug-two"), "Duplicate Name")

    assert first.org_id != second.org_id
    one = await client.get(f"/api/v1/orgs/{first.org_id}", headers=first.headers)
    two = await client.get(f"/api/v1/orgs/{second.org_id}", headers=second.headers)
    assert one.json()["slug"] == "duplicate-name"
    assert two.json()["slug"].startswith("duplicate-name-")
    assert one.json()["slug"] != two.json()["slug"]


async def test_me_reports_the_user_the_membership_and_the_onboarding_state(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor = await create_org(client, make_actor("shell"), "Shell Org")

    body: dict[str, Any] = (await client.get("/api/v1/me", headers=actor.headers)).json()

    assert body["user"]["email"] == actor.email
    assert body["user"]["display_name"] == "Shell"
    assert len(body["memberships"]) == 1
    membership = body["memberships"][0]
    assert membership["role"] == "OWNER"
    assert membership["organization"]["id"] == str(actor.org_id)
    # onboarding has not run, so the shell must route back into the wizard
    assert membership["onboarding"]["completed"] is False
    assert membership["onboarding"]["workspace_id"] == str(actor.workspace_id)


async def test_an_unauthenticated_request_is_401_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 401


async def test_a_garbage_bearer_token_is_401_and_never_echoed(
    client: httpx.AsyncClient,
) -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.FAKE.forged"

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert token not in response.text


async def test_the_api_role_is_downgraded_so_rls_bites_even_as_the_database_owner(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """The proof behind ``tenant_session``'s ``SET LOCAL ROLE hunter_app``.

    The test container connects as a superuser, and a superuser is exempt from
    ``FORCE ROW LEVEL SECURITY``. Without the downgrade, every RLS assertion in
    this suite would pass in development and mean nothing in production.
    """
    org_a = await create_org(client, make_actor("rls-a"), "RLS A")
    org_b = await create_org(client, make_actor("rls-b"), "RLS B")
    assert org_a.org_id is not None and org_b.org_id is not None

    async with tenant_session(session_factory, org_a.org_id, org_a.user_id) as session:
        role = await session.scalar(text("SELECT current_user"))
        visible = (
            (await session.execute(select(Organization.id).where(Organization.id != None)))  # noqa: E711
            .scalars()
            .all()
        )
        other_members = (
            (
                await session.execute(
                    select(OrganizationMember.user_id).where(
                        OrganizationMember.organization_id == org_b.org_id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert role == "hunter_app"
    assert list(visible) == [org_a.org_id], "org B must not be visible inside org A's transaction"
    assert list(other_members) == []


async def test_the_api_role_cannot_write_the_platform_configuration(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``hunter_app`` holds SELECT and nothing else on ``feature_flags``
    (DATABASE.md §15.6), so a logic bug or an injection in a request handler
    cannot flip a platform flag.
    """
    from sqlalchemy.exc import ProgrammingError

    org_id = uuid.uuid4()
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with tenant_session(session_factory, org_id) as session:
            await session.execute(text("UPDATE feature_flags SET enabled = true"))
