"""Audit, system events, heartbeats, idempotency and the outbox — DATABASE.md
§12 and §17.

``audit_logs`` and ``system_events`` are RANGE-partitioned by month on
``created_at`` and are append-only for ``hunter_app``. ``audit_logs`` keeps a
nullable ``organization_id`` (``NULL`` = system action), which is also what the
``tenant_isolation`` policy filters on: an org sees exactly its own rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, Text, func, text
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
    """Durable idempotency for critical consumers, in two phases.

    PK ``(consumer, event_id)``. A consumer *claims* a delivery (insert;
    ``completed_at`` NULL) before applying its effect and *completes* it after,
    so the row distinguishes "being handled" from "handled". Only a completed
    row is a duplicate: a claim left unfinished — a pod evicted, an OOM kill, a
    lost connection between the two steps — is re-claimable once it is older
    than the consumer's stale window, and the redelivery does the work. A
    single ``processed_at`` column could not tell those apart, so a crash
    turned into a delivery permanently answered "already handled" that was
    never handled at all.

    Completed rows past their retention are removed by
    ``infra/scripts/prune_processed_events.py``. Unfinished claims are left
    alone by it: they are the record of a delivery that never landed.
    """

    __tablename__ = "processed_events"
    __table_args__ = (
        Index("ix_processed_events_claimed_at", "claimed_at"),
        Index("ix_processed_events_completed_at", "completed_at"),
    )

    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]


class OutboxEvent(Base):
    """Events a durable producer owes a Redis stream, written in *its* transaction.

    The generic half of T2.9. A worker that writes a business row and then does
    ``XADD`` has two failure windows — crash after the commit (event lost) and
    crash after the ``XADD`` before the ACK (event duplicated) — and no amount of
    retrying closes the first one. Writing the intent to this table inside the
    same transaction as the business row turns "did it happen?" into a question
    the database answers: the row and the obligation commit together or neither
    does, and a dispatcher drains ``dispatched_at IS NULL`` afterwards.

    **Shape-identical to** ``shadow_outbox`` on purpose (SHADOW-LAB.md §6). The
    Shadow Lab shipped its own queue in ``0002`` before this one existed, and the
    absorption has to preserve pending work, so the columns match one for one and
    the migration is an ``INSERT ... SELECT`` with an explicit column list that
    keeps ``event_id``, ``stream``, ``payload``, ``created_at``,
    ``dispatched_at``, ``attempts`` and ``last_error`` and lets ``id`` be
    re-issued from this table's own sequence. Copying ``id`` across two populated
    queues would collide, and it would mean nothing if it did not: ``id`` is a
    drain order, never an identity.

    ``BIGSERIAL`` rather than the UUID v7 of §1, for the same reason
    ``shadow_outbox`` is: a cheap, stable order to drain in. It is **not** a
    watermark — the sequence has gaps and its order is not commit order, so
    "everything below N is published" is false. The pending predicate is
    ``dispatched_at IS NULL``, which is what the partial index serves --
    keyed on ``(created_at, id)`` since ``0004`` because that is the order the
    dispatcher claims in, so the index answers the ``ORDER BY`` too instead of
    being abandoned by the planner for a seq scan and a sort (measured 15.3 ms
    -> 0.2 ms per claim with 30k pending rows).
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_pending",
            "created_at",
            "id",
            postgresql_where=text("dispatched_at IS NULL"),
        ),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        CheckConstraint("char_length(stream) > 0", name="stream_not_empty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    """The event's identity, computed deterministically by the producer from the
    business row. Unique, so a retried transaction queues the event once and a
    redelivery is a no-op instead of a second publication. This — not ``id`` — is
    what survives the absorption of ``shadow_outbox``."""

    stream: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    dispatched_at: Mapped[datetime | None]
    """``NULL`` until the event is on the stream — the reconciliation predicate."""

    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
