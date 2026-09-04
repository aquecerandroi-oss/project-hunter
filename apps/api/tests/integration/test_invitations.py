"""Invitations end to end: issue, accept, revoke — and everything that must fail.

The token is the credential here, so the tests that matter are the negative
ones: it must not be readable back, must not work twice, must not let somebody
else use it, and must not be a way to grant a role the inviter does not hold.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, update

from hunter_api.services.invitations import hash_token
from hunter_core.db.models.identity import OrganizationInvitation
from hunter_core.db.session import tenant_session
from hunter_core.domain.types import utcnow

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture
async def owner(client: httpx.AsyncClient, make_actor: Callable[[str], Actor]) -> Actor:
    unique = uuid.uuid4().hex[:8]
    return await create_org(client, make_actor(f"inviter-{unique}"), f"Invites {unique}")


async def _invite(
    client: httpx.AsyncClient, owner: Actor, email: str, role: str = "ANALYST"
) -> tuple[str, str]:
    response = await client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": email, "role": role},
        headers=owner.headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["token"], body["id"]


async def test_the_token_is_returned_once_and_only_its_hash_is_stored(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
) -> None:
    token, invitation_id = await _invite(client, owner, "hashed@example.test")

    listed = await client.get(f"/api/v1/orgs/{owner.org_id}/invitations", headers=owner.headers)

    assert token not in listed.text, "a second read must never expose the token"
    assert owner.org_id is not None
    async with tenant_session(session_factory, owner.org_id, owner.user_id) as session:
        stored = (
            await session.execute(
                select(OrganizationInvitation.token_hash).where(
                    OrganizationInvitation.id == uuid.UUID(invitation_id)
                )
            )
        ).scalar_one()
    assert stored == hash_token(token)
    assert token not in stored


async def test_accepting_creates_the_membership_with_the_invited_role(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    joiner = make_actor(f"accepts-{uuid.uuid4().hex[:8]}")
    token, _ = await _invite(client, owner, joiner.email, role="TRADER")

    accepted = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)

    assert accepted.status_code == 200
    assert accepted.json()["role"] == "TRADER"
    me = (await client.get("/api/v1/me", headers=joiner.headers)).json()
    assert me["memberships"][0]["organization"]["id"] == str(owner.org_id)
    assert me["memberships"][0]["role"] == "TRADER"


async def test_accepting_with_a_different_email_is_403(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    intruder = make_actor(f"intruder-{uuid.uuid4().hex[:8]}")
    token, _ = await _invite(client, owner, "someone-else@example.test")

    response = await client.post(f"/api/v1/invitations/{token}/accept", headers=intruder.headers)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    body = (await client.get("/api/v1/me", headers=intruder.headers)).json()
    assert body["memberships"] == []


async def test_the_same_token_cannot_be_accepted_twice(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    joiner = make_actor(f"twice-{uuid.uuid4().hex[:8]}")
    token, _ = await _invite(client, owner, joiner.email)

    first = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)
    second = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)

    assert first.status_code == 200
    assert second.status_code == 404


async def test_an_expired_invitation_is_404(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
    make_actor: Callable[[str], Actor],
) -> None:
    joiner = make_actor(f"expired-{uuid.uuid4().hex[:8]}")
    token, invitation_id = await _invite(client, owner, joiner.email)
    assert owner.org_id is not None
    async with tenant_session(session_factory, owner.org_id, owner.user_id) as session:
        await session.execute(
            update(OrganizationInvitation)
            .where(OrganizationInvitation.id == uuid.UUID(invitation_id))
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )

    response = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)

    # the same 404 as "no such token": from the holder's side both mean
    # "this link does not work", and distinguishing them is an oracle
    assert response.status_code == 404


async def test_an_unknown_token_is_404(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    stranger = make_actor(f"stranger-{uuid.uuid4().hex[:8]}")

    response = await client.post(f"/api/v1/invitations/{'z' * 43}/accept", headers=stranger.headers)

    assert response.status_code == 404


async def test_accepting_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.post(f"/api/v1/invitations/{'z' * 43}/accept")

    assert response.status_code == 401


async def test_a_revoked_invitation_can_no_longer_be_accepted(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    joiner = make_actor(f"revoked-{uuid.uuid4().hex[:8]}")
    token, invitation_id = await _invite(client, owner, joiner.email)

    revoked = await client.delete(
        f"/api/v1/orgs/{owner.org_id}/invitations/{invitation_id}", headers=owner.headers
    )
    accepted = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)

    assert revoked.status_code == 204
    assert accepted.status_code == 404


async def test_an_admin_cannot_invite_at_owner(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    admin = make_actor(f"admin-{uuid.uuid4().hex[:8]}")
    admin_token, _ = await _invite(client, owner, admin.email, role="ADMIN")
    await client.post(f"/api/v1/invitations/{admin_token}/accept", headers=admin.headers)

    response = await client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": "escalated@example.test", "role": "OWNER"},
        headers=admin.headers,
    )

    # SECURITY.md §2: an ADMIN manages members but "não pode promover a OWNER"
    assert response.status_code == 403
    assert "higher than your own" in response.json()["detail"]


async def test_a_trader_cannot_invite_at_all(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    trader = make_actor(f"trader-{uuid.uuid4().hex[:8]}")
    token, _ = await _invite(client, owner, trader.email, role="TRADER")
    await client.post(f"/api/v1/invitations/{token}/accept", headers=trader.headers)

    response = await client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": "nope@example.test", "role": "VIEWER"},
        headers=trader.headers,
    )

    assert response.status_code == 403


@pytest.mark.parametrize("email", ["not-an-email", "@example.test", "a@b", "", "a b@c.test"])
async def test_a_malformed_invitation_email_is_422(
    client: httpx.AsyncClient, owner: Actor, email: str
) -> None:
    response = await client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": email, "role": "VIEWER"},
        headers=owner.headers,
    )

    assert response.status_code == 422
