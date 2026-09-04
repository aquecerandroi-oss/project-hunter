"""``/api/v1/orgs/{org_id}/members`` — who is in the organization.

Reading the roster is VIEWER (everyone in the org needs to know who else is);
changing a role or removing someone is OWNER, per SECURITY.md §2's "Membros,
convites, papéis" row — ADMIN may manage invitations but may not promote to
OWNER or remove one, and rather than encode "ADMIN except for OWNER rows" in
two places, M0 keeps both mutations at OWNER.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, audit_kwargs
from hunter_api.repositories.base import encode_cursor
from hunter_api.repositories.organizations import MemberRepository
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.organizations import MemberOut, MemberRoleUpdate
from hunter_api.services.members import MemberNotFoundError, change_member_role, remove_member
from hunter_core.domain.enums import OrganizationRole

if TYPE_CHECKING:
    from sqlalchemy import Row
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}/members", tags=["members"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
OwnerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.OWNER))]


@router.get("", response_model=CursorPage[MemberOut], summary="List members")
async def list_members(
    context: ViewerOrg,
    session: OrgSession,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    cursor: str | None = None,
) -> CursorPage[MemberOut]:
    rows, size = await MemberRepository(session, context.org_id).page(limit=limit, cursor=cursor)
    items = [_out(row) for row in rows]
    next_cursor = (
        encode_cursor(rows[-1].created_at, rows[-1].user_id) if len(items) == size else None
    )
    return CursorPage(items=items, next_cursor=next_cursor)


@router.patch("/{user_id}", response_model=MemberOut, summary="Change a member's role")
async def update_role(
    request: Request,
    context: OwnerOrg,
    session: OrgSession,
    user_id: uuid.UUID,
    payload: MemberRoleUpdate,
) -> MemberOut:
    await change_member_role(
        session=session,
        org_id=context.org_id,
        user_id=user_id,
        role=payload.role,
        **audit_kwargs(request, context, entity_id=user_id),
    )
    return await _read_one(session, context, user_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a member")
async def delete_member(
    request: Request, context: OwnerOrg, session: OrgSession, user_id: uuid.UUID
) -> Response:
    await remove_member(
        session=session,
        org_id=context.org_id,
        user_id=user_id,
        **audit_kwargs(request, context, entity_id=user_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _read_one(session: AsyncSession, context: OrgContext, user_id: uuid.UUID) -> MemberOut:
    row = await MemberRepository(session, context.org_id).detail(user_id)
    if row is None:
        raise MemberNotFoundError
    return _out(row)


def _out(row: Row[Any]) -> MemberOut:
    return MemberOut(
        user_id=row.user_id,
        email=row.email,
        display_name=row.display_name,
        avatar_url=row.avatar_url,
        role=row.role,
        status=row.status,
        joined_at=row.joined_at,
        created_at=row.created_at,
    )
