"""SQLAlchemy declarative base, naming convention and shared mixins.

DATABASE.md §1: UUID v7 primary keys, ``TIMESTAMPTZ`` always UTC,
``NUMERIC(28,10)`` for money (never float), tenant tables carry
``organization_id NOT NULL`` and are indexed on it. No ORM table models live
here (that is T04's job) — only the base class and mixins T04 builds on.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, MetaData, Numeric, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hunter_core.domain.types import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every ``hunter_*`` ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        Decimal: Numeric(28, 10),
        datetime: TIMESTAMP(timezone=True),
        uuid.UUID: postgresql.UUID(as_uuid=True),
    }


class UUIDPrimaryKeyMixin:
    """``id UUID`` primary key, generated application-side as UUID v7."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    """``created_at`` / ``updated_at``, both server-side, both UTC."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TenantMixin:
    """``organization_id`` — every tenant table (DATABASE.md §1.1) carries this,
    indexed, for RLS (``app.current_org``) and tenant-scoped repositories.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
