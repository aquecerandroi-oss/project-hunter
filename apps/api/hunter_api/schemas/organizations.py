"""Organization, membership and ``/me`` payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from hunter_api.schemas.common import StrictModel
from hunter_core.domain.enums import (
    KillSwitchState,
    MemberStatus,
    OrganizationRole,
    Plan,
    WorkspaceObjective,
)


class OrganizationCreate(StrictModel):
    """Sign-up. The slug is derived from the name — a caller cannot choose it
    in M0, which keeps slug squatting off the table until there is a reason to
    allow it.
    """

    name: str = Field(min_length=1, max_length=120)
    workspace_name: str | None = Field(default=None, max_length=120)
    objective: WorkspaceObjective = WorkspaceObjective.EXPLORE


class OrganizationUpdate(StrictModel):
    """Name only, in M0.

    ``plan`` and ``kill_switch_state`` are deliberately absent: the plan is
    billing's to set (Phase 3) and the kill switch moves only through the risk
    engine's own audited transition. Because this model forbids extras, sending
    either one is a 422 that names the field, not a silent no-op.
    """

    name: str = Field(min_length=1, max_length=120)


class OrganizationOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    plan: Plan
    kill_switch_state: KillSwitchState
    created_at: datetime


class OrganizationCreated(OrganizationOut):
    """The sign-up response. ``workspace_id`` is the workspace the onboarding
    wizard immediately PUTs to, so the client needs no second round trip to
    find it.
    """

    workspace_id: uuid.UUID


class OnboardingState(BaseModel):
    """Whether this organization has finished the onboarding flow (PRODUCT.md §3)."""

    completed: bool = False
    completed_at: datetime | None = None
    workspace_id: uuid.UUID | None = None


class MembershipOut(BaseModel):
    organization: OrganizationOut
    role: OrganizationRole
    status: MemberStatus
    onboarding: OnboardingState


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


class MeOut(BaseModel):
    """``GET /api/v1/me`` — everything the app shell needs to render itself."""

    user: UserOut
    memberships: list[MembershipOut]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    role: OrganizationRole
    status: MemberStatus
    joined_at: datetime | None = None
    created_at: datetime


class MemberRoleUpdate(StrictModel):
    role: OrganizationRole
