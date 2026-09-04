"""Audit-log read payloads — DATABASE.md §12, SECURITY.md §5."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    """One ``audit_logs`` row as an organization's admins see it.

    ``ip`` and ``user_agent`` are included on purpose: an audit trail that
    cannot answer "from where" is not much of an audit trail, and both values
    were supplied by the actor's own client. Nothing here reaches across
    organizations — the query runs under ``app.current_org``.
    """

    id: uuid.UUID
    created_at: datetime
    actor_type: str
    actor_id: uuid.UUID | None = None
    action: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
