"""Invitations: issued and revoked inside an organization, accepted outside one.

``POST /api/v1/invitations/{token}/accept`` is deliberately *not* under
``/orgs/{org_id}``: the person holding the link is not a member yet, so there
is no membership to authorize them with, and requiring them to name the
organization would mean putting it in the link. They must still be signed in —
an invitation is accepted *by* somebody, and the email on it has to match.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import Response

from hunter_api.auth.rbac import CurrentPrincipal, OrgContext, require_org
from hunter_api.deps import OrgSession, audit_kwargs, get_session_factory
from hunter_api.repositories.base import encode_cursor
from hunter_api.repositories.invitations import InvitationRepository
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.invitations import InvitationCreate, InvitationCreated, InvitationOut
from hunter_api.services.invitations import (
    accept_invitation,
    create_invitation,
    mint_token,
    revoke_invitation,
)
from hunter_core.domain.enums import OrganizationRole

router = APIRouter(prefix="/api/v1/orgs/{org_id}/invitations", tags=["members"])
accept_router = APIRouter(prefix="/api/v1/invitations", tags=["members"])

AdminOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.ADMIN))]
TOKEN_MAX_LENGTH = 128


@router.post(
    "",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone (the token is returned once)",
)
async def create(
    request: Request, context: AdminOrg, session: OrgSession, payload: InvitationCreate
) -> InvitationCreated:
    token, token_hash = mint_token()
    created = await create_invitation(
        session=session,
        org_id=context.org_id,
        email=payload.email,
        role=payload.role,
        inviter_role=context.role,
        created_by=context.principal.user_id,
        token_hash=token_hash,
        **audit_kwargs(request, context),
    )
    return InvitationCreated(**created, token=token)


@router.get("", response_model=CursorPage[InvitationOut], summary="List invitations")
async def list_invitations(
    context: AdminOrg,
    session: OrgSession,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    cursor: str | None = None,
) -> CursorPage[InvitationOut]:
    rows, size = await InvitationRepository(session, context.org_id).page(
        limit=limit, cursor=cursor
    )
    items = [InvitationOut.model_validate(row, from_attributes=True) for row in rows]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if len(items) == size else None
    return CursorPage(items=items, next_cursor=next_cursor)


@router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an invitation",
)
async def delete(
    request: Request, context: AdminOrg, session: OrgSession, invitation_id: uuid.UUID
) -> Response:
    await revoke_invitation(
        session=session,
        org_id=context.org_id,
        invitation_id=invitation_id,
        **audit_kwargs(request, context, entity_id=invitation_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@accept_router.post("/{token}/accept", summary="Accept an invitation")
async def accept(
    request: Request,
    principal: CurrentPrincipal,
    token: Annotated[str, Path(min_length=8, max_length=TOKEN_MAX_LENGTH)],
) -> dict[str, str]:
    return await accept_invitation(
        get_session_factory(request),
        token=token,
        principal=principal,
        audit=audit_kwargs(request, None, actor_id=principal.user_id),
    )
