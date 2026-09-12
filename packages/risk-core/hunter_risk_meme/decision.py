"""What the meme engine returns and what ``meme_live_orders.admission`` stores.

The same three properties as ``hunter_risk.decision`` (§4 of the meme contract):
every evaluable check is recorded even after the first failure; ``unavailable``
is a third state that rejects; the winning ceiling is published
(``sizing.binding_constraint``). One addition the meme doctrine asks for: every
failed or unavailable check carries the **refusal name** of §4's table
(``MemeCheck.refusal``), so the desk and the diary can say *which* refusal, not
only which check.
"""

from __future__ import annotations

import json
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from hunter_core.domain.enums import KillSwitchState
from hunter_core.strategies.canonical import canonical_json
from hunter_risk_meme.base import MemeModel

__all__ = [
    "CheckState",
    "Counterfactual",
    "LimitCap",
    "MemeCheck",
    "MemeDecision",
    "MemeExitPlan",
    "MemeSizing",
    "check",
    "unavailable",
]


class CheckState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class MemeCheck(MemeModel):
    name: str = Field(min_length=1)
    state: CheckState
    refusal: str | None = None
    """The §4 refusal name when the check did not pass; ``None`` when it passed."""
    value: Decimal | None = None
    limit: Decimal | None = None
    input_ts: str | None = None
    message: str = ""

    @property
    def passed(self) -> bool:
        return self.state is CheckState.PASSED

    @model_validator(mode="after")
    def _named(self) -> MemeCheck:
        if self.state is CheckState.PASSED and self.refusal is not None:
            raise ValueError(f"{self.name}: a passed check carries no refusal")
        if self.state is not CheckState.PASSED and not self.refusal:
            raise ValueError(f"{self.name}: a refusal needs a name")
        return self


def check(
    name: str,
    ok: bool,
    refusal: str,
    *,
    value: Decimal | None = None,
    limit: Decimal | None = None,
    input_ts: str | None = None,
    message: str = "",
) -> MemeCheck:
    return MemeCheck(
        name=name,
        state=CheckState.PASSED if ok else CheckState.FAILED,
        refusal=None if ok else refusal,
        value=value,
        limit=limit,
        input_ts=input_ts,
        message=message,
    )


def unavailable(
    name: str, refusal: str, message: str, *, limit: Decimal | None = None
) -> MemeCheck:
    return MemeCheck(
        name=name, state=CheckState.UNAVAILABLE, refusal=refusal, limit=limit, message=message
    )


class LimitCap(MemeModel):
    name: str = Field(min_length=1)
    sol: Decimal | None
    """``None`` when the ceiling does not constrain."""
    limit: Decimal | None = None
    detail: str = ""


class Counterfactual(MemeModel):
    name: str = Field(min_length=1)
    sol: Decimal | None = None
    unavailable_reason: str | None = None


class MemeSizing(MemeModel):
    requested_sol: Decimal
    caps: tuple[LimitCap, ...]
    binding_limit: LimitCap
    binding_constraint: str
    tied_limits: tuple[str, ...] = ()
    size_without_multipliers: Counterfactual
    size_without_participation: Counterfactual
    sol_before_multiplier: Decimal
    kill_switch_multiplier: Decimal
    sol_final: Decimal
    """Total SOL the buy takes from the wallet (curve + curve fees), before the fixed
    execution costs below."""
    fixed_costs_sol: Decimal
    """Network fee + priority fee + tip + rent when an ATA has to be created."""
    price_impact_pct: Decimal
    max_sol_cost_sol: Decimal
    """``sol_final × (1 + max_slippage)`` — what goes into the instruction (§9.4)."""


class MemeExitPlan(MemeModel):
    position_id: str
    requested_tokens: int
    approved_tokens: int
    reason: str
    route: Literal["curve", "pumpswap"]
    clamped: bool = False


class MemeDecision(MemeModel):
    approved: bool
    kind: Literal["entry", "exit"]
    proposal_id: str
    wallet_id: str
    mint: str
    limits_profile: str
    effective_kill_switch: KillSwitchState
    cancel_pending: bool
    checks: tuple[MemeCheck, ...]
    sizing: MemeSizing | None = None
    exit_plan: MemeExitPlan | None = None

    @model_validator(mode="after")
    def _consistent(self) -> MemeDecision:
        names = [c.name for c in self.checks]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate check names in one decision: {sorted(duplicates)}")
        if self.approved and self.refusals:
            raise ValueError(f"approved with refusals: {list(self.refusals)}")
        if self.approved and self.kind == "entry" and self.sizing is None:
            raise ValueError("an approved entry carries its sizing")
        return self

    @property
    def refusals(self) -> tuple[str, ...]:
        """The §4 refusal names, in evaluation order."""
        return tuple(c.refusal for c in self.checks if c.refusal is not None)

    @property
    def first_refusal(self) -> str | None:
        return self.refusals[0] if self.refusals else None

    def to_jsonable(self) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(canonical_json(self.model_dump()))
        return parsed
