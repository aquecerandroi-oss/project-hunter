"""``/api/v1/orgs`` — create, read and rename an organization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request, status

from hunter_api.auth.rbac import (
    CurrentPrincipal,
    OrganizationNotFoundError,
    OrgContext,
    require_org,
)
from hunter_api.deps import OrgSession, audit_kwargs, get_session_factory
from hunter_api.repositories.organizations import OrganizationRepository
from hunter_api.schemas.organizations import (
    OrganizationCreate,
    OrganizationCreated,
    OrganizationOut,
    OrganizationUpdate,
)
from hunter_api.services.organizations import create_organization, rename_organization
from hunter_core.db.models.identity import Organization
from hunter_core.domain.enums import OrganizationRole

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
AdminOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.ADMIN))]


@router.post(
    "",
    response_model=OrganizationCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization (sign-up)",
)
async def create(
    request: Request, principal: CurrentPrincipal, payload: OrganizationCreate
) -> OrganizationCreated:
    created: dict[str, Any] = await create_organization(
        get_session_factory(request),
        payload=payload,
        principal=principal,
        audit=audit_kwargs(request, None, actor_id=principal.user_id),
    )
    return OrganizationCreated(**created)


@router.get("/{org_id}", response_model=OrganizationOut, summary="Read an organization")
async def read(context: ViewerOrg, session: OrgSession) -> OrganizationOut:
    return _out(await _require(session, context))


@router.patch("/{org_id}", response_model=OrganizationOut, summary="Rename an organization")
async def update(
    request: Request, context: AdminOrg, session: OrgSession, payload: OrganizationUpdate
) -> OrganizationOut:
    await rename_organization(
        session=session,
        org_id=context.org_id,
        name=payload.name,
        **audit_kwargs(request, context, entity_id=context.org_id),
    )
    organization = await _require(session, context)
    await session.refresh(organization)
    return _out(organization)


async def _require(session: AsyncSession, context: OrgContext) -> Organization:
    organization = await OrganizationRepository(session, context.org_id).get()
    if organization is None or organization.deleted_at is not None:
        # RLS makes this unreachable for a member of a live organization; a
        # deleted one gets the same answer as one you are not a member of
        raise OrganizationNotFoundError
    return organization


def _out(organization: Organization) -> OrganizationOut:
    return OrganizationOut.model_validate(organization, from_attributes=True)
