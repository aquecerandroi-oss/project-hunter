"""``RiskLimitsB3`` — the versioned profile ``b3_risk_profiles.limits`` (§9), as data.

Every key of the §9 table lives here, including those only the service uses (bracket,
heartbeat, IPC budgets), so one model validates the whole profile on edit. Where §9 gives
a key without a name (the "falhas para ``spec_unreadable``" next to ``spec_reread_s``) the
name here is ``spec_unreadable_after_failures`` — a name R3/R4 must reuse.

Edit validations (§9) refuse with ``limits_invalid:<campo>``; JSON numbers are refused
(every number is a decimal string), and so is a Python ``float``. The two house rules are
not editable: ``approval_ttl_s = 30`` and ``max_open_positions = 1``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Self

from pydantic import Field, ValidationError, field_serializer, model_validator

from hunter_risk_b3.base import B3Model

__all__ = ["LimitsInvalid", "RiskLimitsB3", "initial_limits", "parse_limits", "parse_limits_json"]

_ONE = Decimal(1)
_ZERO = Decimal(0)


class LimitsInvalid(ValueError):
    """A refused profile edit; ``reason`` is ``limits_invalid:<campo>``."""

    def __init__(self, field: str, detail: str = "") -> None:
        self.field = field
        self.reason = f"limits_invalid:{field}"
        super().__init__(f"{self.reason} {detail}".strip())


class RiskLimitsB3(B3Model):
    limits_version: str = Field(min_length=1)
    daily_loss_limit_brl: Decimal = Field(gt=0)
    alloc_per_trade_brl: Decimal = Field(gt=0)
    max_loss_per_trade_brl: Decimal = Field(gt=0)
    max_contracts_per_position: int = Field(ge=1)
    max_contracts_per_order: int = Field(ge=1)
    max_trades_per_day: int = Field(ge=1)
    symbol_roots: tuple[str, ...] = Field(min_length=1)
    flatten_at_local: time | None
    rico_flatten_local: time | None
    entry_cutoff_local: time | None
    warning_fraction: Decimal
    stop_slippage_ticks: int = Field(ge=0)
    reconcile_interval_s: int = Field(gt=0)
    bracket_step_s: int = Field(gt=0)
    send_budget_s: int = Field(gt=0)
    approval_ttl_s: int = 30
    """House rule, not editable (§9): any other value is ``limits_invalid:approval_ttl_s``."""
    max_open_positions: int = 1
    """Fixed in v1 (check 10): any other value is ``limits_invalid:max_open_positions``."""
    api_heartbeat_s: int = Field(gt=0)
    entries_api_freshness_s: int = Field(gt=0)
    ea_hb_stale_s: int = Field(gt=0)
    spec_reread_s: int = Field(gt=0)
    spec_unreadable_after_failures: int = Field(gt=0)
    max_slippage_ticks: int = Field(ge=0)
    max_quote_age_s: int = Field(gt=0)
    max_clock_offset_s: int = Field(gt=0)
    clock_check_max_age_s: int = Field(gt=0)
    max_spread_ticks: int = Field(ge=0)
    min_stop_ticks: int = Field(gt=0)
    max_stop_ticks: int = Field(gt=0)
    no_entry_first_min: int = Field(ge=0)
    min_minutes_before_flatten: int = Field(ge=0)
    flatten_lead_min: int = Field(ge=0)
    bracket_deadline_s: int = Field(gt=0)
    bracket_max_k: int = Field(ge=0)
    naked_grace_s: int = Field(gt=0)
    entry_cancel_after_s: int = Field(gt=0)
    slippage_alert_ticks: int = Field(ge=0)
    max_rejects: int = Field(gt=0)
    reject_window_s: int = Field(gt=0)
    margin_use_max_pct: Decimal
    pnl_reconcile_tolerance_brl: Decimal = Field(ge=0)
    ipc_call_timeout_s: int = Field(gt=0)
    sltp_record_budget_ms: int = Field(gt=0)
    sltp_record_api_ms: int = Field(gt=0)
    hb_file_interval_s: int = Field(gt=0)
    ea_hb_future_tolerance_s: int = Field(gt=0)
    equity_floor_brl: Decimal | None = Field(gt=0)

    @model_validator(mode="after")
    def _edit_rules(self) -> Self:
        """§9 "Validações na edição"."""
        if self.max_contracts_per_order > self.max_contracts_per_position:
            raise ValueError("limits_invalid:max_contracts_per_order")
        if self.max_loss_per_trade_brl > self.daily_loss_limit_brl:
            raise ValueError("limits_invalid:max_loss_per_trade_brl")
        if self.min_stop_ticks >= self.max_stop_ticks:
            raise ValueError("limits_invalid:min_stop_ticks")
        for name in ("warning_fraction", "margin_use_max_pct"):
            if not _ZERO < getattr(self, name) <= _ONE:
                raise ValueError(f"limits_invalid:{name}")
        if self.sltp_record_api_ms > self.sltp_record_budget_ms:
            raise ValueError("limits_invalid:sltp_record_api_ms")
        if self.flatten_at_local is not None and self.rico_flatten_local is not None:
            latest = _minus_minutes(self.rico_flatten_local, self.flatten_lead_min)
            if self.flatten_at_local > latest:
                raise ValueError("limits_invalid:flatten_at_local")
        if self.approval_ttl_s != 30:
            raise ValueError("limits_invalid:approval_ttl_s")
        if self.max_open_positions != 1:
            raise ValueError("limits_invalid:max_open_positions")
        return self

    @field_serializer("*", when_used="json")
    def _numbers_as_strings(self, value: Any) -> Any:
        """§9: every number is a decimal string in the stored JSON (Decimal already is)."""
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value


def _minus_minutes(local: time, minutes: int) -> time:
    anchor = datetime.combine(date(2000, 1, 2), local, tzinfo=UTC)
    shifted = anchor - timedelta(minutes=minutes)
    return shifted.time() if shifted.date() == anchor.date() else time(0, 0)


def parse_limits(data: dict[str, Any]) -> RiskLimitsB3:
    """Validate a profile; any refusal becomes :class:`LimitsInvalid` naming the field."""
    try:
        return RiskLimitsB3.model_validate(data)
    except TypeError as err:  # the float refusal of B3Model
        field = str(err).split(".", 1)[-1].split(" ", 1)[0]
        raise LimitsInvalid(field, str(err)) from err
    except ValidationError as err:
        first = err.errors()[0]
        loc = first.get("loc", ())
        message = str(first.get("msg", ""))
        if "limits_invalid:" in message:
            field = message.split("limits_invalid:", 1)[1].split()[0]
        else:
            field = str(loc[0]) if loc else "profile"
        raise LimitsInvalid(field, message) from err


class _JsonNumber:
    def __init__(self, raw: str) -> None:
        self.raw = raw


def _refuse_numbers(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    for key, value in pairs:
        if isinstance(value, _JsonNumber):
            raise LimitsInvalid(key, f"JSON number {value.raw}; numbers are decimal strings")
    return dict(pairs)


def parse_limits_json(raw: str) -> RiskLimitsB3:
    """Parse the stored JSON profile: a JSON number anywhere is refused by field name."""
    data = json.loads(
        raw, parse_float=_JsonNumber, parse_int=_JsonNumber, object_pairs_hook=_refuse_numbers
    )
    if not isinstance(data, dict):
        raise LimitsInvalid("profile", "the profile is a JSON object")
    return parse_limits(data)  # pyright: ignore[reportUnknownArgumentType]


def initial_limits(limits_version: str) -> RiskLimitsB3:
    """The §9 table as of 2026-10-17. Origins (Everton / design default / R0a proposal)
    are in the contract; none of them is measured, and D6 leaves flatten unset (no
    entries until Everton fills ``flatten_at_local`` and ``rico_flatten_local``)."""
    return RiskLimitsB3(
        limits_version=limits_version,
        daily_loss_limit_brl=Decimal("9000"),
        alloc_per_trade_brl=Decimal("1000"),
        max_loss_per_trade_brl=Decimal("250"),
        max_contracts_per_position=1,
        max_contracts_per_order=1,
        max_trades_per_day=1,
        symbol_roots=("WIN",),
        flatten_at_local=None,
        rico_flatten_local=None,
        entry_cutoff_local=None,
        warning_fraction=Decimal("0.5"),
        stop_slippage_ticks=2,
        reconcile_interval_s=5,
        bracket_step_s=1,
        send_budget_s=3,
        api_heartbeat_s=5,
        entries_api_freshness_s=15,
        ea_hb_stale_s=30,
        spec_reread_s=60,
        spec_unreadable_after_failures=3,
        max_slippage_ticks=1,
        max_quote_age_s=5,
        max_clock_offset_s=2,
        clock_check_max_age_s=900,
        max_spread_ticks=2,
        min_stop_ticks=10,
        max_stop_ticks=400,
        no_entry_first_min=5,
        min_minutes_before_flatten=15,
        flatten_lead_min=20,
        bracket_deadline_s=120,
        bracket_max_k=4,
        naked_grace_s=5,
        entry_cancel_after_s=10,
        slippage_alert_ticks=2,
        max_rejects=3,
        reject_window_s=600,
        margin_use_max_pct=Decimal("0.5"),
        pnl_reconcile_tolerance_brl=Decimal("5"),
        ipc_call_timeout_s=10,
        sltp_record_budget_ms=500,
        sltp_record_api_ms=300,
        hb_file_interval_s=2,
        ea_hb_future_tolerance_s=5,
        equity_floor_brl=None,
    )
