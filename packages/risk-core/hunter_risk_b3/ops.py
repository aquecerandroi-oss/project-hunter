"""``RobotOpsState`` — the registry state the engine reads (docs/RISK_ENGINE_B3.md §8.1).

The three counts (``entries_today``, ``open_entry_intents``, ``unknown_intents``) arrive
**already without the proposal under evaluation** (§8.1, check 11 and 13, ``[Astra
R0a-1]``): the ``pre_send_gate`` re-evaluation must not refuse the entry because of itself.

Two shape choices, stated: ``orphan_sltp_unknown`` ("bool, por símbolo") is the set of
symbols that have an orphan uncertain SLTP, so check 11 asks ``proposal.symbol in it``;
``robot_magics`` (§1.1, "o conjunto de todos os já atribuídos à organização") is added
here because check 10/11 must tell ``position_already_open`` / ``pending_order_present``
from the ``foreign_*`` reasons, and §8.1 lists no other input that carries it.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from hunter_risk_b3.base import B3Model, UtcDatetime

__all__ = ["AuditPath", "DayPnl", "FeeSchedule", "LastReconcile", "RobotOpsState"]


class LastReconcile(B3Model):
    at: UtcDatetime
    clean: bool
    consistent_passes: int = Field(ge=0)


class AuditPath(B3Model):
    api_last_ok_at: UtcDatetime | None
    buffer_len: int = Field(ge=0)
    buffer_writable: bool


class DayPnl(B3Model):
    """The day's loss inputs (§8.3). No field defaults to zero: absent is ``None``, and
    ``None`` makes check 14 ``unavailable``."""

    anchor_equity: Decimal | None
    anchor_at: UtcDatetime | None
    cash_flows_brl: Decimal | None
    history_complete: bool
    realized_gross_brl: Decimal | None
    costs_positive_brl: Decimal | None = Field(ge=0)
    open_mtm_gross_brl: Decimal | None
    open_exit_fee_brl: Decimal | None = Field(ge=0)
    mark_time: UtcDatetime | None
    """When the open-position valuation was made (also when flat: the instant the empty
    position list was read). ``None`` or older than ``max_quote_age_s`` ⇒ ``mark_stale``."""
    equity_delta_brl: Decimal | None


class FeeSchedule(B3Model):
    per_leg_brl: Decimal | None = Field(ge=0)
    source: str | None
    valid: bool

    @model_validator(mode="after")
    def _valid_has_number_and_source(self) -> FeeSchedule:
        if self.valid and (self.per_leg_brl is None or not self.source):
            raise ValueError("a valid fee schedule has a per-leg amount and a source")
        return self


class RobotOpsState(B3Model):
    entries_today: int = Field(ge=0)
    open_entry_intents: int = Field(ge=0)
    unknown_intents: int = Field(ge=0)
    orphan_sltp_unknown: frozenset[str]
    entry_rejects: tuple[UtcDatetime, ...]
    breaker_latched: bool
    last_reconcile: LastReconcile | None
    audit: AuditPath
    day: DayPnl
    fee_schedule: FeeSchedule
    robot_magics: frozenset[int]
