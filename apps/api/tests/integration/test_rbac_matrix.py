"""RBAC, endpoint by endpoint — SECURITY.md §2.

The ladder is ``VIEWER < ANALYST < TRADER < ADMIN < OWNER`` (``auth/rbac.py``,
``ROLE_ORDER``) and every tenant route declares a minimum rank on that ladder
via ``require_org(minimum)``. The table below is the explicit, hand-written
mapping from route to minimum role — copied from the routers, not derived from
them — so that a route whose declared minimum silently changes shows up here
as a failing assertion instead of a matrix that quietly follows the code.

Two properties, each parametrized over the whole table:

1. the rank immediately *below* the minimum is refused with 403 problem+json
   (never 404 — the caller is already a member, so the organization's
   existence is not a secret from them, SECURITY.md §3.3);
2. the minimum rank itself is never refused with 403 (it may still be 404,
   409 or 422 for reasons that have nothing to do with role).

``test_the_table_covers_every_tenant_route`` fails the moment a new operation
appears under ``/orgs/{org_id}`` in the live OpenAPI schema without a matching
line here, exactly like ``test_isolation.py``'s equivalent guard.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest

from hunter_api.auth.rbac import ROLE_ORDER
from hunter_core.domain.enums import OrganizationRole

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from fastapi import FastAPI

pytestmark = pytest.mark.integration

ONBOARDING_BODY: dict[str, Any] = {
    "objective": "paper_trading",
    "virtual_capital": "10000",
    "risk_preset": "balanced",
    "monitored_exchanges": [],
}

# (route id, HTTP method — for the assertion message only, the dispatcher
# below knows the real one — minimum role). Copied by hand from
# organizations.py, members.py, invitations.py, workspaces.py and audit.py.
ROUTES: list[tuple[str, str, OrganizationRole]] = [
    ("org.read", "GET", OrganizationRole.VIEWER),
    ("org.update", "PATCH", OrganizationRole.ADMIN),
    ("members.list", "GET", OrganizationRole.VIEWER),
    ("members.update_role", "PATCH", OrganizationRole.OWNER),
    ("members.delete", "DELETE", OrganizationRole.OWNER),
    ("invitations.list", "GET", OrganizationRole.ADMIN),
    ("invitations.create", "POST", OrganizationRole.ADMIN),
    ("invitations.delete", "DELETE", OrganizationRole.ADMIN),
    ("workspaces.list", "GET", OrganizationRole.VIEWER),
    ("workspaces.create", "POST", OrganizationRole.ADMIN),
    ("workspaces.read", "GET", OrganizationRole.VIEWER),
    ("workspaces.update", "PATCH", OrganizationRole.ADMIN),
    ("workspaces.onboarding", "PUT", OrganizationRole.ADMIN),
    ("audit.list", "GET", OrganizationRole.ADMIN),
]


def _role_below(minimum: OrganizationRole) -> OrganizationRole | None:
    """The next rank down the ladder, or ``None`` for the floor (``VIEWER``)."""
    index = ROLE_ORDER.index(minimum)
    return ROLE_ORDER[index - 1] if index > 0 else None


class OrgRoles:
    """One organization with one active member at every role on the ladder.

    ``second_owner`` exists so the OWNER-only routes (demote/remove a member)
    have someone to call as *exactly* OWNER without hitting the "last owner"
    guard, which answers 409 regardless of role and would be indistinguishable
    from a role failure here.
    """

    def __init__(
        self,
        owner: Actor,
        second_owner: Actor,
        admin: Actor,
        trader: Actor,
        analyst: Actor,
        viewer: Actor,
    ) -> None:
        self.owner = owner
        self._by_role = {
            OrganizationRole.OWNER: second_owner,
            OrganizationRole.ADMIN: admin,
            OrganizationRole.TRADER: trader,
            OrganizationRole.ANALYST: analyst,
            OrganizationRole.VIEWER: viewer,
        }

    def actor(self, role: OrganizationRole) -> Actor:
        return self._by_role[role]


async def _join(
    client: httpx.AsyncClient,
    owner: Actor,
    make_actor: Callable[[str], Actor],
    role: OrganizationRole,
) -> Actor:
    joiner = make_actor(f"rbac-{role.value.lower()}-{uuid.uuid4().hex[:8]}")
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
    joiner.workspace_id = owner.workspace_id
    return joiner


@pytest.fixture
async def org_roles(client: httpx.AsyncClient, make_actor: Callable[[str], Actor]) -> OrgRoles:
    unique = uuid.uuid4().hex[:8]
    owner = await create_org(client, make_actor(f"rbac-owner-{unique}"), f"RBAC {unique}")
    second_owner = await _join(client, owner, make_actor, OrganizationRole.OWNER)
    admin = await _join(client, owner, make_actor, OrganizationRole.ADMIN)
    trader = await _join(client, owner, make_actor, OrganizationRole.TRADER)
    analyst = await _join(client, owner, make_actor, OrganizationRole.ANALYST)
    viewer = await _join(client, owner, make_actor, OrganizationRole.VIEWER)
    return OrgRoles(owner, second_owner, admin, trader, analyst, viewer)


async def _call(
    client: httpx.AsyncClient, org: OrgRoles, kind: str, caller: Actor
) -> httpx.Response:
    org_id = org.owner.org_id
    workspace_id = org.owner.workspace_id
    assert org_id is not None and workspace_id is not None

    if kind == "org.read":
        return await client.get(f"/api/v1/orgs/{org_id}", headers=caller.headers)
    if kind == "org.update":
        return await client.patch(
            f"/api/v1/orgs/{org_id}", json={"name": "RBAC Renamed"}, headers=caller.headers
        )
    if kind == "members.list":
        return await client.get(f"/api/v1/orgs/{org_id}/members", headers=caller.headers)
    if kind == "members.update_role":
        target = org.actor(OrganizationRole.VIEWER)
        assert target.user_id is not None
        return await client.patch(
            f"/api/v1/orgs/{org_id}/members/{target.user_id}",
            json={"role": "ANALYST"},
            headers=caller.headers,
        )
    if kind == "members.delete":
        target = org.actor(OrganizationRole.VIEWER)
        assert target.user_id is not None
        return await client.delete(
            f"/api/v1/orgs/{org_id}/members/{target.user_id}", headers=caller.headers
        )
    if kind == "invitations.list":
        return await client.get(f"/api/v1/orgs/{org_id}/invitations", headers=caller.headers)
    if kind == "invitations.create":
        email = f"rbac-invite-{uuid.uuid4().hex[:8]}@example.test"
        return await client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": email, "role": "VIEWER"},
            headers=caller.headers,
        )
    if kind == "invitations.delete":
        email = f"rbac-revoke-{uuid.uuid4().hex[:8]}@example.test"
        created = await client.post(
            f"/api/v1/orgs/{org_id}/invitations",
            json={"email": email, "role": "VIEWER"},
            headers=org.owner.headers,
        )
        assert created.status_code == 201, created.text
        invitation_id = created.json()["id"]
        return await client.delete(
            f"/api/v1/orgs/{org_id}/invitations/{invitation_id}", headers=caller.headers
        )
    if kind == "workspaces.list":
        return await client.get(f"/api/v1/orgs/{org_id}/workspaces", headers=caller.headers)
    if kind == "workspaces.create":
        return await client.post(
            f"/api/v1/orgs/{org_id}/workspaces",
            json={"name": f"RBAC WS {uuid.uuid4().hex[:8]}"},
            headers=caller.headers,
        )
    if kind == "workspaces.read":
        return await client.get(
            f"/api/v1/orgs/{org_id}/workspaces/{workspace_id}", headers=caller.headers
        )
    if kind == "workspaces.update":
        return await client.patch(
            f"/api/v1/orgs/{org_id}/workspaces/{workspace_id}",
            json={"name": "RBAC WS Renamed"},
            headers=caller.headers,
        )
    if kind == "workspaces.onboarding":
        return await client.put(
            f"/api/v1/orgs/{org_id}/workspaces/{workspace_id}/onboarding",
            json=ONBOARDING_BODY,
            headers=caller.headers,
        )
    if kind == "audit.list":
        return await client.get(f"/api/v1/orgs/{org_id}/audit", headers=caller.headers)
    raise AssertionError(f"unhandled route kind {kind!r}")  # pragma: no cover


async def test_the_table_covers_every_tenant_route(app: FastAPI) -> None:
    """A route added under ``/orgs/{org_id}`` without a line above would slip
    past the matrix — same guard as ``test_isolation.py``, same count.
    """
    paths = cast("dict[str, dict[str, Any]]", app.openapi()["paths"])
    operations = [
        (method.upper(), path)
        for path, item in paths.items()
        if path.startswith("/api/v1/orgs/{org_id}")
        for method in item
    ]

    assert len(ROUTES) == len(operations), sorted(operations)


@pytest.mark.parametrize(
    ("kind", "method", "minimum"),
    [
        (kind, method, minimum)
        for kind, method, minimum in ROUTES
        if _role_below(minimum) is not None
    ],
    ids=[kind for kind, _, minimum in ROUTES if _role_below(minimum) is not None],
)
async def test_a_role_below_the_minimum_is_403(
    client: httpx.AsyncClient,
    org_roles: OrgRoles,
    kind: str,
    method: str,
    minimum: OrganizationRole,
) -> None:
    below = _role_below(minimum)
    assert below is not None
    caller = org_roles.actor(below)

    response = await _call(client, org_roles, kind, caller)

    assert response.status_code == 403, (
        f"{method} {kind} as {below.value} -> {response.status_code}"
    )
    assert response.headers["content-type"].startswith("application/problem+json")
    assert minimum.value in response.json()["detail"]


@pytest.mark.parametrize(
    ("kind", "method", "minimum"),
    [(kind, method, minimum) for kind, method, minimum in ROUTES],
    ids=[kind for kind, _, _ in ROUTES],
)
async def test_the_minimum_role_is_never_refused_as_forbidden(
    client: httpx.AsyncClient,
    org_roles: OrgRoles,
    kind: str,
    method: str,
    minimum: OrganizationRole,
) -> None:
    caller = org_roles.actor(minimum)

    response = await _call(client, org_roles, kind, caller)

    assert response.status_code != 403, (
        f"{method} {kind} as exactly {minimum.value} -> 403 {response.text}"
    )
