"""One detector against one feature vector: a pure verdict, with its reasons.

``evaluate_detector`` is a function of ``(definition, vector, projection,
config)`` and nothing else — no clock, no store, no Redis. The baselines arrive
already resolved in a :class:`BaselineProjection` built for the cut, which is
what lets the same call run in the scanner, in a bootstrap and in a replay and
produce the same bytes.

**Two axes, never collapsed.** ``evaluation_state`` says whether the data behind
the verdict can be believed (``ok`` / ``stale`` / ``unknown``); the anomaly's
``status`` says where it is in its life. A degraded reading is ``stale``: the
number is shown, and it is *ineligible* — it does not update a severity and it
does not advance the resolution clock (``docs/PIPELINE.md`` §2, "dados degradados
não alimentam anomalias"). Missing data, an immature baseline or a flat baseline
are ``unknown``, each with its own reason — and "insufficient history" is
deliberately not spelled the same way as "stale source".
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyType
from hunter_core.domain.types import ensure_utc
from hunter_indicators.anomalies.detectors import (
    DEFAULT_DETECTORS,
    REASON_DISABLED,
    REASON_NO_FEATURE,
    DetectorDefinition,
)
from hunter_indicators.anomalies.severity import (
    AnomalyDirection,
    NormalizationConfig,
    evaluate_deviation,
)
from hunter_indicators.baselines.projection import BaselineProjection
from hunter_indicators.features.vector import FeatureVector, Quality


@dataclass(frozen=True, slots=True)
class AnomalyEvaluation:
    """What one detector saw at one instant, whether or not it fires."""

    market_id: uuid.UUID
    type: AnomalyType
    observation_ts: datetime
    evaluation_state: AnomalyEvaluationState
    detector_version: str
    normalization_version: str
    feature: str
    feature_version: int
    unit: str
    severity: Decimal | None = None
    confidence: Decimal | None = None
    baseline: Decimal | None = None
    current_value: Decimal | None = None
    deviation: Decimal | None = None
    direction: AnomalyDirection = AnomalyDirection.FLAT
    reason: str | None = None
    detail: str | None = None
    baseline_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))

    @property
    def eligible(self) -> bool:
        """Only an ``ok`` evaluation with a number may change an anomaly."""
        return self.evaluation_state is AnomalyEvaluationState.OK and self.severity is not None

    def fires(self, definition: DetectorDefinition) -> bool:
        return (
            self.eligible
            and self.severity is not None
            and (self.severity >= definition.fire_min_severity)
        )

    def holds(self, definition: DetectorDefinition) -> bool:
        return (
            self.eligible
            and self.severity is not None
            and (self.severity >= definition.hold_min_severity)
        )

    def as_wire(self) -> dict[str, Any]:
        """The evidence an ``anomalies`` row carries in ``metadata``."""
        return {
            "type": self.type.value,
            "observation_ts": self.observation_ts,
            "evaluation_state": self.evaluation_state.value,
            "eligible": self.eligible,
            "detector_version": self.detector_version,
            "normalization_version": self.normalization_version,
            "feature": self.feature,
            "feature_version": self.feature_version,
            "unit": self.unit,
            "severity": self.severity,
            "confidence": self.confidence,
            "baseline": self.baseline,
            "current_value": self.current_value,
            "deviation": self.deviation,
            "direction": self.direction.value,
            "reason": self.reason,
            "detail": self.detail,
            "baseline_ids": [str(item) for item in self.baseline_ids],
        }


def _unknown(
    definition: DetectorDefinition,
    config: NormalizationConfig,
    *,
    market_id: uuid.UUID,
    observation_ts: datetime,
    reason: str,
    detail: str | None = None,
    current_value: Decimal | None = None,
    baseline: Decimal | None = None,
    baseline_ids: tuple[uuid.UUID, ...] = (),
) -> AnomalyEvaluation:
    return AnomalyEvaluation(
        market_id=market_id,
        type=definition.type,
        observation_ts=observation_ts,
        evaluation_state=AnomalyEvaluationState.UNKNOWN,
        detector_version=definition.identity,
        normalization_version=config.identity,
        feature=definition.feature,
        feature_version=definition.feature_version,
        unit=definition.unit,
        reason=reason,
        detail=detail,
        current_value=current_value,
        baseline=baseline,
        baseline_ids=baseline_ids,
    )


def evaluate_detector(
    definition: DetectorDefinition,
    *,
    market_id: uuid.UUID,
    vector: FeatureVector,
    projection: BaselineProjection,
    config: NormalizationConfig,
) -> AnomalyEvaluation:
    """``definition`` against ``vector``, judged by the baselines in ``projection``."""
    observation_ts = vector.ts
    if not definition.enabled:
        return _unknown(
            definition,
            config,
            market_id=market_id,
            observation_ts=observation_ts,
            reason=REASON_DISABLED,
            detail=definition.disabled_reason,
        )
    value = vector.values.get(definition.feature)
    if value is None:
        return _unknown(
            definition,
            config,
            market_id=market_id,
            observation_ts=observation_ts,
            reason=REASON_NO_FEATURE,
        )
    if value.quality is Quality.UNAVAILABLE or value.value is None:
        return _unknown(
            definition,
            config,
            market_id=market_id,
            observation_ts=observation_ts,
            reason=value.reason.value if value.reason is not None else REASON_NO_FEATURE,
        )
    lookup = projection.resolve(
        market_id,
        definition.feature,
        observation_ts,
        feature_version=definition.feature_version,
    )
    if not lookup.usable or lookup.revision is None:
        return _unknown(
            definition,
            config,
            market_id=market_id,
            observation_ts=observation_ts,
            reason=lookup.reason or "no_baseline",
            current_value=value.value,
            baseline=lookup.median,
            baseline_ids=() if lookup.baseline_id is None else (lookup.baseline_id,),
        )
    baseline_ids = () if lookup.baseline_id is None else (lookup.baseline_id,)
    deviation = evaluate_deviation(value.value, lookup.revision, config, definition.side)
    if not deviation.available:
        return _unknown(
            definition,
            config,
            market_id=market_id,
            observation_ts=observation_ts,
            reason=deviation.reason or "no_deviation",
            current_value=value.value,
            baseline=deviation.baseline,
            baseline_ids=baseline_ids,
        )
    state = (
        AnomalyEvaluationState.OK if value.quality is Quality.OK else AnomalyEvaluationState.STALE
    )
    return AnomalyEvaluation(
        market_id=market_id,
        type=definition.type,
        observation_ts=observation_ts,
        evaluation_state=state,
        detector_version=definition.identity,
        normalization_version=config.identity,
        feature=definition.feature,
        feature_version=definition.feature_version,
        unit=definition.unit,
        severity=deviation.severity,
        confidence=deviation.confidence,
        baseline=deviation.baseline,
        current_value=deviation.current_value,
        deviation=deviation.value,
        direction=deviation.direction,
        reason=None
        if state is AnomalyEvaluationState.OK
        else (value.reason.value if value.reason is not None else "degraded"),
        baseline_ids=baseline_ids,
    )


def evaluate_detectors(
    *,
    market_id: uuid.UUID,
    vector: FeatureVector,
    projection: BaselineProjection,
    config: NormalizationConfig,
    detectors: Sequence[DetectorDefinition] = DEFAULT_DETECTORS,
) -> tuple[AnomalyEvaluation, ...]:
    """Every detector once, in roster order — one verdict per ``(market, type)``."""
    return tuple(
        evaluate_detector(
            definition,
            market_id=market_id,
            vector=vector,
            projection=projection,
            config=config,
        )
        for definition in detectors
    )


__all__ = ["AnomalyEvaluation", "evaluate_detector", "evaluate_detectors"]
