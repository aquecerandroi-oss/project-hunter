"""``/api/v1/orgs/{org_id}/workspaces`` — workspaces and the onboarding PUT."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, audit_kwargs
from hunter_api.repositories.base import encode_cursor
from hunter_api.repositories.workspaces import WorkspaceRepository
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.workspaces import (
    OnboardingUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from hunter_api.services.workspaces import (
    WorkspaceNotFoundError,
    complete_onboarding,
    completed_at,
    create_workspace,
    update_workspace,
)
from hunter_core.domain.enums import OrganizationRole

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.db.models.identity import Workspace

router = APIRouter(prefix="/api/v1/orgs/{org_id}/workspaces", tags=["workspaces"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
AdminOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.ADMIN))]


@router.get("", response_model=CursorPage[WorkspaceOut], summary="List workspaces")
async def list_workspaces(
    context: ViewerOrg,
    session: OrgSession,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    cursor: str | None = None,
) -> CursorPage[WorkspaceOut]:
    rows, size = await WorkspaceRepository(session, context.org_id).page(limit=limit, cursor=cursor)
    items = [_out(row) for row in rows]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if len(items) == size else None
    return CursorPage(items=items, next_cursor=next_cursor)


@router.post(
    "",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create(
    request: Request, context: AdminOrg, session: OrgSession, payload: WorkspaceCreate
) -> WorkspaceOut:
    created = await create_workspace(
        session=session,
        org_id=context.org_id,
        payload=payload,
        **audit_kwargs(request, context),
    )
    return await _read(session, context, uuid.UUID(created["id"]))


@router.get("/{workspace_id}", response_model=WorkspaceOut, summary="Read a workspace")
async def read(context: AdminOrg, session: OrgSession, workspace_id: uuid.UUID) -> WorkspaceOut:
    return await _read(session, context, workspace_id)


@router.patch("/{workspace_id}", response_model=WorkspaceOut, summary="Update a workspace")
async def update(
    request: Request,
    context: AdminOrg,
    session: OrgSession,
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
) -> WorkspaceOut:
    await update_workspace(
        session=session,
        org_id=context.org_id,
        workspace_id=workspace_id,
        payload=payload,
        **audit_kwargs(request, context, entity_id=workspace_id),
    )
    return await _read(session, context, workspace_id)


@router.put(
    "/{workspace_id}/onboarding",
    response_model=WorkspaceOut,
    summary="Save the onboarding answers (idempotent)",
)
async def onboarding(
    request: Request,
    context: AdminOrg,
    session: OrgSession,
    workspace_id: uuid.UUID,
    payload: OnboardingUpdate,
) -> WorkspaceOut:
    await complete_onboarding(
        session=session,
        org_id=context.org_id,
        workspace_id=workspace_id,
        payload=payload,
        actor=context.principal.user_id,
        **audit_kwargs(request, context, entity_id=workspace_id),
    )
    return await _read(session, context, workspace_id)


async def _read(
    session: AsyncSession, context: OrgContext, workspace_id: uuid.UUID
) -> WorkspaceOut:
    workspace = await WorkspaceRepository(session, context.org_id).get(workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError
    return _out(workspace)


def _out(workspace: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        organization_id=workspace.organization_id,
        name=workspace.name,
        objective=workspace.objective,
        default_risk_profile_id=workspace.default_risk_profile_id,
        settings=dict(workspace.settings),
        created_at=workspace.created_at,
        onboarding_completed_at=completed_at(workspace.settings),
    )
