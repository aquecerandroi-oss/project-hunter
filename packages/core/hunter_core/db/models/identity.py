"""Identity and tenancy — DATABASE.md §2 (users through api_keys)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, TEXT_ARRAY_EMPTY, org_fk, pg_enum
from hunter_core.domain.enums import (
    KillSwitchState,
    MemberStatus,
    OrganizationRole,
    Plan,
    WorkspaceObjective,
)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person. Identity itself lives in Clerk; this is the local mirror."""

    __tablename__ = "users"

    external_auth_id: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    onboarding_state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    last_seen_at: Mapped[datetime | None]


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The tenant. Every financial row in the database points back here."""

    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    plan: Mapped[Plan] = mapped_column(pg_enum("plan_tier"), server_default=Plan.FREE.value)
    kill_switch_state: Mapped[KillSwitchState] = mapped_column(
        pg_enum("kill_switch_state"), server_default=KillSwitchState.ACTIVE.value
    )
    kill_switch_reason: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    deleted_at: Mapped[datetime | None]


class OrganizationMember(Base):
    """Membership and RBAC role — DATABASE.md §2, SECURITY.md §2."""

    __tablename__ = "organization_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[OrganizationRole] = mapped_column(pg_enum("org_role"))
    status: Mapped[MemberStatus] = mapped_column(
        pg_enum("member_status"), server_default=MemberStatus.INVITED.value
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    joined_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OrganizationInvitation(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Pending invitation; ``token_hash`` never stores the token itself."""

    __tablename__ = "organization_invitations"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("token_hash"),
        Index("ix_org_invitations_org_email", "organization_id", "email"),
    )

    email: Mapped[str] = mapped_column(Text)
    role: Mapped[OrganizationRole] = mapped_column(pg_enum("org_role"))
    token_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Workspace(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A working context inside an organization; owns portfolios."""

    __tablename__ = "workspaces"
    __table_args__ = (org_fk(),)

    name: Mapped[str] = mapped_column(Text)
    objective: Mapped[WorkspaceObjective] = mapped_column(pg_enum("workspace_objective"))
    default_risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_profiles.id", ondelete="SET NULL"), index=True
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    deleted_at: Mapped[datetime | None]


class ApiKey(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Programmatic access. Schema in M0, used from Phase 2 (PRODUCT.md §4)."""

    __tablename__ = "api_keys"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("key_hash"),
        Index("ix_api_keys_org_created", "organization_id", "created_at"),
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    key_prefix: Mapped[str] = mapped_column(Text)
    key_hash: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=TEXT_ARRAY_EMPTY)
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
