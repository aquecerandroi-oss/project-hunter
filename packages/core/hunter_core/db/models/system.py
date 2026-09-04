"""Audit, system events, heartbeats and idempotency — DATABASE.md §12.

``audit_logs`` and ``system_events`` are RANGE-partitioned by month on
``created_at`` and are append-only for ``hunter_app``. ``audit_logs`` keeps a
nullable ``organization_id`` (``NULL`` = system action), which is also what the
``tenant_isolation`` policy filters on: an org sees exactly its own rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, pg_enum
from hunter_core.domain.enums import RiskEventSeverity, WorkerHeartbeatStatus


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Every meaningful mutation, with before/after. Append-only, never pruned."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)


class SystemEvent(Base, UUIDPrimaryKeyMixin):
    """Operational events (missing partition, worker degraded, ...). 30 d retention."""

    __tablename__ = "system_events"
    __table_args__ = (
        Index("ix_system_events_level_created", "level", "created_at"),
        Index("ix_system_events_component_created", "component", "created_at"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), primary_key=True)
    level: Mapped[RiskEventSeverity] = mapped_column(
        pg_enum("event_severity"), server_default=RiskEventSeverity.INFO.value
    )
    component: Mapped[str] = mapped_column(Text)
    event: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)


class WorkerHeartbeat(Base):
    """Liveness per worker instance. PK ``(worker_role, instance_id)``."""

    __tablename__ = "worker_heartbeats"

    worker_role: Mapped[str] = mapped_column(Text, primary_key=True)
    instance_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_heartbeat_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_success_at: Mapped[datetime | None]
    error_count: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[WorkerHeartbeatStatus] = mapped_column(
        pg_enum("worker_heartbeat_status"), server_default=WorkerHeartbeatStatus.HEALTHY.value
    )
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)


class ProcessedEvent(Base):
    """Durable idempotency for critical consumers. PK ``(consumer, event_id)``;
    rows older than 7 days are pruned daily by the analytics worker.
    """

    __tablename__ = "processed_events"
    __table_args__ = (Index("ix_processed_events_processed_at", "processed_at"),)

    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now())
