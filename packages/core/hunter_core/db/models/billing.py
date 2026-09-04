"""Subscriptions, plan entitlements and feature flags — DATABASE.md §2.

``plan_entitlements`` and ``feature_flags`` are global system tables (no
``organization_id``, no RLS); ``organization_feature_overrides`` is a tenant
table that narrows a flag for one organization.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import SQL_FALSE, org_fk, pg_enum
from hunter_core.domain.enums import Plan, SubscriptionStatus


class Subscription(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One per organization. Billing runs in Phase 3; the schema lands in M0."""

    __tablename__ = "subscriptions"
    __table_args__ = (org_fk(),)

    organization_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    plan: Mapped[Plan] = mapped_column(pg_enum("plan_tier"), server_default=Plan.FREE.value)
    status: Mapped[SubscriptionStatus] = mapped_column(
        pg_enum("subscription_status"), server_default=SubscriptionStatus.ACTIVE.value
    )
    provider: Mapped[str | None] = mapped_column(Text)
    provider_customer_id: Mapped[str | None] = mapped_column(Text)
    provider_subscription_id: Mapped[str | None] = mapped_column(Text)
    current_period_start: Mapped[datetime | None]
    current_period_end: Mapped[datetime | None]


class PlanEntitlement(Base):
    """Seeded limits per plan — PRODUCT.md §5. PK ``(plan, key)``."""

    __tablename__ = "plan_entitlements"

    plan: Mapped[Plan] = mapped_column(pg_enum("plan_tier"), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)


class FeatureFlag(Base):
    """System flags; env ``ENABLE_*`` is the default, this table overrides it."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=SQL_FALSE)
    description: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class OrganizationFeatureOverride(Base, TenantMixin):
    """Per-organization override of a system flag. PK ``(organization_id, key)``."""

    __tablename__ = "organization_feature_overrides"
    __table_args__ = (org_fk(),)

    organization_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(
        ForeignKey("feature_flags.key", ondelete="CASCADE"), primary_key=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
