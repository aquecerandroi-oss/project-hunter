"""What the engine returns and what ``trade_proposals.risk_decision`` stores.

Three properties the rest of the system leans on:

- **every evaluable check is here**, passed or not (RISK_ENGINE.md §3). The
  engine does not stop at the first failure, because "why was this refused" is
  almost never answered by the first refusal alone;
- ``unavailable`` is a **third state**, not a synonym of ``failed`` (``R-OPS-1``).
  Both reject an entry, and they are different facts: one says the limit was
  violated, the other says the limit could not be measured. A panel that could
  not tell them apart would report a healthy book as a violated one;
- the winning ceiling is **published** (``R-PROV-1``): ``sizing.binding_limit``
  says which of the nine ceilings produced the size, with its value and the
  limit behind it, so "the Risk Engine allows 1.2 %" is a sentence a number can
  contradict.

:meth:`RiskDecision.to_jsonable` goes through
``hunter_core.strategies.canonical.canonical_json``: numbers become normalised
decimal strings, timestamps ISO-8601 ``Z``. A value read back from JSONB is the
value that was decided, with no float in between.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from hunter_core.domain.enums import ExitReason, KillSwitchState
from hunter_core.strategies.canonical import canonical_json
from hunter_risk.base import RiskModel
from hunter_risk.inputs import MarketIdentity


class CheckState(StrEnum):
    """Outcome of one check."""

    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    """The input the check needs was absent, stale or degraded. Rejects an entry."""


class RiskCheck(RiskModel):
    """One line of the Explanation Panel."""

    name: str = Field(min_length=1)
    state: CheckState
    value: Decimal | None = None
    limit: Decimal | None = None
    message: str = ""

    @property
    def passed(self) -> bool:
        return self.state is CheckState.PASSED


def check(
    name: str,
    ok: bool,
    *,
    value: Decimal | None = None,
    limit: Decimal | None = None,
    message: str = "",
) -> RiskCheck:
    """A check that was evaluated: ``passed`` or ``failed``."""
    return RiskCheck(
        name=name,
        state=CheckState.PASSED if ok else CheckState.FAILED,
        value=value,
        limit=limit,
        message=message,
    )


def unavailable(name: str, message: str, *, limit: Decimal | None = None) -> RiskCheck:
    """A check whose input was missing, stale or degraded. Rejects an entry."""
    return RiskCheck(name=name, state=CheckState.UNAVAILABLE, limit=limit, message=message)


class LimitCap(RiskModel):
    """One ceiling of the sizing, in quote notional."""

    name: str = Field(min_length=1)
    notional: Decimal | None
    """``None`` when this ceiling does not constrain (e.g. a validated beta of 0)."""
    limit: Decimal | None = None
    """The configured limit the ceiling came from, for the panel."""
    detail: str = ""


class Counterfactual(RiskModel):
    """A "what would the size have been" number - v2 §4.

    Two of them exist and they are **never** reported as one: the kill-switch
    step (``size_without_multipliers``) and the bite of the participation rule
    (``size_without_participation``) answer different questions, and confusing
    them produces the wrong sentence in both directions. When the input is
    missing the number is ``None`` **with a reason**, never a zero.
    """

    name: str = Field(min_length=1)
    qty: Decimal | None = None
    notional: Decimal | None = None
    unavailable_reason: str | None = None


class Sizing(RiskModel):
    """How the size was reached, in the order it was reached."""

    entry_ref: Decimal
    """The reference the proposal carried, kept as evidence of what was asked."""
    sizing_price: Decimal
    """The price every ceiling was actually measured at: the **worse** of
    ``entry_ref`` and the observed price (review of 2026-09-06, finding 2). Equal
    to ``entry_ref`` when the market has not moved away from it; above it when
    the market has, so a stale reference never buys more units than the market
    would sell."""
    stop: Decimal
    """The stop the strategy declared. The engine never moves it."""
    stop_distance_pct: Decimal
    cost_pct: Decimal
    """Round-trip cost hypothesis folded into the planned loss, not into the price."""
    caps: tuple[LimitCap, ...]
    binding_limit: LimitCap
    """The ceiling that won, **before** the kill switch multiplier (``R-PROV-1``)."""
    binding_constraint: str
    """Its name - the field ``docs/RISK_ENGINE.md`` v2 §4 calls out by that name."""
    size_without_multipliers: Counterfactual
    size_without_participation: Counterfactual
    tied_limits: tuple[str, ...] = ()
    """Other ceilings that produced exactly the same number."""
    notional_before_multiplier: Decimal
    kill_switch_multiplier: Decimal
    notional_after_multiplier: Decimal
    """``R-KS-2``: the same proposal with and without the multiplier, side by side."""
    qty: Decimal
    """Rounded **down** to ``step_size``. Rounding up would exceed a ceiling."""
    notional: Decimal
    planned_risk_quote: Decimal
    planned_risk_pct: Decimal


class ExitPlan(RiskModel):
    """A protective exit, always allowed, never larger than the position."""

    position_id: uuid.UUID
    requested_qty: Decimal
    approved_qty: Decimal
    reason: ExitReason
    clamped: bool = False
    """True when the request asked for more than the position holds; spot cannot
    sell what it does not have, so the quantity is reduced and the fact recorded
    instead of the exit being refused."""


class RiskDecision(RiskModel):
    """The record persisted in ``trade_proposals.risk_decision``."""

    approved: bool
    kind: Literal["entry", "exit"]
    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    market: MarketIdentity
    limits_profile: str
    effective_kill_switch: KillSwitchState
    cancel_pending: bool
    """Directive §5: BLOQUEADO cancels pending entries - and nothing else."""
    shadow_only: bool
    """Directive §4: without a validated beta the asset stays in shadow."""
    checks: tuple[RiskCheck, ...]
    sizing: Sizing | None = None
    exit_plan: ExitPlan | None = None

    @model_validator(mode="after")
    def _consistent(self) -> RiskDecision:
        names = [check.name for check in self.checks]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"duplicate check names in one decision: {sorted(duplicates)}")
        if self.approved and self.rejection_reasons:
            raise ValueError(
                "a decision cannot be approved while a check did not pass: "
                f"{list(self.rejection_reasons)}"
            )
        return self

    @property
    def rejection_reasons(self) -> tuple[str, ...]:
        """Names of the checks that did not pass, in evaluation order."""
        return tuple(check.name for check in self.checks if not check.passed)

    @property
    def binding_limit(self) -> LimitCap | None:
        """The ceiling that decided the size, when there was a size."""
        return None if self.sizing is None else self.sizing.binding_limit

    def to_jsonable(self) -> dict[str, Any]:
        """The canonical JSON object for ``trade_proposals.risk_decision``."""
        parsed: dict[str, Any] = json.loads(canonical_json(self.model_dump()))
        return parsed
