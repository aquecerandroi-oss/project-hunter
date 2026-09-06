"""The contract of the stage classifier: thresholds, inputs, state, decision.

Data only, so the classifier (``classifier.py``) and its consumers depend on the
same shapes without depending on each other. The thresholds are read from
``opportunity_weights.weights["stage"]`` — never a default in code — and the
decision carries ``state_in``/``state_out`` plus every value it read, which is
what lets a stored stage be recomputed after the profile moves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from hunter_core.domain.enums import OpportunityStage, TradeDirection

REASON_ATR_WARMUP = "atr_warmup"  # no ATR yet, or an ATR of zero: ``r`` has no denominator
REASON_ATR_DEGRADED = "atr_degraded"  # an ATR exists, but this reading cannot be believed
REASON_RETURN_UNAVAILABLE = "return_1h_unavailable"
REASON_NOT_CONFIRMED = "not_confirmed"  # EARLY territory, confirmations did not all fire
REASON_QUALITY_LOST = "quality_lost"
REASON_STAGE_WITHDRAWN = "stage_withdrawn"  # what was published stopped being supported
REASON_STALE_OBSERVATION = "stale_observation"

STAGE_BASIS_RATIO = "ratio"
STAGE_BASIS_EXHAUSTION = "exhaustion"

RETURN_KEY = "return_1h"
ATR_KEY = "atr_14_pct"
RETURN_4H_KEY = "return_4h"
CONFIRMATION_KEYS = (
    "relative_volume_1h",
    "trade_velocity_1m",
    "open_interest_change_1h",
    "buy_pressure_5m",
)
READ_KEYS = (RETURN_KEY, ATR_KEY, RETURN_4H_KEY, *CONFIRMATION_KEYS)
"""Every feature the classifier reads — what the envelope records as evidence."""

_NO_CONFIRMATIONS: Mapping[str, bool] = MappingProxyType({})
_NO_VALUES: Mapping[str, Decimal | None] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class StageThresholds:
    """The versioned parameters of the classifier — read, never hardcoded."""

    r_early_max: Decimal
    r_developing_max: Decimal
    relative_volume_1h_min: Decimal
    trade_velocity_baseline_multiple_min: Decimal
    open_interest_change_1h_min: Decimal
    buy_pressure_5m_long_min: Decimal
    buy_pressure_5m_short_max: Decimal
    extended_return_4h_atr_multiple: Decimal
    extended_relative_volume_15m_declines: int
    extended_relative_volume_15m_closes: int
    confirmations: int
    weights_version: str

    @classmethod
    def from_weights(cls, weights: Mapping[str, Any], *, version: str) -> StageThresholds:
        """Read ``weights["stage"]``; a missing key raises instead of defaulting.

        Every field but ``weights_version`` is a profile parameter and its declared
        type decides the parsing, so no second list can drift."""
        block: Mapping[str, Any] = weights["stage"]
        params: dict[str, Any] = {}
        for item in fields(cls):
            if item.name == "weights_version":
                continue
            if item.type == "Decimal":
                params[item.name] = Decimal(str(block[item.name]))
            elif item.type == "int":
                params[item.name] = int(block[item.name])
            else:  # a new annotation needs a parser here, not a silent int()
                raise TypeError(f"{item.name}: {item.type} has no declared parser")
        return cls(weights_version=version, **params)


@dataclass(frozen=True, slots=True)
class StageInputs:
    """What the vector does not carry: the median of the ``trade_velocity_1m``
    baseline (resolved by the caller, so this stays pure) and the
    ``relative_volume_15m`` readings at the last 15m closes, oldest first."""

    trade_velocity_baseline: Decimal | None = None
    relative_volume_15m_closes: tuple[Decimal, ...] = ()


@dataclass(frozen=True, slots=True)
class StageState:
    """The hysteresis, serialised into the envelope as ``state_in``/``state_out``.

    ``direction`` is the side of the **published** stage, not of the observation
    being evaluated: an EARLY confirmed long two observations ago stays long
    while the current minute prints a negative return, and the side has to
    survive a restart with the stage it belongs to. Publishing is therefore a
    claim about the *pair* ``(stage, direction)``: flipping the sign is a change
    like any other and needs the same two distinct observations, which is why
    ``candidate_direction`` is counted alongside ``candidate``.
    """

    stage: OpportunityStage = OpportunityStage.NONE
    basis: str = ""
    candidate: OpportunityStage = OpportunityStage.NONE
    confirmations: int = 0
    last_observation_ts: datetime | None = None
    direction: TradeDirection = TradeDirection.NEUTRAL
    candidate_direction: TradeDirection = TradeDirection.NEUTRAL
    unsupported: int = 0
    """Consecutive observations that did not support the published pair.

    Withdrawing a claim and publishing a new one are different decisions.
    Counting only the *candidate* keeps a stage alive forever when the market
    alternates — every observation restarts the candidate count, it never
    reaches two, and a DEVELOPING published half an hour ago is still published
    (Astra, revisão do fix-pass da T2.3). Two observations that do not support
    what is published take it down to ``NONE``; the replacement still needs two
    observations of its own."""

    def as_wire(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "basis": self.basis,
            "candidate": self.candidate.value,
            "confirmations": self.confirmations,
            "last_observation_ts": self.last_observation_ts,
            "direction": self.direction.value,
            "candidate_direction": self.candidate_direction.value,
            "unsupported": self.unsupported,
        }


EMPTY_STAGE_STATE = StageState()  # a market nobody has classified yet (module singleton)
NO_STAGE_EXTRAS = StageInputs()  # no baseline, no 15m history: the honest cold start


@dataclass(frozen=True, slots=True)
class StageDecision:
    """One evaluation: what is published, what is pending, and on what evidence."""

    stage: OpportunityStage
    candidate: OpportunityStage
    observation_ts: datetime
    state_in: StageState
    state_out: StageState
    thresholds_version: str
    basis: str = ""
    direction: TradeDirection = TradeDirection.NEUTRAL
    """The side of **this observation** (the sign of ``return_1h``). The side of
    what is published is ``published_direction``, and the two differ whenever a
    move flips while a stage confirmed earlier is still standing."""
    r: Decimal | None = None
    reason: str | None = None
    invalidated: bool = False
    confirmations: Mapping[str, bool] = _NO_CONFIRMATIONS
    values: Mapping[str, Decimal | None] = _NO_VALUES
    inputs: StageInputs = NO_STAGE_EXTRAS
    """The external evidence (baseline median, 15m volume history) the vector does
    not carry. In the envelope so a stored decision can be recomputed — recording
    "the confirmation fired" without the number it fired against would not be
    reproducible (Astra, T2.3 diff review, must-fix 5)."""

    @property
    def published_direction(self) -> TradeDirection:
        """The side of the stage that is actually published, from the state."""
        return self.state_out.direction

    def as_wire(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "candidate": self.candidate.value,
            "basis": self.basis,
            "direction": self.direction.value,
            "published_direction": self.published_direction.value,
            "observation_ts": self.observation_ts,
            "r": self.r,
            "reason": self.reason,
            "invalidated": self.invalidated,
            "confirmations": dict(sorted(self.confirmations.items())),
            "values": dict(sorted(self.values.items())),
            "inputs": {
                "trade_velocity_baseline": self.inputs.trade_velocity_baseline,
                "relative_volume_15m_closes": list(self.inputs.relative_volume_15m_closes),
            },
            "thresholds_version": self.thresholds_version,
            "state_in": self.state_in.as_wire(),
            "state_out": self.state_out.as_wire(),
        }


__all__ = [
    "ATR_KEY",
    "CONFIRMATION_KEYS",
    "EMPTY_STAGE_STATE",
    "NO_STAGE_EXTRAS",
    "READ_KEYS",
    "REASON_ATR_DEGRADED",
    "REASON_ATR_WARMUP",
    "REASON_NOT_CONFIRMED",
    "REASON_QUALITY_LOST",
    "REASON_RETURN_UNAVAILABLE",
    "REASON_STAGE_WITHDRAWN",
    "REASON_STALE_OBSERVATION",
    "RETURN_4H_KEY",
    "RETURN_KEY",
    "STAGE_BASIS_EXHAUSTION",
    "STAGE_BASIS_RATIO",
    "StageDecision",
    "StageInputs",
    "StageState",
    "StageThresholds",
]
