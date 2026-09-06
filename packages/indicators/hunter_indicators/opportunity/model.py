"""The contract of the scorer: profile, component shapes, result and quanta.

Data only. Three rules of the joint M2 decision are enforced by these shapes
rather than by convention:

- **the weights are read, never written here.** :class:`WeightProfile` parses the
  active ``opportunity_weights`` row and raises on a missing key: a scorer that
  defaults a weight would decide with numbers nobody published;
- **absence never redistributes.** A component's denominator is the number of
  inputs its *profile* declares (:attr:`ComponentDefinition.expected`), not the
  number that happened to arrive, so losing the quiet half of a pair cannot
  promote the loud half (Astra, T2.4 design review, item 3). The same fixed
  denominator gives the component's confidence, which is where the loss shows up;
- **direction is declared per input, never inferred from the deviation.** A
  return of −1% against a median of −3% deviates *upwards* while the price falls;
  :class:`DirectionRule` says how each reading becomes a side, and most readings
  (volume, velocity, spread) say nothing about one (Astra, item 5).

Everything a stored decomposition needs to be recomputed travels in
:meth:`ComponentScore.as_wire` — raw, normalised, weight, contribution, and the
per-input evidence with its baseline id.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from hunter_core.domain.enums import TradeDirection
from hunter_indicators.anomalies.severity import DetectorSide

SCORER_VERSION = "opportunity_v1"
"""The version of the scoring procedure itself (aggregation, direction, clip)."""

COMPONENT_PROFILE_VERSION = "components_v1"
"""The version of the roster below: which inputs each component reads."""

SCORE_QUANTUM = Decimal("0.01")
"""``opportunities.score`` is ``NUMERIC(5,2)`` — two decimals, ROUND_HALF_EVEN."""

CONFIDENCE_QUANTUM = Decimal("0.0001")
COMPONENT_QUANTUM = Decimal("0.0001")
"""Components and contributions at four decimals, per ``weights["precision"]``."""

REASON_NO_USABLE_INPUT = "no_usable_input"
REASON_REGIME_UNKNOWN = "regime_unknown"
REASON_REGIME_STALE = "regime_stale"
REASON_ANOMALIES_UNKNOWN = "anomalies_unknown"
REASON_NOT_IMPLEMENTED = "feature_not_implemented"
REASON_NO_AGENTS = "no_agents_until_m4"
REASON_NO_EVIDENCE = "no_eligible_evidence"
REASON_NO_DIRECTIONAL_EVIDENCE = "no_directional_evidence"
"""No directional input carried any weight: nothing was said about a side."""
REASON_DIRECTIONAL_CANCELS = "directional_evidence_cancels"
"""Directional inputs of equal weight pulled opposite ways. A different fact from
the one above, and the two may not share a number (cross review, must-fix 1):
silence is not disagreement, and only disagreement lowers the confidence."""
REASON_REGIME_CONFIDENCE = "regime_confidence_unknown"
REASON_DEGRADED = "degraded"

NO_GAPS: Mapping[str, str] = MappingProxyType({})
"""A component whose profile declares no build gap (a typed, shared default)."""

NO_DETAIL: Mapping[str, Any] = MappingProxyType({})


class ComponentKind(StrEnum):
    """How a component turns readings into 0-100."""

    MAD = "mad"
    """Deviations against the robust baseline, through ``mad_piecewise_v1``."""
    REGIME = "regime"
    ANOMALIES = "anomalies"
    CONSENSUS = "consensus"
    EXTERNAL = "external"


class DirectionRule(StrEnum):
    """How one reading becomes a side — declared per input, never inferred."""

    NONE = "none"
    """The reading says nothing about a side (volume, velocity, spread, funding)."""
    SIGN = "sign"
    """Positive is long, negative is short (signed momentum, book imbalance)."""
    POSITIVE_LONG = "positive_long"
    """Only the positive half means anything (a breakout above the range)."""
    FRACTION_HALF = "fraction_half"
    """A fraction read around one half (taker buy pressure)."""


@dataclass(frozen=True, slots=True)
class ComponentInput:
    """One feature a component reads, with its tail and its direction rule."""

    feature: str
    feature_version: int
    side: DetectorSide
    direction_rule: DirectionRule = DirectionRule.NONE

    def as_wire(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "feature_version": self.feature_version,
            "side": self.side.value,
            "direction_rule": self.direction_rule.value,
        }


@dataclass(frozen=True, slots=True)
class ComponentDefinition:
    """One component of the weight vector, fully described by data."""

    name: str
    kind: ComponentKind
    transform: str
    description: str
    inputs: tuple[ComponentInput, ...] = ()
    not_implemented: Mapping[str, str] = NO_GAPS
    """What ``docs/PIPELINE.md`` §5 asks of this component and this build does not
    have. Excluded from the denominator on purpose: coverage measures what the
    *runtime* could read, and a build gap that never moves would otherwise pin the
    confidence of the component below one forever, hiding real outages behind a
    constant (Astra, T2.4 design review, item 2). The gap is declared here, and it
    is copied into every decomposition."""

    @property
    def expected(self) -> int:
        """The fixed denominator: the inputs this profile declares."""
        return len(self.inputs)

    def as_wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "transform": self.transform,
            "expected": self.expected,
            "inputs": [item.as_wire() for item in self.inputs],
            "not_implemented": dict(sorted(self.not_implemented.items())),
        }


@dataclass(frozen=True, slots=True)
class InputScore:
    """What one input contributed, and everything needed to recompute it."""

    feature: str
    available: bool
    value: Decimal | None = None
    baseline: Decimal | None = None
    scale: Decimal | None = None
    deviation: Decimal | None = None
    severity: Decimal | None = None
    maturity: Decimal | None = None
    direction: TradeDirection = TradeDirection.NEUTRAL
    baseline_id: UUID | None = None
    reason: str | None = None

    def as_wire(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "available": self.available,
            "value": self.value,
            "baseline": self.baseline,
            "scale": self.scale,
            "deviation": self.deviation,
            "severity": self.severity,
            "maturity": self.maturity,
            "direction": self.direction.value,
            "baseline_id": self.baseline_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ComponentScore:
    """``raw``, ``normalized``, ``weight``, ``contribution`` — and why."""

    name: str
    kind: ComponentKind
    transform: str
    weight: Decimal
    raw: Decimal | None
    normalized: Decimal | None
    contribution: Decimal
    confidence: Decimal
    direction: TradeDirection
    expected: int
    used: int
    available: bool
    inputs: tuple[InputScore, ...] = ()
    not_implemented: Mapping[str, str] = NO_GAPS
    detail: Mapping[str, Any] = NO_DETAIL
    reason: str | None = None

    @property
    def counts_for_confidence(self) -> bool:
        """A zero-weight component grades nothing: it cannot lower a confidence it
        does not move, and it must not raise one either."""
        return self.weight > 0

    def as_wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "transform": self.transform,
            "weight": self.weight,
            "raw": self.raw,
            "normalized": self.normalized,
            "contribution": self.contribution,
            "confidence": self.confidence,
            "direction": self.direction.value,
            "expected": self.expected,
            "used": self.used,
            "available": self.available,
            "reason": self.reason,
            "inputs": [item.as_wire() for item in self.inputs],
            "not_implemented": dict(sorted(self.not_implemented.items())),
            "detail": dict(sorted(self.detail.items())),
        }


@dataclass(frozen=True, slots=True)
class EarlyMovement:
    """The signed term outside the weight budget: ``magnitude * e``."""

    e: int
    magnitude: Decimal
    contribution: Decimal
    stage: str
    stage_direction: str
    reason: str | None = None

    def as_wire(self) -> dict[str, Any]:
        return {
            "e": self.e,
            "magnitude": self.magnitude,
            "contribution": self.contribution,
            "stage": self.stage,
            "stage_direction": self.stage_direction,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """One evaluation: the score, its decomposition and the evidence behind it."""

    score: Decimal | None
    confidence: Decimal
    direction: TradeDirection
    agreement: Decimal | None
    """How much the directional evidence agrees with itself, or ``None`` when
    there was none to agree — a fact the reader has to be able to tell from a
    perfect standoff, which is ``0``."""
    components: tuple[ComponentScore, ...]
    early_movement: EarlyMovement
    observation_ts: datetime
    weights_version: str
    versions: Mapping[str, str]
    eligible: bool = True
    reason: str | None = None
    direction_reason: str | None = None
    baseline_ids: tuple[UUID, ...] = ()

    def component(self, name: str) -> ComponentScore:
        for item in self.components:
            if item.name == name:
                return item
        raise KeyError(name)

    def decomposition(self) -> dict[str, Any]:
        """``opportunities.decomposition`` — sorted, byte-stable, self-adding."""
        return {
            "scorer_version": SCORER_VERSION,
            "profile_version": COMPONENT_PROFILE_VERSION,
            "weights_version": self.weights_version,
            "versions": dict(sorted(self.versions.items())),
            "observation_ts": self.observation_ts,
            "eligible": self.eligible,
            "reason": self.reason,
            "score": self.score,
            "confidence": self.confidence,
            "direction": self.direction.value,
            "direction_reason": self.direction_reason,
            "agreement": self.agreement,
            "early_movement": self.early_movement.as_wire(),
            "components": [item.as_wire() for item in sorted(self.components, key=_by_name)],
            "baseline_ids": [str(item) for item in self.baseline_ids],
        }


def _by_name(component: ComponentScore) -> str:
    return component.name


def quantize(value: Decimal, quantum: Decimal) -> Decimal:
    """``value`` at ``quantum``, under the frozen context (ROUND_HALF_EVEN)."""
    from decimal import localcontext

    from hunter_core.strategies.numeric import CONTEXT

    with localcontext(CONTEXT):
        return value.quantize(quantum)


def clip(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return min(max(value, low), high)


__all__ = [
    "COMPONENT_PROFILE_VERSION",
    "COMPONENT_QUANTUM",
    "CONFIDENCE_QUANTUM",
    "REASON_ANOMALIES_UNKNOWN",
    "REASON_DEGRADED",
    "REASON_DIRECTIONAL_CANCELS",
    "REASON_NOT_IMPLEMENTED",
    "REASON_NO_AGENTS",
    "REASON_NO_DIRECTIONAL_EVIDENCE",
    "REASON_NO_EVIDENCE",
    "REASON_NO_USABLE_INPUT",
    "REASON_REGIME_CONFIDENCE",
    "REASON_REGIME_STALE",
    "REASON_REGIME_UNKNOWN",
    "SCORER_VERSION",
    "SCORE_QUANTUM",
    "ComponentDefinition",
    "ComponentInput",
    "ComponentKind",
    "ComponentScore",
    "DirectionRule",
    "EarlyMovement",
    "InputScore",
    "ScoreResult",
    "clip",
    "quantize",
]
