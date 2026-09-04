"""Every mutating endpoint writes exactly one audit row, and the rules hold.

CLAUDE.md: "Every meaningful mutation is audited (``audit_logs``,
append-only)." The matrix below is parametrized over the mutating surface, so
a route added later without ``@audited`` fails here. "Exactly one" matters as
much as "at least one": a mutation audited twice makes the trail unusable as
evidence of how many times something happened.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.identity import Workspace
from hunter_core.db.models.system import AuditLog
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import MemberStatus, OrganizationRole

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

ONBOARDING_BODY: dict[str, Any] = {
    "objective": "paper_trading",
    "virtual_capital": "25000.5",
    "risk_preset": "conservative",
    "monitored_exchanges": ["binance", "bybit"],
}


async def _audit_count(
    session_factory: async_sessionmaker[AsyncSession],
    actor: Actor,
    action: str,
) -> int:
    assert actor.org_id is not None
    async with tenant_session(session_factory, actor.org_id, actor.user_id) as session:
        total = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    return total or 0


async def _audit_row(
    session_factory: async_sessionmaker[AsyncSession], actor: Actor, action: str
) -> AuditLog:
    assert actor.org_id is not None
    async with tenant_session(session_factory, actor.org_id, actor.user_id) as session:
        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.action == action)))
            .scalars()
            .all()
        )
    assert len(rows) == 1, f"{action}: expected exactly one audit row, got {len(rows)}"
    return rows[0]


@pytest.fixture
async def owner(client: httpx.AsyncClient, make_actor: Callable[[str], Actor]) -> Actor:
    unique = uuid.uuid4().hex[:8]
    return await create_org(client, make_actor(f"owner-{unique}"), f"Mutations {unique}")


@pytest.mark.parametrize(
    ("action", "method", "suffix", "body"),
    [
        ("organization.updated", "PATCH", "", {"name": "Renamed Org"}),
        ("workspace.created", "POST", "/workspaces", {"name": "Second Workspace"}),
        (
            "invitation.created",
            "POST",
            "/invitations",
            {"email": "invited@example.test", "role": "ANALYST"},
        ),
    ],
)
async def test_a_mutation_writes_exactly_one_audit_row(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
    action: str,
    method: str,
    suffix: str,
    body: dict[str, Any],
) -> None:
    response = await client.request(
        method, f"/api/v1/orgs/{owner.org_id}{suffix}", json=body, headers=owner.headers
    )
    assert response.status_code in (200, 201), response.text

    row = await _audit_row(session_factory, owner, action)
    assert row.organization_id == owner.org_id
    assert row.actor_id == owner.user_id
    assert row.actor_type == "user"
    assert row.after is not None


async def test_updating_the_organization_records_before_and_after(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
) -> None:
    original = (await client.get(f"/api/v1/orgs/{owner.org_id}", headers=owner.headers)).json()[
        "name"
    ]

    await client.patch(
        f"/api/v1/orgs/{owner.org_id}", json={"name": "After Rename"}, headers=owner.headers
    )

    row = await _audit_row(session_factory, owner, "organization.updated")
    assert row.before == {"name": original}
    assert row.after == {"name": "After Rename"}


@pytest.mark.parametrize("field", ["plan", "kill_switch_state", "slug", "id"])
async def test_the_organization_patch_refuses_fields_it_does_not_own(
    client: httpx.AsyncClient, owner: Actor, field: str
) -> None:
    # silently ignoring these is how a client ships a feature that never worked
    response = await client.patch(
        f"/api/v1/orgs/{owner.org_id}",
        json={"name": "Fine", field: "ENTERPRISE"},
        headers=owner.headers,
    )

    assert response.status_code == 422
    assert any(field in error["loc"] for error in response.json()["errors"])


async def test_onboarding_persists_the_answers_and_is_idempotent(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
) -> None:
    url = f"/api/v1/orgs/{owner.org_id}/workspaces/{owner.workspace_id}/onboarding"

    first = await client.put(url, json=ONBOARDING_BODY, headers=owner.headers)
    assert first.status_code == 200, first.text
    second = await client.put(url, json=ONBOARDING_BODY, headers=owner.headers)

    assert second.status_code == 200
    body = second.json()
    assert body["objective"] == "paper_trading"
    assert body["settings"]["monitored_exchanges"] == ["binance", "bybit"]
    # money is a string in JSONB: json has one numeric type and it is a float
    assert Decimal(body["settings"]["default_initial_capital"]) == Decimal("25000.5")
    assert body["default_risk_profile_id"] is not None
    # the completion timestamp is a fact about when onboarding finished; a
    # re-save from the settings screen months later must not rewrite it
    assert body["onboarding_completed_at"] == first.json()["onboarding_completed_at"]

    assert owner.org_id is not None
    async with tenant_session(session_factory, owner.org_id, owner.user_id) as session:
        workspace = await session.get(Workspace, owner.workspace_id)
    assert workspace is not None
    assert workspace.settings["risk_preset"] == "conservative"

    me = (await client.get("/api/v1/me", headers=owner.headers)).json()
    assert me["memberships"][0]["onboarding"]["completed"] is True


async def test_onboarding_rejects_an_unknown_exchange_code(
    client: httpx.AsyncClient, owner: Actor
) -> None:
    body = {**ONBOARDING_BODY, "monitored_exchanges": ["binance", "not-an-exchange"]}

    response = await client.put(
        f"/api/v1/orgs/{owner.org_id}/workspaces/{owner.workspace_id}/onboarding",
        json=body,
        headers=owner.headers,
    )

    assert response.status_code == 422
    assert "not-an-exchange" in response.json()["detail"]


async def test_onboarding_rejects_capital_below_the_sizing_floor(
    client: httpx.AsyncClient, owner: Actor
) -> None:
    body = {**ONBOARDING_BODY, "virtual_capital": "999.99"}

    response = await client.put(
        f"/api/v1/orgs/{owner.org_id}/workspaces/{owner.workspace_id}/onboarding",
        json=body,
        headers=owner.headers,
    )

    assert response.status_code == 422


async def test_the_last_owner_cannot_be_demoted(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
) -> None:
    response = await client.patch(
        f"/api/v1/orgs/{owner.org_id}/members/{owner.user_id}",
        json={"role": "ADMIN"},
        headers=owner.headers,
    )

    assert response.status_code == 409
    assert "last owner" in response.json()["detail"].lower()
    # and nothing was audited, because nothing happened
    assert await _audit_count(session_factory, owner, "member.role_changed") == 0


async def test_the_last_owner_cannot_be_removed(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
) -> None:
    response = await client.delete(
        f"/api/v1/orgs/{owner.org_id}/members/{owner.user_id}", headers=owner.headers
    )

    assert response.status_code == 409
    assert await _audit_count(session_factory, owner, "member.removed") == 0
    members = (
        await client.get(f"/api/v1/orgs/{owner.org_id}/members", headers=owner.headers)
    ).json()
    assert len(members["items"]) == 1


async def test_a_second_owner_makes_the_first_demotable(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
    make_actor: Callable[[str], Actor],
) -> None:
    joiner = await _join(client, owner, make_actor, OrganizationRole.OWNER)

    response = await client.patch(
        f"/api/v1/orgs/{owner.org_id}/members/{owner.user_id}",
        json={"role": "ADMIN"},
        headers=owner.headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"
    row = await _audit_row(session_factory, owner, "member.role_changed")
    assert row.before == {
        "user_id": str(owner.user_id),
        "role": "OWNER",
        "status": MemberStatus.ACTIVE.value,
    }
    assert row.after == {"user_id": str(owner.user_id), "role": "ADMIN"}
    assert joiner.user_id is not None


async def test_removing_a_member_is_audited_once(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    owner: Actor,
    make_actor: Callable[[str], Actor],
) -> None:
    joiner = await _join(client, owner, make_actor, OrganizationRole.ANALYST)

    response = await client.delete(
        f"/api/v1/orgs/{owner.org_id}/members/{joiner.user_id}", headers=owner.headers
    )

    assert response.status_code == 204
    row = await _audit_row(session_factory, owner, "member.removed")
    assert row.after == {"user_id": str(joiner.user_id), "removed": True}


async def test_a_viewer_cannot_change_roles_but_can_read_the_roster(
    client: httpx.AsyncClient, owner: Actor, make_actor: Callable[[str], Actor]
) -> None:
    viewer = await _join(client, owner, make_actor, OrganizationRole.VIEWER)

    read = await client.get(f"/api/v1/orgs/{owner.org_id}/members", headers=viewer.headers)
    write = await client.patch(
        f"/api/v1/orgs/{owner.org_id}/members/{owner.user_id}",
        json={"role": "VIEWER"},
        headers=viewer.headers,
    )
    audit = await client.get(f"/api/v1/orgs/{owner.org_id}/audit", headers=viewer.headers)

    assert read.status_code == 200
    # 403, not 404: the viewer is a member, so the organization's existence is
    # not a secret from them — only the action is refused
    assert write.status_code == 403
    assert audit.status_code == 403


async def _join(
    client: httpx.AsyncClient,
    owner: Actor,
    make_actor: Callable[[str], Actor],
    role: OrganizationRole,
) -> Actor:
    """Invite a fresh actor into ``owner``'s organization and accept it."""
    joiner = make_actor(f"joiner-{uuid.uuid4().hex[:8]}")
    created = await client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": joiner.email, "role": role.value},
        headers=owner.headers,
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    accepted = await client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)
    assert accepted.status_code == 200, accepted.text
    me = (await client.get("/api/v1/me", headers=joiner.headers)).json()
    joiner.user_id = uuid.UUID(me["user"]["id"])
    joiner.org_id = owner.org_id
    return joiner
