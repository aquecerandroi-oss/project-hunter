"""Inputs about the session, the calendar, the kill switch, the symbol spec and the
margin (docs/RISK_ENGINE_B3.md §8.1). All computed by the service **before** the
evaluation; the engine never fetches them.

Two additions to the field list of §8.1, both needed by an output the contract names:
``SpecPin.spec_pin_id`` (the decision records ``spec_pin_id``, §8.4) and
``OrderCheckResult`` as the typed form of ``order_check {v: ok|refused(reason)}``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from hunter_risk_b3.base import B3Model, UtcDatetime
from hunter_risk_b3.enums import AuthorityPhase, KillSwitchState, SpecStatus

__all__ = [
    "SPEC_FIELDS",
    "ArmedStrategy",
    "AuthorityView",
    "CalendarB3",
    "ClockCheck",
    "CurrentContract",
    "KillSwitchB3",
    "MarginInputs",
    "OrderCheckResult",
    "SessionContext",
    "SpecInputs",
    "SpecNow",
    "SpecPin",
]


class ClockCheck(B3Model):
    offset_ms: int | None
    measured_at: UtcDatetime | None
    ok: bool


class SessionContext(B3Model):
    session_date: date
    open_utc: UtcDatetime
    close_utc: UtcDatetime
    flatten_at_utc: UtcDatetime | None
    """``None`` ⇒ check 7 ``flatten_schedule_unset`` (D6 empty ⇒ no entries)."""
    rico_flatten_utc: UtcDatetime | None
    session_end_utc: UtcDatetime
    entry_cutoff_utc: UtcDatetime | None
    grid_version: str = Field(min_length=1)
    clock: ClockCheck


class CurrentContract(B3Model):
    symbol: str = Field(min_length=1)
    root: str = Field(min_length=1)
    expiry_date: date


class CalendarB3(B3Model):
    is_holiday: bool
    """No B3 session that day (holiday or weekend)."""
    is_shortened: bool
    has_grid: bool
    """A grid row valid for that date — for a shortened day, its own row."""
    current_contract: CurrentContract | None
    is_expiry_day: bool
    read_ok: bool


class AuthorityView(B3Model):
    phase: AuthorityPhase
    instance_id: uuid.UUID | None
    authority_expires_at: UtcDatetime | None

    @model_validator(mode="after")
    def _granted_has_owner_and_deadline(self) -> Self:
        if self.phase is not AuthorityPhase.READ_ONLY and (
            self.instance_id is None or self.authority_expires_at is None
        ):
            raise ValueError(
                f"authority in {self.phase} needs instance_id and authority_expires_at"
            )
        return self


class ArmedStrategy(B3Model):
    key: str = Field(min_length=1)
    version: int = Field(ge=1)
    params_hash: str = Field(min_length=1)


class KillSwitchB3(B3Model):
    system: KillSwitchState
    organization: KillSwitchState
    robot: KillSwitchState
    authority: AuthorityView
    registered_account_hash: str = Field(min_length=1)
    k1_present: bool
    armed_strategy: ArmedStrategy | None


SPEC_FIELDS: tuple[str, ...] = (
    "trade_tick_size", "trade_tick_value", "point", "digits", "volume_min", "volume_step",
    "volume_max", "trade_mode", "filling_mode", "expiration_mode", "account_margin_mode",
    "terminal_version", "package_version", "order_lifecycle_proven", "comment_preserved",
    "stale_ticket_rejection_proven",
)  # fmt: skip
"""The fields compared by check 23, in contract order (both models carry all of them)."""


class SpecPin(B3Model):
    """The spec fixed at arming. Every field is required and the numeric ones positive."""

    spec_pin_id: str = Field(min_length=1)
    trade_tick_size: Decimal = Field(gt=0)
    trade_tick_value: Decimal = Field(gt=0)
    point: Decimal = Field(gt=0)
    digits: int = Field(ge=0)
    volume_min: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)
    trade_mode: str
    filling_mode: str
    expiration_mode: str
    account_margin_mode: str
    terminal_version: str
    package_version: str
    order_lifecycle_proven: bool
    """T14 proof, recorded with its evidence at arming."""
    comment_preserved: bool
    """T8 proof."""
    stale_ticket_rejection_proven: bool
    """T13 proof."""


class SpecNow(B3Model):
    """The spec re-read now. ``status = ok`` requires every field."""

    status: SpecStatus
    trade_tick_size: Decimal | None = None
    trade_tick_value: Decimal | None = None
    point: Decimal | None = None
    digits: int | None = None
    volume_min: Decimal | None = None
    volume_step: Decimal | None = None
    volume_max: Decimal | None = None
    trade_mode: str | None = None
    filling_mode: str | None = None
    expiration_mode: str | None = None
    account_margin_mode: str | None = None
    terminal_version: str | None = None
    package_version: str | None = None
    order_lifecycle_proven: bool | None = None
    comment_preserved: bool | None = None
    stale_ticket_rejection_proven: bool | None = None

    @model_validator(mode="after")
    def _complete_when_ok(self) -> Self:
        if self.status is SpecStatus.OK:
            missing = [f for f in SPEC_FIELDS if getattr(self, f) is None]
            if missing:
                raise ValueError(f"spec status ok without {missing}")
        return self


class SpecInputs(B3Model):
    """The ``spec`` argument of :func:`hunter_risk_b3.evaluate`."""

    pin: SpecPin
    now: SpecNow


class OrderCheckResult(B3Model):
    ok: bool
    reason: str | None = None


class MarginInputs(B3Model):
    """``order_calc_margin`` and ``order_check`` per candidate volume, computed by the
    service for ``v = 1..max_contracts_per_order`` before the evaluation (§8.1)."""

    per_volume: dict[int, Decimal]
    order_check: dict[int, OrderCheckResult]
    read_ok: bool
