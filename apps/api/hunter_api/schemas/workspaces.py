"""Workspace and onboarding payloads — PRODUCT.md §3."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from hunter_api.schemas.common import StrictModel
from hunter_core.domain.enums import RiskPreset, WorkspaceObjective

MIN_VIRTUAL_CAPITAL = Decimal("1000")
DEFAULT_VIRTUAL_CAPITAL = Decimal("10000")
MAX_MONITORED_EXCHANGES = 10


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    objective: WorkspaceObjective = WorkspaceObjective.EXPLORE


class WorkspaceUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    objective: WorkspaceObjective | None = None


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    objective: WorkspaceObjective
    default_risk_profile_id: uuid.UUID | None = None
    settings: dict[str, Any]
    created_at: datetime
    onboarding_completed_at: datetime | None = None


class OnboardingUpdate(StrictModel):
    """The six-step onboarding, submitted at once (PRODUCT.md §3).

    ``virtual_capital`` is a ``Decimal`` and never a float — it becomes the
    default initial capital of the paper portfolios created in M3, i.e. money.
    The 1 000 floor is what makes position sizing meaningful at all: below it,
    a 1 % risk budget rounds to nothing on most instruments.
    """

    objective: WorkspaceObjective
    virtual_capital: Decimal = Field(
        default=DEFAULT_VIRTUAL_CAPITAL, ge=MIN_VIRTUAL_CAPITAL, decimal_places=10, max_digits=28
    )
    risk_preset: RiskPreset = RiskPreset.BALANCED
    monitored_exchanges: list[str] = Field(default_factory=list, max_length=MAX_MONITORED_EXCHANGES)
