"""Kill switch payloads — RISK_ENGINE.md §5, DATABASE.md §18.7.

Two shapes with one job between them: say *what* the switch is and *why*, with
the numbers that justified it, so the Risk Center shows an explanation instead of
a colour. ``Decimal`` fields are serialised as strings by the API's JSON encoder,
which is the same refusal of ``float`` the engine makes on construction (§8).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from hunter_api.schemas.common import StrictModel
from hunter_core.domain.enums import KillSwitchState


class ScopeStatesOut(BaseModel):
    """The three scopes, unmerged — the effective state is the most restrictive."""

    system: KillSwitchState
    organization: KillSwitchState
    portfolio: KillSwitchState


class DailyReferenceOut(BaseModel):
    """The persisted anchor of the São Paulo trading day.

    ``equity_day_start`` is ``None`` when the reference could not be rebuilt —
    entries blocked, protections preserved. ``observed_at`` is the *real* instant
    of the evaluation, not midnight.
    """

    trading_day: date | None
    trading_day_timezone: str
    trading_day_start_utc: datetime | None
    equity_day_start: Decimal | None
    observed_at: datetime | None
    available: bool


class PeakOut(BaseModel):
    """The monotonic, **sampled** peak — never the intratick maximum."""

    equity: Decimal
    observed_at: datetime
    sampling_interval_s: int


class TransitionOut(BaseModel):
    """One audited move. ``evidence`` is the numbers; ``reason`` is the prose."""

    from_state: KillSwitchState
    to_state: KillSwitchState
    reason: str | None
    actor_type: str
    actor_id: uuid.UUID | None
    """Named, not authenticated: the column has no FK to ``users`` on purpose
    (§18.7), so this proves somebody was named by the API that authenticated
    them — the trail survives the person being removed."""
    evidence: dict[str, Any]
    created_at: datetime


class KillSwitchOut(BaseModel):
    """The wallet's kill switch, with its motive and its evidence."""

    portfolio_id: uuid.UUID
    effective: KillSwitchState
    blocks_entries: bool
    scopes: ScopeStatesOut
    reason: str | None
    daily_reference: DailyReferenceOut
    peak: PeakOut
    last_transition: TransitionOut | None


class ResumeRequest(StrictModel):
    """A resume states a reason, and the reason is stored on the transition."""

    reason: str = Field(min_length=1, max_length=500)


class ResumeOut(BaseModel):
    """What the resume moved, and the assessment it was allowed against."""

    portfolio_id: uuid.UUID
    from_state: KillSwitchState
    to_state: KillSwitchState
    actor_id: uuid.UUID
    daily_loss_pct: Decimal
    drawdown_pct: Decimal
    effective: KillSwitchState
