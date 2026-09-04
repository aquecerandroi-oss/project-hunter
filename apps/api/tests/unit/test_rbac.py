"""Role ordering and the ``require_org`` dependency — SECURITY.md §2 and §3.

The 404-vs-403 split is the security-relevant part: an organization you are
not a member of must be indistinguishable from one that does not exist, while
an organization you *are* in may honestly tell you your role is too low.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from starlette.requests import Request

from hunter_api.auth.principal import Membership, Principal
from hunter_api.auth.rbac import (
    ROLE_ORDER,
    InsufficientRoleError,
    OrganizationNotFoundError,
    OrgContext,
    at_least,
    get_org_context,
    require_org,
)
from hunter_core.domain.enums import MemberStatus, OrganizationRole

pytestmark = pytest.mark.unit

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
USER = uuid.uuid4()


def _request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/orgs",
        "headers": [],
        "state": {},
    }
    return Request(scope)


def _principal(*memberships: Membership) -> Principal:
    return Principal(
        user_id=USER,
        external_auth_id="user_FAKE_clerk_id",
        email="member@example.test",
        memberships=tuple(memberships),
    )


def _member(
    org_id: uuid.UUID,
    role: OrganizationRole,
    status: MemberStatus = MemberStatus.ACTIVE,
) -> Membership:
    return Membership(org_id=org_id, role=role, status=status)


def test_roles_are_ordered_from_viewer_to_owner() -> None:
    assert list(ROLE_ORDER) == [
        OrganizationRole.VIEWER,
        OrganizationRole.ANALYST,
        OrganizationRole.TRADER,
        OrganizationRole.ADMIN,
        OrganizationRole.OWNER,
    ]


@pytest.mark.parametrize(
    ("role", "minimum", "expected"),
    [
        (OrganizationRole.OWNER, OrganizationRole.VIEWER, True),
        (OrganizationRole.OWNER, OrganizationRole.OWNER, True),
        (OrganizationRole.ADMIN, OrganizationRole.OWNER, False),
        (OrganizationRole.TRADER, OrganizationRole.ADMIN, False),
        (OrganizationRole.TRADER, OrganizationRole.ANALYST, True),
        (OrganizationRole.ANALYST, OrganizationRole.TRADER, False),
        (OrganizationRole.VIEWER, OrganizationRole.VIEWER, True),
    ],
)
def test_at_least_compares_by_rank(
    role: OrganizationRole, minimum: OrganizationRole, expected: bool
) -> None:
    assert at_least(role, minimum) is expected


async def test_a_member_gets_an_org_context() -> None:
    request = _request()
    principal = _principal(_member(ORG_A, OrganizationRole.TRADER))

    context = await get_org_context(ORG_A, request, principal)

    assert context == OrgContext(org_id=ORG_A, role=OrganizationRole.TRADER, principal=principal)
    # the rate limiter and the log context read these off request.state
    assert request.state.org_id == str(ORG_A)
    assert request.state.principal_id == str(USER)


async def test_another_organizations_id_is_a_404_not_a_403() -> None:
    principal = _principal(_member(ORG_A, OrganizationRole.OWNER))

    with pytest.raises(OrganizationNotFoundError) as exc_info:
        await get_org_context(ORG_B, _request(), principal)

    assert exc_info.value.status_code == 404
    # nothing in the response may hint that ORG_B exists
    assert str(ORG_B) not in str(exc_info.value.detail)


async def test_a_non_member_leaves_request_state_untouched() -> None:
    request = _request()
    principal = _principal(_member(ORG_A, OrganizationRole.OWNER))

    with pytest.raises(OrganizationNotFoundError):
        await get_org_context(ORG_B, request, principal)

    assert getattr(request.state, "org_id", None) is None


@pytest.mark.parametrize("status", [MemberStatus.INVITED, MemberStatus.SUSPENDED])
async def test_a_membership_that_is_not_active_is_a_404(status: MemberStatus) -> None:
    principal = _principal(_member(ORG_A, OrganizationRole.OWNER, status))

    with pytest.raises(OrganizationNotFoundError):
        await get_org_context(ORG_A, _request(), principal)


def test_a_role_below_the_minimum_is_a_403() -> None:
    principal = _principal(_member(ORG_A, OrganizationRole.ANALYST))
    context = OrgContext(org_id=ORG_A, role=OrganizationRole.ANALYST, principal=principal)

    with pytest.raises(InsufficientRoleError) as exc_info:
        require_org(OrganizationRole.ADMIN)(context)

    # you are in this organization, so "forbidden" leaks nothing you did not
    # already know — unlike the membership check above
    assert exc_info.value.status_code == 403


def test_a_role_at_or_above_the_minimum_passes_the_context_through() -> None:
    principal = _principal(_member(ORG_A, OrganizationRole.ADMIN))
    context = OrgContext(org_id=ORG_A, role=OrganizationRole.ADMIN, principal=principal)

    assert require_org(OrganizationRole.ADMIN)(context) is context
    assert require_org(OrganizationRole.VIEWER)(context) is context


def test_principal_membership_lookup_ignores_inactive_rows() -> None:
    principal = _principal(
        _member(ORG_A, OrganizationRole.OWNER, MemberStatus.SUSPENDED),
        _member(ORG_B, OrganizationRole.VIEWER),
    )

    assert principal.membership(ORG_A) is None
    assert principal.membership(ORG_B) is not None
    assert [m.org_id for m in principal.active_memberships()] == [ORG_B]
