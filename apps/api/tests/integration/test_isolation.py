"""Tenant isolation, endpoint by endpoint — SECURITY.md §3.

Two rules, both parametrized over the whole tenant surface so a route added
later without a membership check fails here rather than in production:

1. a member of organization A calling any endpoint with organization B's id
   gets **404**, never 403. 403 would confirm that B exists, turning the API
   into an existence oracle for every organization id anyone cares to try;
2. B's rows never appear in A's lists, even when the reader is an OWNER.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from fastapi import FastAPI

pytestmark = pytest.mark.integration

ANY_UUID = uuid.uuid4()


def _tenant_routes(org_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[Any]:
    """Every route under ``/orgs/{org_id}``, with a valid-looking body."""
    base = f"/api/v1/orgs/{org_id}"
    return [
        ("GET", base, None),
        ("PATCH", base, {"name": "Renamed By An Outsider"}),
        ("GET", f"{base}/members", None),
        ("PATCH", f"{base}/members/{user_id}", {"role": "VIEWER"}),
        ("DELETE", f"{base}/members/{user_id}", None),
        ("GET", f"{base}/invitations", None),
        ("POST", f"{base}/invitations", {"email": "intruder@example.test", "role": "ADMIN"}),
        ("DELETE", f"{base}/invitations/{ANY_UUID}", None),
        ("GET", f"{base}/workspaces", None),
        ("POST", f"{base}/workspaces", {"name": "Intruder Workspace"}),
        ("GET", f"{base}/workspaces/{workspace_id}", None),
        ("PATCH", f"{base}/workspaces/{workspace_id}", {"name": "Renamed"}),
        (
            "PUT",
            f"{base}/workspaces/{workspace_id}/onboarding",
            {
                "objective": "paper_trading",
                "virtual_capital": "10000",
                "risk_preset": "balanced",
                "monitored_exchanges": [],
            },
        ),
        ("GET", f"{base}/audit", None),
    ]


@pytest.fixture
async def two_orgs(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> tuple[Actor, Actor]:
    unique = uuid.uuid4().hex[:8]
    a = await create_org(client, make_actor(f"iso-a-{unique}"), f"Isolation A {unique}")
    b = await create_org(client, make_actor(f"iso-b-{unique}"), f"Isolation B {unique}")
    return a, b


@pytest.mark.parametrize("index", range(14))
async def test_every_tenant_route_answers_404_for_another_organization(
    client: httpx.AsyncClient, two_orgs: tuple[Actor, Actor], index: int
) -> None:
    a, b = two_orgs
    assert b.org_id is not None and b.workspace_id is not None and b.user_id is not None
    method, url, body = _tenant_routes(b.org_id, b.workspace_id, b.user_id)[index]

    response = await client.request(method, url, json=body, headers=a.headers)

    assert response.status_code == 404, f"{method} {url} -> {response.status_code}"
    assert response.headers["content-type"].startswith("application/problem+json")
    # the body must not distinguish "exists but forbidden" from "does not exist"
    assert "Organization not found" in response.json()["detail"]


async def test_the_route_list_covers_every_tenant_route_the_app_serves(app: FastAPI) -> None:
    """A route added under ``/orgs/{org_id}`` without a line above would slip
    past the matrix, so the count is asserted against the live OpenAPI schema.
    """
    paths = cast("dict[str, dict[str, Any]]", app.openapi()["paths"])
    operations = [
        (method.upper(), path)
        for path, item in paths.items()
        if path.startswith("/api/v1/orgs/{org_id}")
        for method in item
    ]

    assert len(operations) == 14, sorted(operations)


async def test_a_nonexistent_organization_is_the_same_404(
    client: httpx.AsyncClient, two_orgs: tuple[Actor, Actor]
) -> None:
    a, _ = two_orgs

    response = await client.get(f"/api/v1/orgs/{uuid.uuid4()}", headers=a.headers)

    assert response.status_code == 404


async def test_lists_never_leak_another_organizations_rows(
    client: httpx.AsyncClient, two_orgs: tuple[Actor, Actor]
) -> None:
    a, b = two_orgs
    await client.post(
        f"/api/v1/orgs/{b.org_id}/invitations",
        json={"email": "b-invitee@example.test", "role": "VIEWER"},
        headers=b.headers,
    )
    await client.post(
        f"/api/v1/orgs/{b.org_id}/workspaces",
        json={"name": "B Only Workspace"},
        headers=b.headers,
    )

    members = (await client.get(f"/api/v1/orgs/{a.org_id}/members", headers=a.headers)).json()
    invitations = (
        await client.get(f"/api/v1/orgs/{a.org_id}/invitations", headers=a.headers)
    ).json()
    workspaces = (await client.get(f"/api/v1/orgs/{a.org_id}/workspaces", headers=a.headers)).json()
    audit = (await client.get(f"/api/v1/orgs/{a.org_id}/audit", headers=a.headers)).json()

    assert [m["user_id"] for m in members["items"]] == [str(a.user_id)]
    assert invitations["items"] == []
    assert [w["id"] for w in workspaces["items"]] == [str(a.workspace_id)]
    # the audit query runs under app.current_org, so B's rows are not merely
    # filtered in Python — Postgres never returns them
    assert audit["items"], "A's own sign-up must be in A's trail"
    assert all(row["actor_id"] in (str(a.user_id), None) for row in audit["items"])
    assert all(row["action"] == "organization.created" for row in audit["items"])


async def test_me_lists_only_the_callers_own_organizations(
    client: httpx.AsyncClient, two_orgs: tuple[Actor, Actor]
) -> None:
    a, b = two_orgs

    body = (await client.get("/api/v1/me", headers=a.headers)).json()

    org_ids = {m["organization"]["id"] for m in body["memberships"]}
    assert org_ids == {str(a.org_id)}
    assert str(b.org_id) not in org_ids
