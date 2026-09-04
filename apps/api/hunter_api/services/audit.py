"""Turning ``deps.audit_kwargs`` into an :class:`~hunter_core.audit.AuditEvent`.

Two flows cannot use the ``@audited`` decorator — sign-up and the Clerk webhook
both run before (or outside) any organization context, so there is no
``deps.org_session`` to have bound a sink. They record explicitly, through
this one adapter, so the resulting ``audit_logs`` row is identical in shape to
every decorated mutation's.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from hunter_core.audit import AuditEvent, SqlAuditSink

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def audit_event(
    action: str,
    entity_type: str,
    audit: dict[str, Any],
    *,
    before: Any = None,
    after: Any = None,
) -> AuditEvent:
    entity_id = audit.get("entity_id")
    return AuditEvent(
        actor_type=audit.get("actor_type", "system"),
        actor_id=str(audit.get("actor_id", "system")),
        organization_id=_as_uuid(audit.get("organization_id")),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        ip=audit.get("ip"),
        user_agent=audit.get("user_agent"),
        metadata=audit.get("audit_metadata") or {},
    )


async def record(
    session: AsyncSession,
    action: str,
    entity_type: str,
    audit: dict[str, Any],
    *,
    before: Any = None,
    after: Any = None,
) -> None:
    """Write one audit row on ``session`` — same transaction as the mutation."""
    await SqlAuditSink(session).record(
        audit_event(action, entity_type, audit, before=before, after=after)
    )


def _as_uuid(value: Any) -> uuid.UUID | None:
    return value if isinstance(value, uuid.UUID) else None
