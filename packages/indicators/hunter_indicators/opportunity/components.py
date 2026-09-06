"""One component at a time: from readings to ``raw``/``normalized``/``contribution``.

Pure functions of what they are given — a vector, a baseline projection, a set of
anomaly states, a regime decision. No clock, no IO, no registry lookup at score
time: the profile in ``profile.py`` already says what to read.

The MAD path reuses T2.3 exactly (``evaluate_deviation`` and the versioned
``mad_piecewise_v1`` transformation) so that a severity in a score and a severity
in an anomaly are the same number computed the same way. What this module adds is
the aggregation, and its one rule is the **fixed denominator**: an input that
could not be read contributes zero to the numerator and still counts in the
denominator, so absence lowers the component instead of promoting whatever
survived.

The components that do **not** read a baseline (regime, anomalies, agent
consensus, external intelligence) live in ``overlays.py`` and share
:func:`assemble_component` with this module, so every component — whatever its
transformation — is quantised, weighted and explained the same way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from hunter_core.domain.enums import TradeDirection
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.anomalies.evaluation import evaluate_deviation
from hunter_indicators.anomalies.severity import NormalizationConfig
from hunter_indicators.baselines.projection import BaselineProjection
from hunter_indicators.features.vector import FeatureVector, Quality
from hunter_indicators.opportunity.model import (
    COMPONENT_QUANTUM,
    CONFIDENCE_QUANTUM,
    REASON_NO_USABLE_INPUT,
    ComponentDefinition,
    ComponentInput,
    ComponentKind,
    ComponentScore,
    DirectionRule,
    InputScore,
    quantize,
)

REASON_NOT_IN_VECTOR = "feature_not_in_vector"
REASON_INELIGIBLE = "ineligible_evaluation"

ZERO = Decimal(0)
HUNDRED = Decimal(100)
_HALF = Decimal("0.5")


def _direction_of(rule: DirectionRule, value: Decimal) -> TradeDirection:
    """The side a reading claims — from the reading, never from its deviation."""
    if rule is DirectionRule.SIGN:
        if value > 0:
            return TradeDirection.LONG
        return TradeDirection.SHORT if value < 0 else TradeDirection.NEUTRAL
    if rule is DirectionRule.POSITIVE_LONG:
        return TradeDirection.LONG if value > 0 else TradeDirection.NEUTRAL
    if rule is DirectionRule.FRACTION_HALF:
        if value > _HALF:
            return TradeDirection.LONG
        return TradeDirection.SHORT if value < _HALF else TradeDirection.NEUTRAL
    return TradeDirection.NEUTRAL


def _oriented(deviation: Decimal, item: ComponentInput) -> Decimal:
    """``d`` turned so that "the direction this input cares about" is positive."""
    from hunter_indicators.anomalies.severity import DetectorSide

    if item.side is DetectorSide.DOWN:
        return -deviation
    if item.side is DetectorSide.BOTH:
        return abs(deviation)
    return deviation


def _score_input(
    item: ComponentInput,
    *,
    market_id: UUID,
    vector: FeatureVector,
    projection: BaselineProjection,
    config: NormalizationConfig,
) -> InputScore:
    """One reading against its baseline: severity, maturity, side, or a reason."""
    value = vector.values.get(item.feature)
    if value is None:
        return InputScore(feature=item.feature, available=False, reason=REASON_NOT_IN_VECTOR)
    if value.quality is not Quality.OK:
        return InputScore(
            feature=item.feature,
            available=False,
            value=value.value,
            reason=value.reason.value if value.reason is not None else value.quality.value,
        )
    reading = value.value
    if reading is None:  # pragma: no cover - FeatureValue forbids it outside UNAVAILABLE
        return InputScore(feature=item.feature, available=False, reason=REASON_NOT_IN_VECTOR)
    lookup = projection.resolve(
        market_id, item.feature, vector.ts, feature_version=item.feature_version
    )
    if not lookup.usable or lookup.revision is None:
        return InputScore(
            feature=item.feature,
            available=False,
            value=reading,
            baseline=lookup.median,
            baseline_id=lookup.baseline_id,
            reason=lookup.reason,
        )
    deviation = evaluate_deviation(reading, lookup.revision, config, item.side)
    if not deviation.available or deviation.value is None or deviation.severity is None:
        return InputScore(
            feature=item.feature,
            available=False,
            value=reading,
            baseline=deviation.baseline,
            scale=deviation.scale,
            baseline_id=lookup.baseline_id,
            reason=deviation.reason,
        )
    return InputScore(
        feature=item.feature,
        available=True,
        value=reading,
        baseline=deviation.baseline,
        scale=deviation.scale,
        deviation=deviation.value,
        severity=deviation.severity,
        maturity=deviation.confidence,
        direction=_direction_of(item.direction_rule, reading),
        baseline_id=lookup.baseline_id,
    )


def assemble_component(
    definition: ComponentDefinition,
    *,
    weight: Decimal,
    inputs: Sequence[InputScore],
    raw: Decimal | None,
    normalized: Decimal | None,
    confidence: Decimal,
    direction: TradeDirection,
    used: int,
    expected: int,
    available: bool,
    reason: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> ComponentScore:
    with localcontext(CONTEXT):
        # The *multiplication* has to happen inside the frozen context too: under
        # an ambient ``prec = 4`` the product would already be rounded before
        # ``quantize`` ever saw it, and 11.9340 would be stored as 11.9300
        # (Astra, T2.4 diff review, must-fix 2).
        contribution = (
            (weight * normalized).quantize(COMPONENT_QUANTUM)
            if available and normalized is not None
            else ZERO.quantize(COMPONENT_QUANTUM)
        )
    return ComponentScore(
        name=definition.name,
        kind=definition.kind,
        transform=definition.transform,
        weight=weight,
        raw=raw,
        normalized=normalized,
        contribution=contribution,
        confidence=quantize(confidence, CONFIDENCE_QUANTUM),
        direction=direction,
        expected=expected,
        used=used,
        available=available,
        inputs=tuple(inputs),
        not_implemented=dict(definition.not_implemented),
        detail=dict(detail or {}),
        reason=reason,
    )


def score_mad_component(
    definition: ComponentDefinition,
    *,
    weight: Decimal,
    market_id: UUID,
    vector: FeatureVector,
    projection: BaselineProjection,
    config: NormalizationConfig,
) -> ComponentScore:
    """A component whose inputs are deviations against the robust baseline."""
    if definition.kind is not ComponentKind.MAD:
        raise ValueError(f"{definition.name} is a {definition.kind} component, not a MAD one")
    scores = [
        _score_input(item, market_id=market_id, vector=vector, projection=projection, config=config)
        for item in definition.inputs
    ]
    expected = definition.expected
    usable = [entry for entry in scores if entry.available]
    with localcontext(CONTEXT):
        denominator = Decimal(expected)
        severity_total = sum((entry.severity or ZERO for entry in usable), ZERO)
        maturity_total = sum((entry.maturity or ZERO for entry in usable), ZERO)
        oriented_total = sum(
            (
                _oriented(entry.deviation or ZERO, item)
                for item, entry in zip(definition.inputs, scores, strict=True)
                if entry.available
            ),
            ZERO,
        )
        vote = sum(
            (
                (entry.severity or ZERO) * _sign(entry.direction)
                for entry in usable
                if entry.direction is not TradeDirection.NEUTRAL
            ),
            ZERO,
        )
        normalized = quantize(severity_total / denominator, COMPONENT_QUANTUM) if usable else None
        raw = quantize(oriented_total / denominator, COMPONENT_QUANTUM) if usable else None
        confidence = maturity_total / denominator if usable else ZERO
    return assemble_component(
        definition,
        weight=weight,
        inputs=scores,
        raw=raw,
        normalized=normalized,
        confidence=confidence,
        direction=_vote_direction(vote),
        used=len(usable),
        expected=expected,
        available=bool(usable),
        reason=None if usable else REASON_NO_USABLE_INPUT,
    )


def _sign(direction: TradeDirection) -> Decimal:
    if direction is TradeDirection.LONG:
        return Decimal(1)
    return Decimal(-1) if direction is TradeDirection.SHORT else ZERO


def _vote_direction(vote: Decimal) -> TradeDirection:
    if vote > 0:
        return TradeDirection.LONG
    return TradeDirection.SHORT if vote < 0 else TradeDirection.NEUTRAL


__all__ = [
    "HUNDRED",
    "REASON_INELIGIBLE",
    "REASON_NOT_IN_VECTOR",
    "ZERO",
    "assemble_component",
    "score_mad_component",
]
