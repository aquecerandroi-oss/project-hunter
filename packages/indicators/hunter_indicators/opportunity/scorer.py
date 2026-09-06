"""The score itself: components, direction, confidence, envelope.

``score = clip(sum(w_i * c_i) + magnitude * e, 0, 100)`` — the arithmetic of the
joint M2 decision, with the weights read from the active ``opportunity_weights``
row and ``e`` the signed Early-Movement term of the **published** stage.

Order matters and is fixed, because one component consumes what the others
produce:

1. the MAD components are scored from the vector and the baselines;
2. the **direction** is the weighted vote of their directional inputs — the
   regime does not take part in the consensus that decides its own input (Astra,
   T2.4 design review, item 5);
3. the regime component is scored against that direction;
4. anomalies, agent consensus and external intelligence complete the roster;
5. the contributions are summed **already quantised**, so the stored decomposition
   adds up to the stored score exactly, and the explanation cannot disagree with
   the number it explains.

Two refusals worth stating:

- **an ineligible sample produces no score.** If no MAD component could be read —
  every feature degraded, or the baselines still warming up — there is no market
  evidence, and a score built from the regime and an empty anomaly set would be a
  number about nothing. The result carries ``eligible = False`` and the caller
  keeps the previous score with its own timestamp and a stale stamp
  (``docs/plans/M2.md``, decision 8);
- **a missing component never redistributes its weight.** It lowers the
  confidence and nothing else; the ceiling of the score drops with it, which is
  the honest consequence of not knowing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from uuid import UUID

from hunter_core.domain.enums import OpportunityStage, TradeDirection
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.anomalies.lifecycle import AnomalyState
from hunter_indicators.anomalies.severity import NormalizationConfig
from hunter_indicators.baselines.projection import BaselineProjection
from hunter_indicators.features.vector import FeatureVector
from hunter_indicators.opportunity.components import score_mad_component
from hunter_indicators.opportunity.model import (
    COMPONENT_PROFILE_VERSION,
    COMPONENT_QUANTUM,
    CONFIDENCE_QUANTUM,
    REASON_DIRECTIONAL_CANCELS,
    REASON_NO_DIRECTIONAL_EVIDENCE,
    REASON_NO_EVIDENCE,
    SCORE_QUANTUM,
    SCORER_VERSION,
    ComponentKind,
    ComponentScore,
    EarlyMovement,
    ScoreResult,
    clip,
    quantize,
)
from hunter_indicators.opportunity.overlays import (
    score_anomaly_component,
    score_consensus_component,
    score_external_component,
    score_regime_component,
)
from hunter_indicators.opportunity.profile import COMPONENTS
from hunter_indicators.opportunity.weights import WeightProfile
from hunter_indicators.regime.decision import RegimeDecision
from hunter_indicators.stage.model import StageDecision

ZERO = Decimal(0)
HUNDRED = Decimal(100)
REASON_NO_STAGE = "stage_unavailable"


@dataclass(frozen=True, slots=True)
class ScoreContext:
    """Everything the scorer reads. Resolved by the caller; pure from here on."""

    market_id: UUID
    vector: FeatureVector
    projection: BaselineProjection
    config: NormalizationConfig
    profile: WeightProfile
    stage: StageDecision | None = None
    regime: RegimeDecision | None = None
    regime_stale: bool = False
    anomalies: Sequence[AnomalyState] | None = None
    agreeing_signals: int = 0

    def __post_init__(self) -> None:
        """One cut, and nothing in the sample from after it.

        Every piece of evidence is resolved by the caller from a different place
        — the vector from the hot state, the stage and the regime from their own
        state machines, the anomalies from the database — and nothing but this
        check makes them describe the *same instant*. A replay that paired a
        vector from 10:00 with the anomaly set of 10:01 scored the older market
        with the newer news: it moved 48 to 52 in Astra's probe (T2.4 diff
        review, must-fix 1). Refusing is the only honest answer: silently
        dropping the future evidence would produce a score nobody asked for, and
        keeping it is look-ahead.
        """
        observation_ts = self.vector.ts
        if self.projection.cut.observation_ts != observation_ts:
            raise ValueError(
                f"the baselines were resolved for {self.projection.cut.observation_ts} and the "
                f"vector is of {observation_ts}: one score, one cut"
            )
        if self.stage is not None and self.stage.observation_ts > observation_ts:
            raise ValueError(
                f"the stage decision is of {self.stage.observation_ts}, after the cut "
                f"{observation_ts}"
            )
        if self.regime is not None and self.regime.observation_ts > observation_ts:
            raise ValueError(
                f"the regime decision is of {self.regime.observation_ts}, after the cut "
                f"{observation_ts}"
            )
        for state in self.anomalies or ():
            if state.observation_ts > observation_ts or state.detected_at > observation_ts:
                raise ValueError(
                    f"anomaly {state.type.value} was observed at {state.observation_ts} "
                    f"(detected {state.detected_at}), after the cut {observation_ts}"
                )

    @property
    def versions(self) -> dict[str, str]:
        """Every version a stored score has to name to be reproducible."""
        return {
            "scorer": SCORER_VERSION,
            "components": COMPONENT_PROFILE_VERSION,
            "weights": self.profile.version,
            "features": self.vector.feature_set_version,
            "quality_policy": self.vector.quality_policy_version,
            "normalization": self.config.identity,
            "stage": self.stage.thresholds_version if self.stage is not None else "",
            "regime": self.regime.classifier_version if self.regime is not None else "",
        }


def _early_movement(ctx: ScoreContext) -> EarlyMovement:
    """``e`` from the **published** stage, so the term inherits its hysteresis.

    The stage's own published direction travels next to it: an EARLY confirmed
    long two observations ago stays long while the opportunity's direction flips,
    and the explanation must not present that as "EARLY confirmed short" (Astra,
    T2.4 design review, item 6).
    """
    magnitude = ctx.profile.early_movement_magnitude
    stage = ctx.stage
    published = stage.state_out.stage if stage is not None else OpportunityStage.NONE
    direction = stage.published_direction if stage is not None else TradeDirection.NEUTRAL
    if published is OpportunityStage.EARLY:
        e = 1
    elif published is OpportunityStage.EXTENDED:
        e = -1
    else:
        e = 0
    if e not in ctx.profile.early_movement_values:
        raise ValueError(
            f"profile {ctx.profile.version} does not allow e={e}: "
            f"{ctx.profile.early_movement_values}"
        )
    with localcontext(CONTEXT):
        contribution = quantize(magnitude * Decimal(e), COMPONENT_QUANTUM)
    return EarlyMovement(
        e=e,
        magnitude=magnitude,
        contribution=contribution,
        stage=published.value,
        stage_direction=direction.value,
        reason=REASON_NO_STAGE if stage is None else None,
    )


def _direction(
    components: Sequence[ComponentScore],
) -> tuple[TradeDirection, Decimal | None, str | None]:
    """The weighted vote of the directional inputs, and how much they agree.

    Each input votes with the share of the score it actually carries
    (``weight_i * severity / expected_i``): a saturated momentum in a component
    weighted 0.20 speaks louder than a mild book imbalance weighted 0.15, which is
    the same arithmetic that produced the score.

    Two different silences, and they return different things (cross review,
    must-fix 1):

    - **nobody voted** — every directional reading sits on its own median, or none
      was available at all. There is no agreement to measure, so the agreement is
      ``None`` and the confidence keeps its coverage untouched. Reporting ``0``
      halved the confidence of a market whose readings were all fine, and moving
      one reading off its median doubled it back with nothing having improved;
    - **the votes cancelled exactly** — real evidence, read contradictorily. That
      *is* an agreement of zero, it carries its own reason, and the declared floor
      of 0.5 applies to it.
    """
    signed = ZERO
    magnitude = ZERO
    with localcontext(CONTEXT):
        for component in components:
            if component.kind is not ComponentKind.MAD or component.expected == 0:
                continue
            for entry in component.inputs:
                if not entry.available or entry.direction is TradeDirection.NEUTRAL:
                    continue
                share = component.weight * (entry.severity or ZERO) / Decimal(component.expected)
                signed += share if entry.direction is TradeDirection.LONG else -share
                magnitude += share
        if magnitude == 0:
            return TradeDirection.NEUTRAL, None, REASON_NO_DIRECTIONAL_EVIDENCE
        agreement = quantize(abs(signed) / magnitude, CONFIDENCE_QUANTUM)
    if signed > 0:
        return TradeDirection.LONG, agreement, None
    if signed < 0:
        return TradeDirection.SHORT, agreement, None
    return TradeDirection.NEUTRAL, agreement, REASON_DIRECTIONAL_CANCELS


def _confidence(components: Sequence[ComponentScore], agreement: Decimal | None) -> Decimal:
    """Weighted maturity of what was read, tempered by how much it agrees.

    ``coverage * (1 + agreement) / 2``: full disagreement halves the confidence
    rather than zeroing it — the evidence is real, the reading of it is
    contradictory. A declared assumption of ``opportunity_v1``, not a calibration
    (Astra, T2.4 design review, item 5).

    ``agreement is None`` means no directional evidence was cast at all, and the
    factor is **one**: the term grades a contradiction, and there is nothing to
    contradict. Applying the floor there punished a market for its momentum
    sitting on its own median (cross review, must-fix 1).

    Zero-weight components are excluded from both terms: they move no score, so
    they may neither raise nor lower the confidence in it.
    """
    weighted = [component for component in components if component.counts_for_confidence]
    with localcontext(CONTEXT):
        total = sum((component.weight for component in weighted), ZERO)
        if total == 0:
            return quantize(ZERO, CONFIDENCE_QUANTUM)
        covered = sum((component.weight * component.confidence for component in weighted), ZERO)
        factor = Decimal(1) if agreement is None else (Decimal(1) + agreement) / Decimal(2)
        return quantize(covered / total * factor, CONFIDENCE_QUANTUM)


def score_opportunity(ctx: ScoreContext) -> ScoreResult:
    """The score of one market at one cut, with its whole decomposition."""
    mad: list[ComponentScore] = []
    for definition in COMPONENTS:
        if definition.kind is not ComponentKind.MAD:
            continue
        mad.append(
            score_mad_component(
                definition,
                weight=ctx.profile.weight_of(definition.name),
                market_id=ctx.market_id,
                vector=ctx.vector,
                projection=ctx.projection,
                config=ctx.config,
            )
        )
    direction, agreement, direction_reason = _direction(mad)
    others: list[ComponentScore] = []
    for definition in COMPONENTS:
        weight = ctx.profile.weight_of(definition.name)
        if definition.kind is ComponentKind.REGIME:
            others.append(
                score_regime_component(
                    definition,
                    weight=weight,
                    regime=ctx.regime,
                    direction=direction,
                    stale=ctx.regime_stale,
                )
            )
        elif definition.kind is ComponentKind.ANOMALIES:
            others.append(
                score_anomaly_component(definition, weight=weight, anomalies=ctx.anomalies)
            )
        elif definition.kind is ComponentKind.CONSENSUS:
            others.append(
                score_consensus_component(
                    definition, weight=weight, agreeing_signals=ctx.agreeing_signals
                )
            )
        elif definition.kind is ComponentKind.EXTERNAL:
            others.append(score_external_component(definition, weight=weight))
    components = tuple(sorted([*mad, *others], key=lambda item: item.name))
    early = _early_movement(ctx)
    eligible = any(component.available for component in mad)
    confidence = _confidence(components, agreement)
    with localcontext(CONTEXT):
        total = sum((component.contribution for component in components), ZERO)
        score = quantize(clip(total + early.contribution, ZERO, HUNDRED), SCORE_QUANTUM)
    baseline_ids = tuple(
        sorted(
            {
                entry.baseline_id
                for component in components
                for entry in component.inputs
                if entry.baseline_id is not None
            }
        )
    )
    return ScoreResult(
        score=score if eligible else None,
        confidence=confidence if eligible else quantize(ZERO, CONFIDENCE_QUANTUM),
        direction=direction if eligible else TradeDirection.NEUTRAL,
        agreement=agreement,
        components=components,
        early_movement=early,
        observation_ts=ctx.vector.ts,
        weights_version=ctx.profile.version,
        versions=ctx.versions,
        eligible=eligible,
        reason=None if eligible else REASON_NO_EVIDENCE,
        direction_reason=direction_reason,
        baseline_ids=baseline_ids,
    )


__all__ = ["REASON_NO_STAGE", "ScoreContext", "score_opportunity"]
