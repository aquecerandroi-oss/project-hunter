"""One market, one cut: features -> anomalies -> stage -> score -> status.

This is the single owner Astra asked for in the T2.5 design review. Running the
five engines as independent stream consumers would have been closer to
``PIPELINE.md`` section 3's letter ("trigger: ``features.updated``") and wrong in
substance: each stage would read a state some other task had already moved past,
and ``ScoreContext.__post_init__`` refuses exactly that -- one score, one cut.
``features.updated`` is still published, for consumers outside this process; it
is a *notification*, not this pipeline's transport.

Everything below is a pure function of what the caller resolved. This module
performs no IO, holds no clock of its own (``ctx.as_of`` is the only "now") and
writes nothing: it returns an :class:`Evaluation` the persist cycle turns into
rows and events. That is what makes "recompute this stored score from its
envelope" a guarantee rather than a hope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus, OpportunityStatus
from hunter_core.logging import get_logger
from hunter_indicators.anomalies import (
    DEFAULT_DETECTORS,
    AnomalyAction,
    AnomalyState,
    AnomalyTransition,
    advance_all,
    evaluate_detectors,
)
from hunter_indicators.features import (
    EMPTY_STATE,
    FeatureState,
    FeatureVector,
    compute_features,
)
from hunter_indicators.opportunity import (
    EpisodeState,
    HistoryMark,
    HistoryVerdict,
    ScoreContext,
    ScoreResult,
    StatusDecision,
    StatusSample,
    advance_status,
    explain,
    opportunity_envelope,
    quality_signature,
    score_opportunity,
    should_record_history,
)
from hunter_indicators.stage import (
    EMPTY_STAGE_STATE,
    StageDecision,
    StageInputs,
    StageState,
    classify_stage,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_indicators.anomalies import DetectorDefinition, NormalizationConfig
    from hunter_indicators.baselines import BaselineProjection
    from hunter_indicators.features import FeatureResult, MarketContext
    from hunter_indicators.opportunity import StatusThresholds, WeightProfile
    from hunter_indicators.regime import RegimeDecision
    from hunter_indicators.stage import StageThresholds

logger = get_logger(__name__)

__all__ = ["Evaluation", "EvaluationInputs", "evaluate_market", "next_anomaly_states"]


@dataclass(frozen=True, slots=True)
class EvaluationInputs:
    """The versioned policy and the resolved evidence of one evaluation."""

    market_id: UUID
    context: MarketContext
    projection: BaselineProjection
    profile: WeightProfile
    config: NormalizationConfig
    stage_thresholds: StageThresholds
    status_thresholds: StatusThresholds
    stage_inputs: StageInputs = StageInputs()
    stage_state: StageState | None = None
    feature_state: FeatureState = EMPTY_STATE
    anomaly_states: Sequence[AnomalyState] = ()
    detectors: Sequence[DetectorDefinition] = DEFAULT_DETECTORS
    episode: EpisodeState | None = None
    regime: RegimeDecision | None = None
    regime_stale: bool = False
    regime_id: UUID | None = None
    last_history: HistoryMark | None = None
    score_due: bool = True
    """A vector is produced on every tick that passes the 1 s throttle; the score
    has its own 2 s throttle, and skipping it must not skip the features."""


@dataclass(frozen=True, slots=True)
class Evaluation:
    """What one observation of one market concluded."""

    market_id: UUID
    vector: FeatureVector
    features: FeatureResult
    transitions: tuple[AnomalyTransition, ...] = ()
    stage: StageDecision | None = None
    score: ScoreResult | None = None
    status: StatusDecision | None = None
    explanation: dict[str, Any] = field(default_factory=dict[str, Any])
    envelope: dict[str, Any] = field(default_factory=dict[str, Any])
    history: HistoryVerdict | None = None
    history_mark: HistoryMark | None = None
    anomaly_states: tuple[AnomalyState, ...] = ()

    @property
    def observation_ts(self) -> datetime:
        return self.vector.ts

    @property
    def baseline_ids(self) -> tuple[UUID, ...]:
        ids: set[UUID] = set(self.score.baseline_ids if self.score is not None else ())
        for state in self.anomaly_states:
            ids.update(state.baseline_ids)
        return tuple(sorted(ids))


def _regime_label(decision: RegimeDecision | None) -> str:
    """The published **pair**, which is what the history rule compares.

    Spelling the projected label instead would hide ``bull+high -> bear+high``
    from every directional consumer (notes-T2.4 section 8g).
    """
    if decision is None:
        return ""
    trend, volatility = decision.state_out.pair
    return f"{trend.value}/{volatility.value}"


def _strongest_eligible(states: Sequence[AnomalyState]) -> Decimal | None:
    severities = [
        state.severity
        for state in states
        if state.status is AnomalyStatus.ACTIVE
        and state.evaluation_state is AnomalyEvaluationState.OK
    ]
    return max(severities) if severities else None


def next_anomaly_states(
    previous: Sequence[AnomalyState], transitions: Sequence[AnomalyTransition]
) -> tuple[AnomalyState, ...]:
    by_type = {state.type: state for state in previous}
    for transition in transitions:
        if transition.state is not None:
            by_type[transition.state.type] = transition.state
    return tuple(by_type[key] for key in sorted(by_type, key=lambda item: item.value))


def evaluate_market(inputs: EvaluationInputs) -> Evaluation:
    """Advance one market by one observation. Pure; no IO, no clock."""
    result: FeatureResult = compute_features(inputs.context, inputs.feature_state)
    vector = result.vector

    evaluations = evaluate_detectors(
        market_id=inputs.market_id,
        vector=vector,
        projection=inputs.projection,
        config=inputs.config,
        detectors=inputs.detectors,
    )
    transitions = advance_all(inputs.anomaly_states, evaluations, inputs.detectors)
    anomaly_states = next_anomaly_states(inputs.anomaly_states, transitions)

    stage = classify_stage(
        vector,
        thresholds=inputs.stage_thresholds,
        state=inputs.stage_state or EMPTY_STAGE_STATE,
        inputs=inputs.stage_inputs,
        observation_ts=vector.ts,
    )

    if not inputs.score_due:
        return Evaluation(
            market_id=inputs.market_id,
            vector=vector,
            features=result,
            transitions=transitions,
            stage=stage,
            anomaly_states=anomaly_states,
        )

    ctx = ScoreContext(
        market_id=inputs.market_id,
        vector=vector,
        projection=inputs.projection,
        config=inputs.config,
        profile=inputs.profile,
        stage=stage,
        regime=inputs.regime,
        regime_stale=inputs.regime_stale,
        anomalies=anomaly_states,
    )
    score = score_opportunity(ctx)
    sample = StatusSample(
        observation_ts=vector.ts,
        score=score.score,
        eligible=score.eligible,
        stage=stage.stage,
        direction=score.direction,
        confidence=score.confidence,
        anomaly_severity=_strongest_eligible(anomaly_states),
    )
    status = advance_status(inputs.episode, sample, inputs.status_thresholds)
    explanation = explain(score, status=status.status)
    envelope = opportunity_envelope(score, ctx, regime_id=inputs.regime_id, status=status.as_wire())
    mark = HistoryMark(
        ts=vector.ts,
        score=score.score,
        status=status.status,
        stage=stage.stage,
        direction=score.direction,
        stage_direction=stage.published_direction,
        regime=_regime_label(inputs.regime),
        quality=quality_signature(score.components),
        eligible=score.eligible,
        versions=score.versions,
    )
    history = should_record_history(inputs.last_history, mark)
    return Evaluation(
        market_id=inputs.market_id,
        vector=vector,
        features=result,
        transitions=transitions,
        stage=stage,
        score=score,
        status=status,
        explanation=explanation,
        envelope=envelope,
        history=history,
        history_mark=mark,
        anomaly_states=anomaly_states,
    )


def opened_or_closed(transitions: Sequence[AnomalyTransition]) -> tuple[int, int]:
    """``(opened, closed)`` in one evaluation -- the two numbers the proof reports."""
    opened = sum(1 for item in transitions if item.action is AnomalyAction.OPEN)
    closed = sum(
        1 for item in transitions if item.action in (AnomalyAction.RESOLVE, AnomalyAction.EXPIRE)
    )
    return (opened, closed)


def status_of(evaluation: Evaluation) -> OpportunityStatus | None:
    return None if evaluation.status is None else evaluation.status.status
