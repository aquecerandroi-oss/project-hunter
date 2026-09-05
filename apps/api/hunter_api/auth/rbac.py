"""Role-based access control and the tenant-route dependencies — SECURITY.md §2/§3.

Every route under ``/api/v1/orgs/{org_id}`` declares a minimum role. Two
distinct failures come out of that, and the difference is deliberate:

- **not a member** → 404. An organization id you have no membership of must be
  indistinguishable from one that does not exist, or the API becomes an oracle
  for "does this tenant exist" (SECURITY.md §3.3).
- **member, role too low** → 403. You already know the organization exists, so
  saying "not enough privilege" leaks nothing and is the only answer that lets
  you do something about it (ask an admin).

An ``invited`` or ``suspended`` membership is not a membership here: it takes
the 404 path. A suspended member keeping read access would defeat the point of
suspending them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request, status

from hunter_api.auth.clerk import InvalidTokenError
from hunter_api.auth.principal import Principal
from hunter_api.errors import HunterError
from hunter_api.middleware.rate_limit import enforce_principal_limit
from hunter_core.domain.enums import OrganizationRole

if TYPE_CHECKING:
    from collections.abc import Callable

    from hunter_api.auth.clerk import AuthProvider
    from hunter_api.auth.principal import PrincipalResolver

ROLE_ORDER: tuple[OrganizationRole, ...] = (
    OrganizationRole.VIEWER,
    OrganizationRole.ANALYST,
    OrganizationRole.TRADER,
    OrganizationRole.ADMIN,
    OrganizationRole.OWNER,
)
"""Least to most privileged. The RBAC matrix in SECURITY.md §2 is a strict
ladder — every capability of a lower role belongs to every higher one — so a
single rank comparison is the whole model, with no per-capability table to
drift out of sync with the routes."""

_RANK = {role: rank for rank, role in enumerate(ROLE_ORDER)}

BEARER_PREFIX = "bearer "


class OrganizationNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="organization-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )


class InsufficientRoleError(HunterError):
    def __init__(self, minimum: OrganizationRole) -> None:
        super().__init__(
            type_slug="insufficient-role",
            title="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires the {minimum.value} role or higher.",
        )


@dataclass(frozen=True, slots=True)
class OrgContext:
    """The organization this request acts for, and with what authority."""

    org_id: uuid.UUID
    role: OrganizationRole
    principal: Principal


def at_least(role: OrganizationRole, minimum: OrganizationRole) -> bool:
    """Whether ``role`` ranks at or above ``minimum`` on the SECURITY.md §2 ladder."""
    return _RANK[role] >= _RANK[minimum]


def bearer_token(request: Request) -> str:
    """The bearer token, or 401. Never logged, never echoed."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith(BEARER_PREFIX):
        raise InvalidTokenError
    token = header[len(BEARER_PREFIX) :].strip()
    if not token:
        raise InvalidTokenError
    return token


async def get_principal(request: Request) -> Principal:
    """Verify the bearer token, resolve the caller, and spend their budget.

    Both collaborators come off ``app.state`` (built once in ``create_app``'s
    lifespan) rather than being constructed per request: the JWKS cache lives
    inside the provider, and a per-request provider would re-fetch Clerk's keys
    on every call.

    The per-principal rate limit is applied here rather than declared on each
    route, because this is the one point every authenticated request passes
    through: ``require_org`` reaches it through ``get_org_context``, and so
    does every non-tenant route. A route added next year gets the limit without
    anyone remembering to ask for it.
    """
    provider: AuthProvider = request.app.state.auth_provider
    resolver: PrincipalResolver = request.app.state.principal_resolver
    principal = await resolver.resolve(await provider.verify(bearer_token(request)))
    request.state.principal_id = str(principal.user_id)
    await enforce_principal_limit(request, str(principal.user_id))
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def get_org_context(
    org_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> OrgContext:
    """Membership for the ``{org_id}`` in the path — 404 when there is none.

    FastAPI caches this per request, so the several dependencies that need it
    (the role check, the tenant session, the audit context) resolve it once.
    """
    membership = principal.membership(org_id)
    if membership is None:
        raise OrganizationNotFoundError
    request.state.org_id = str(org_id)
    request.state.principal_id = str(principal.user_id)
    return OrgContext(org_id=org_id, role=membership.role, principal=principal)


CurrentOrg = Annotated[OrgContext, Depends(get_org_context)]


def require_org(minimum: OrganizationRole) -> Callable[[OrgContext], OrgContext]:
    """A dependency asserting the caller holds at least ``minimum`` in this org.

    Returned as a factory so each route spells its own floor
    (``Depends(require_org(OrganizationRole.ADMIN))``) — the declaration lives
    next to the handler it guards, where a reviewer reads it.
    """

    def dependency(context: CurrentOrg) -> OrgContext:
        if not at_least(context.role, minimum):
            raise InsufficientRoleError(minimum)
        return context

    return dependency
