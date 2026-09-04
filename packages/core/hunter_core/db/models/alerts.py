"""Alert rules and notifications — DATABASE.md §11 (tenant)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    JSONB_EMPTY,
    JSONB_EMPTY_LIST,
    SQL_TRUE,
    org_fk,
    pg_enum,
)
from hunter_core.domain.enums import AlertChannel, NotificationStatus


class AlertRule(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A user-defined condition plus its delivery channels and cooldown."""

    __tablename__ = "alert_rules"
    __table_args__ = (
        org_fk(),
        Index("ix_alert_rules_org_enabled", "organization_id", "enabled"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    channels: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    enabled: Mapped[bool] = mapped_column(server_default=SQL_TRUE)
    cooldown_s: Mapped[int] = mapped_column(Integer, server_default="300")
    last_triggered_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]


class Notification(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One delivery. ``user_id IS NULL`` means every member of the organization."""

    __tablename__ = "notifications"
    __table_args__ = (
        org_fk(),
        Index(
            "ix_notifications_org_user_status_created",
            "organization_id",
            "user_id",
            "status",
            "created_at",
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    channel: Mapped[AlertChannel] = mapped_column(
        pg_enum("notification_channel"), server_default=AlertChannel.IN_APP.value
    )
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum("notification_status"), server_default=NotificationStatus.PENDING.value
    )
    sent_at: Mapped[datetime | None]
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
