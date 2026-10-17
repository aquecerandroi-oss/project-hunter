"""What the B3 engine returns (docs/RISK_ENGINE_B3.md §8.2, §8.4).

The decision is evidence, so its consistency is enforced by the model and not by review:
an entry decision has exactly the 25 checks in id order with the contract's names;
``approved`` is true **iff** every check passed and ``n_final ≥ 1``; ``reasons`` is
derived from the checks (id order) plus ``sizing_zero``. A hand-built decision that claims
approval next to a failed check does not construct.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import Final, Self

from pydantic import Field, model_validator

from hunter_core.strategies.canonical import canonical_json
from hunter_risk_b3.base import B3Model, UtcDatetime
from hunter_risk_b3.enums import CheckState, DecisionKind, KillCause, KillSwitchState

__all__ = [
    "CHECK_NAMES",
    "SIZING_ZERO",
    "B3Check",
    "B3Sizing",
    "CheckValue",
    "RiskDecision",
    "check_failed",
    "check_passed",
    "check_unavailable",
]

CHECK_NAMES: Final[tuple[str, ...]] = (
    "kill_switch", "account_mode", "terminal_state", "symbol_whitelist", "trading_day",
    "entry_window", "flatten_margin", "quote_fresh", "spread", "open_positions",
    "order_in_flight", "contracts_caps", "trades_today", "daily_loss", "stop_geometry",
    "trade_risk_vs_allowance", "trade_risk_cap", "margin", "broker_reject_breaker",
    "reconciliation_ok", "audit_path", "signal_validity", "spec_unchanged", "slippage_guard",
    "equity_floor",
)  # fmt: skip
"""§8.2, index = id − 1."""

SIZING_ZERO: Final = "sizing_zero"
CheckValue = Decimal | int | str | None


class B3Check(B3Model):
    """``{id, name, state, value, limit, input_ts, reason, message}`` (§8.2)."""

    id: int = Field(ge=1, le=25)
    name: str = Field(min_length=1)
    state: CheckState
    value: CheckValue = None
    limit: CheckValue = None
    input_ts: UtcDatetime | None = None
    reason: str | None = None
    message: str = ""

    @property
    def passed(self) -> bool:
        return self.state is CheckState.PASSED

    @model_validator(mode="after")
    def _reason_iff_not_passed(self) -> Self:
        if self.passed and self.reason is not None:
            raise ValueError(f"{self.name}: a passed check carries no reason")
        if not self.passed and not self.reason:
            raise ValueError(f"{self.name}: a {self.state} check needs its reason")
        return self


def _check(
    cid: int,
    state: CheckState,
    reason: str | None,
    *,
    value: CheckValue = None,
    limit: CheckValue = None,
    input_ts: UtcDatetime | None = None,
    message: str = "",
) -> B3Check:
    return B3Check(
        id=cid, name=CHECK_NAMES[cid - 1], state=state, value=value, limit=limit,
        input_ts=input_ts, reason=reason, message=message,
    )  # fmt: skip


def check_passed(
    cid: int, *, value: CheckValue = None, limit: CheckValue = None,
    input_ts: UtcDatetime | None = None, message: str = "",
) -> B3Check:  # fmt: skip
    return _check(cid, CheckState.PASSED, None, value=value, limit=limit, input_ts=input_ts,
                  message=message)  # fmt: skip


def check_failed(
    cid: int, reason: str, *, value: CheckValue = None, limit: CheckValue = None,
    input_ts: UtcDatetime | None = None, message: str = "",
) -> B3Check:  # fmt: skip
    return _check(cid, CheckState.FAILED, reason, value=value, limit=limit, input_ts=input_ts,
                  message=message)  # fmt: skip


def check_unavailable(
    cid: int, reason: str, *, value: CheckValue = None, limit: CheckValue = None,
    input_ts: UtcDatetime | None = None, message: str = "",
) -> B3Check:  # fmt: skip
    return _check(cid, CheckState.UNAVAILABLE, reason, value=value, limit=limit,
                  input_ts=input_ts, message=message)  # fmt: skip


class B3Sizing(B3Model):
    caps: dict[str, int | None]
    """§8.3 ceilings in contract order; ``None`` = not computable from the inputs."""
    n_raw: int | None
    n_final: int = Field(ge=0)
    binding_constraint: str | None
    risk_per_contract_brl: Decimal | None
    risk_modeled_brl: Decimal | None
    allowance_brl: Decimal | None
    limit_price: Decimal | None
    bracket_gap_ticks: None = None
    """Always null for an entry (§8.4); the bracket records its own gap (§5.1)."""


class RiskDecision(B3Model):
    kind: DecisionKind
    proposal_id: uuid.UUID | None
    approved: bool
    reasons: tuple[str, ...]
    checks: tuple[B3Check, ...]
    sizing: B3Sizing | None
    kill_switch_effective: KillSwitchState
    triggers: tuple[KillCause, ...]
    limits_version: str | None
    grid_version: str | None
    spec_pin_id: str | None
    as_of: UtcDatetime | None
    approved_at: UtcDatetime | None
    expires_at: UtcDatetime | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.kind is DecisionKind.EXIT:
            if not self.approved or self.reasons:
                raise ValueError("an exit decision is always approved, without reasons (§8.6)")
            return self
        if [c.id for c in self.checks] != list(range(1, 26)):
            raise ValueError("an entry decision carries the 25 checks in id order")
        if any(c.name != CHECK_NAMES[c.id - 1] for c in self.checks):
            raise ValueError("check names must be the contract's names")
        if self.proposal_id is None or self.sizing is None or self.as_of is None:
            raise ValueError("an entry decision carries proposal_id, sizing and as_of")
        all_passed = all(c.passed for c in self.checks)
        if self.approved != (all_passed and self.sizing.n_final >= 1):
            raise ValueError("approved iff every check passed and n_final >= 1")
        derived = tuple(c.reason for c in self.checks if c.reason is not None)
        if self.sizing.n_raw is not None and self.sizing.n_final < 1:
            derived = (*derived, SIZING_ZERO)
        if self.reasons != derived:
            raise ValueError(f"reasons {self.reasons} differ from the checks' {derived}")
        return self

    def decision_hash(self) -> str:
        """sha256 of the canonical JSON — same inputs, same hash (§8.5 determinism)."""
        return hashlib.sha256(canonical_json(self.model_dump())).hexdigest()
