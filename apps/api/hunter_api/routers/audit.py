"""``GET /api/v1/orgs/{org_id}/audit`` — the organization's own trail.

ADMIN and above: the trail names who did what, which is a record about the
organization's people. It is read-only here and append-only in Postgres —
``hunter_app`` holds ``SELECT``/``INSERT`` and nothing else, on the parent and
on every monthly partition (DATABASE.md §15.6), so no route, and no bug in
one, can edit or erase history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession
from hunter_api.repositories.audit import AuditRepository
from hunter_api.repositories.base import encode_cursor
from hunter_api.schemas.audit import AuditEntryOut
from hunter_api.schemas.common import CursorPage
from hunter_core.domain.enums import OrganizationRole

router = APIRouter(prefix="/api/v1/orgs/{org_id}/audit", tags=["audit"])

AdminOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.ADMIN))]


@router.get("", response_model=CursorPage[AuditEntryOut], summary="Read the audit log")
async def list_audit(
    context: AdminOrg,
    session: OrgSession,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    cursor: str | None = None,
    action: Annotated[str | None, Query(max_length=120)] = None,
    actor: uuid.UUID | None = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> CursorPage[AuditEntryOut]:
    rows, size = await AuditRepository(session, context.org_id).page(
        limit=limit, cursor=cursor, action=action, actor_id=actor, since=since, until=until
    )
    items = [
        AuditEntryOut(
            id=row.id,
            created_at=row.created_at,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            before=row.before,
            after=row.after,
            # the column is INET, and asyncpg hands back an ipaddress object
            ip=str(row.ip) if row.ip is not None else None,
            user_agent=row.user_agent,
            request_id=row.request_id,
        )
        for row in rows
    ]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if len(items) == size else None
    return CursorPage(items=items, next_cursor=next_cursor)
