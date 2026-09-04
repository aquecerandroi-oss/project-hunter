"""Reading the audit trail — append-only, and never across organizations."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_

from hunter_api.repositories.base import TenantRepository, clamp_page_size, decode_cursor
from hunter_core.db.models.system import AuditLog

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


class AuditRepository(TenantRepository):
    """``audit_logs`` for one organization.

    The ordering is ``(created_at DESC, id DESC)`` — an audit view is read
    newest-first — and the cursor is the matching keyset. ``created_at`` leads
    both the primary key and the partition key (DATABASE.md §15.2), so a page
    is one index-ordered scan touching only the months it needs.
    """

    async def page(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[Sequence[AuditLog], int]:
        size = clamp_page_size(limit)
        statement = select(AuditLog).where(AuditLog.organization_id == self.org_id)
        if action:
            statement = statement.where(AuditLog.action == action)
        if actor_id is not None:
            statement = statement.where(AuditLog.actor_id == actor_id)
        if since is not None:
            statement = statement.where(AuditLog.created_at >= since)
        if until is not None:
            statement = statement.where(AuditLog.created_at < until)
        after = decode_cursor(cursor)
        if after is not None:
            statement = statement.where(tuple_(AuditLog.created_at, AuditLog.id) < after)
        statement = statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        rows = (await self.session.execute(statement.limit(size + 1))).scalars().all()
        return rows[:size], size
