"""Connected exchange accounts — DATABASE.md §8 (tenant; schema in M0, used in Phase 3).

``CHECK (withdraw_enabled = false)`` is deliberate and load-bearing: a key whose
permissions include withdrawal is rejected at validation time and is never
persisted as usable (SECURITY.md §4). Keys are stored envelope-encrypted; only
the execution worker ever decrypts them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, SQL_FALSE, org_fk, pg_enum
from hunter_core.domain.enums import ConnectionStatus


class ExchangeConnection(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One API key pair of one organization on one exchange."""

    __tablename__ = "exchange_connections"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("organization_id", "exchange_id", "label", name="uq_exchange_conn_label"),
        CheckConstraint("withdraw_enabled = false", name="withdraw_disabled"),
    )

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exchanges.id", ondelete="RESTRICT"), index=True
    )
    label: Mapped[str] = mapped_column(Text)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    api_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_key_version: Mapped[int] = mapped_column(Integer, server_default="1")
    key_fingerprint: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    withdraw_enabled: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    status: Mapped[ConnectionStatus] = mapped_column(
        pg_enum("connection_status"), server_default=ConnectionStatus.PENDING.value
    )
    last_validated_at: Mapped[datetime | None]
    validation_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
