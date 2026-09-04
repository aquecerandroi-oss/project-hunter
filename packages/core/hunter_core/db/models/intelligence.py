"""External intelligence — DATABASE.md §10 (global; Phase 2/3, schema in M0).

External content is **data**, never instruction: nothing here is ever
interpolated into a prompt as a command (SECURITY.md §6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, UUID_ARRAY_EMPTY, pg_enum
from hunter_core.domain.enums import IntelligenceSourceKind


class IntelligenceSource(Base, UUIDPrimaryKeyMixin):
    """A feed: news, reddit, x, google_trends, onchain, whales, listings, ..."""

    __tablename__ = "intelligence_sources"

    key: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[IntelligenceSourceKind] = mapped_column(pg_enum("intelligence_source_kind"))
    status: Mapped[str] = mapped_column(Text, server_default="inactive")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    last_polled_at: Mapped[datetime | None]


class IntelligenceEvent(Base, UUIDPrimaryKeyMixin):
    """A deduplicated external item plus its model classification."""

    __tablename__ = "intelligence_events"
    __table_args__ = (
        Index("ix_intelligence_events_occurred", "occurred_at"),
        Index("ix_intelligence_events_assets", "asset_ids", postgresql_using="gin"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intelligence_sources.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(Text)
    dedupe_hash: Mapped[str] = mapped_column(Text, unique=True)
    occurred_at: Mapped[datetime]
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    title: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    asset_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default=UUID_ARRAY_EMPTY
    )
    classification: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
