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
from sqlalchemy import func, select, text

from hunter_api.auth.clerk_api import StaticProfileSource, UserProfile
from hunter_core.db.models.billing import Subscription
from hunter_core.db.models.identity import Organization, OrganizationMember, User, Workspace
from hunter_core.db.models.portfolios import RiskProfile
from hunter_core.db.models.system import AuditLog
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import MemberStatus, OrganizationRole, Plan, RiskPreset

from .conftest import Actor, auth_header, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
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


async def test_a_second_clerk_account_claiming_a_taken_email_is_409_not_503(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """``users.email`` is unique, so two Clerk accounts cannot both own one.

    The answer has to say which side is at fault. A 503 ("try again") is a lie
    the client retries forever; 409 with a documented ``type`` is a fact the
    frontend can act on — sign in with the account that already owns this
    address, or use a different one.
    """
    unique = uuid.uuid4().hex[:8]
    first = await create_org(client, make_actor(f"claimed-{unique}"), f"Claimed {unique}")

    twin_subject = f"user_FAKE_twin_{unique}"
    profiles.add(UserProfile(external_auth_id=twin_subject, email=first.email))
    response = await client.get("/api/v1/me", headers=auth_header(signing_key, twin_subject))

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["type"] == "https://hunter.dev/problems/email-already-registered"
    assert response.headers["content-type"].startswith("application/problem+json")
    # and the collision is on the record, system-scope, with no second user row
    async with role_session(session_factory, db_role="hunter_worker") as session:
        conflicts = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "user.provision_conflict")
                )
            )
            .scalars()
            .all()
        )
        twins = await session.scalar(
            select(func.count()).select_from(User).where(User.external_auth_id == twin_subject)
        )
    assert [row for row in conflicts if row.after and row.after["external_auth_id"] == twin_subject]
    assert twins == 0


async def test_a_clerk_account_with_no_verified_email_cannot_be_provisioned(
    client: httpx.AsyncClient, signing_key: rsa.RSAPrivateKey, profiles: StaticProfileSource
) -> None:
    """The profile source answers "no verified address" — the same shape Clerk
    returns for an account that signed up and never confirmed. Provisioning
    fails closed: an unverified address in ``users.email`` is an invitation to
    somebody else's organization waiting to be accepted.
    """
    subject = f"user_FAKE_unverified_{uuid.uuid4().hex[:8]}"
    profiles.add(UserProfile(external_auth_id=subject, email=None))

    response = await client.get("/api/v1/me", headers=auth_header(signing_key, subject))

    assert response.status_code == 503
    assert response.json()["type"] == "https://hunter.dev/problems/email-not-verified"


async def test_provisioning_a_brand_new_account_writes_one_provisioned_audit_row(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """``user.provisioned`` means a row was inserted, so it is written only
    when the insert actually inserted: two concurrent first requests of the
    same account must not read as two provisionings.
    """
    actor = make_actor(f"provisioned-{uuid.uuid4().hex[:8]}")

    for _ in range(2):
        assert (await client.get("/api/v1/me", headers=actor.headers)).status_code == 200

    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "user.provisioned",
                        AuditLog.after["external_auth_id"].astext == actor.subject,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_a_token_minted_for_another_origin_is_refused_on_a_tenant_route(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """``azp`` is the origin Clerk minted the token for.

    Same Clerk instance, same signature, same issuer, same user — but issued
    to somebody else's frontend. Without the ``azp`` check that token is a
    working credential here, which is how one application's session becomes
    another application's session.
    """
    unique = uuid.uuid4().hex[:8]
    owner = await create_org(client, make_actor(f"azp-{unique}"), f"Azp {unique}")

    response = await client.get(
        f"/api/v1/orgs/{owner.org_id}",
        headers=auth_header(signing_key, owner.subject, azp="https://attacker.test"),
    )

    assert response.status_code == 401
    assert response.json()["type"] == "https://hunter.dev/problems/invalid-token"
