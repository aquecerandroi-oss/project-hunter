"""The components that are not read from a baseline: regime, anomalies, agents.

Split from ``components.py`` for the 350-line budget
(``infra/scripts/check_file_size.py``), along the seam the joint decision already
draws: the MAD path is one transformation shared by five components, and these
three (plus the registered-but-empty external intelligence) each **declare their
own transformation**, versioned by name:

- ``anomaly_stack_v1`` — the eligible severities, strongest first, each later one
  halved, saturated at 100: a second anomaly is still worth something, and a
  crowd of small ones cannot drown the strongest signal. It does **not** claim
  that a stack can never pass a single extreme reading (60 + 30 + 15 does beat a
  lone 90 — Astra, T2.4 diff review), only that each further anomaly buys half of
  what the one before it did;
- ``regime_compat_v1`` — a table over ``{trend, volatility} x direction``, read
  from the **pair** and not from the projected label, so a bull market that is
  merely violent is not mistaken for a directionless one;
- ``agent_consensus_v1`` — zero until M4. With weight zero it is a *known* zero
  and stays available; if a future profile ever gives it weight, the same code
  reports it unavailable instead of feeding a fabricated zero into a real weight.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, localcontext

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    MarketRegime,
    TradeDirection,
)
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.anomalies.lifecycle import AnomalyState
from hunter_indicators.opportunity.components import HUNDRED, ZERO, assemble_component
from hunter_indicators.opportunity.model import (
    COMPONENT_QUANTUM,
    REASON_ANOMALIES_UNKNOWN,
    REASON_NO_AGENTS,
    REASON_NOT_IMPLEMENTED,
    REASON_REGIME_CONFIDENCE,
    REASON_REGIME_STALE,
    REASON_REGIME_UNKNOWN,
    ComponentDefinition,
    ComponentScore,
    InputScore,
    clip,
    quantize,
)
from hunter_indicators.regime.decision import RegimeDecision
from hunter_indicators.regime.model import RegimeTrend, RegimeVolatility

REGIME_COMPATIBLE = Decimal("80")
REGIME_NEUTRAL = Decimal("50")
REGIME_OPPOSED = Decimal("20")
REGIME_HIGH_VOLATILITY_ADJUSTMENT = Decimal("-15")
"""Declared policy of ``regime_compat_v1``, not a calibration: a violent market is
a worse place to open *either* side, and the penalty is the same for both."""


def score_anomaly_component(
    definition: ComponentDefinition,
    *,
    weight: Decimal,
    anomalies: Sequence[AnomalyState] | None,
) -> ComponentScore:
    """``anomaly_stack_v1``: eligible severities, strongest first, each halved.

    ``anomalies=None`` means the set could not be loaded — unknown, and therefore
    unavailable. An **empty** set is knowledge: this market has no active anomaly,
    and zero is the honest reading of that, not a missing value.
    """
    if anomalies is None:
        return assemble_component(
            definition,
            weight=weight,
            inputs=(),
            raw=None,
            normalized=None,
            confidence=ZERO,
            direction=TradeDirection.NEUTRAL,
            used=0,
            expected=0,
            available=False,
            reason=REASON_ANOMALIES_UNKNOWN,
        )
    entries: list[InputScore] = []
    active = 0
    for state in anomalies:
        if state.status is not AnomalyStatus.ACTIVE:
            continue  # a resolved row is history, not evidence about now
        active += 1
        eligible = state.evaluation_state is AnomalyEvaluationState.OK
        entries.append(
            InputScore(
                feature=state.type.value,
                available=eligible,
                value=state.current_value,
                baseline=state.baseline,
                deviation=state.deviation,
                severity=state.severity if eligible else None,
                maturity=state.confidence,
                baseline_id=state.baseline_ids[0] if state.baseline_ids else None,
                reason=None if eligible else state.evaluation_state.value,
            )
        )
    # Sorted by strength, ties by type: the same set handed over in another order
    # (a query without ORDER BY, say) has to serialise to the same bytes (Astra,
    # T2.4 diff review, must-fix 3).
    scores = sorted(entries, key=lambda entry: (-(entry.severity or ZERO), entry.feature))
    usable = [entry for entry in scores if entry.available and entry.severity is not None]
    with localcontext(CONTEXT):
        raw = ZERO
        for index, entry in enumerate(usable):
            raw += (entry.severity or ZERO) / (Decimal(2) ** index)
        normalized = quantize(clip(raw, ZERO, HUNDRED), COMPONENT_QUANTUM)
        raw = quantize(raw, COMPONENT_QUANTUM)
        # "There are no active anomalies" is knowledge and scores a confident
        # zero; "there are anomalies we could not evaluate" is not, and it may
        # not borrow that certainty (Astra, must-fix 4). With every active
        # anomaly ineligible there is nothing to say at all.
        #
        # The eligible ones bring the detector's **own** confidence with them
        # (``anomalies.confidence``, the maturity of the baseline it read), so
        # the component is mean maturity times coverage — the same shape the MAD
        # components use, and the reason a severity-90 anomaly the detector is
        # 10% sure of no longer arrives here as certainty (cross review,
        # nice-to-have 1). A row that reports no confidence at all counts as zero
        # in the numerator, exactly as ``score_mad_component`` treats a maturity
        # it was not given: nothing here invents one.
        maturity = sum((entry.maturity or ZERO for entry in usable), ZERO)
        confidence = Decimal(1) if active == 0 else maturity / Decimal(active)
    available = active == 0 or bool(usable)
    return assemble_component(
        definition,
        weight=weight,
        inputs=scores,
        raw=raw if available else None,
        normalized=normalized if available else None,
        confidence=confidence,
        direction=TradeDirection.NEUTRAL,
        used=len(usable),
        expected=active,
        available=available,
        reason=None if available else REASON_ANOMALIES_UNKNOWN,
        detail={"eligible": len(usable), "active": active},
    )


def _compatibility(trend: RegimeTrend, direction: TradeDirection) -> Decimal:
    if direction is TradeDirection.NEUTRAL or trend is RegimeTrend.SIDEWAYS:
        return REGIME_NEUTRAL
    aligned = (trend is RegimeTrend.BULL and direction is TradeDirection.LONG) or (
        trend is RegimeTrend.BEAR and direction is TradeDirection.SHORT
    )
    return REGIME_COMPATIBLE if aligned else REGIME_OPPOSED


def score_regime_component(
    definition: ComponentDefinition,
    *,
    weight: Decimal,
    regime: RegimeDecision | None,
    direction: TradeDirection,
    stale: bool = False,
) -> ComponentScore:
    """``regime_compat_v1``: the published pair judged against the proposed side.

    The classifier's own ``confidence`` is what this component is confident of
    (cross review, nice-to-have 1): a regime confirmed by the breadth grades 1.00
    and one the breadth contradicts grades 0.60, instead of every regime arriving
    at the score as certainty. When the classifier reports **no** confidence — its
    published pair and the reading of this minute disagree, so the hysteresis is
    holding a pending candidate — the component is unavailable with its own
    reason. Declared consequence, and the reason it is a refusal and not a
    fabricated number: while a transition is pending the regime contributes
    nothing, so the score loses up to 8.00 points (weight 0.10 over a table whose
    maximum is 80) — the same way every other unreadable component behaves here.
    """
    if regime is None or regime.regime is MarketRegime.UNKNOWN:
        reason = REASON_REGIME_UNKNOWN
    elif stale:
        reason = REASON_REGIME_STALE
    elif regime.confidence is None:
        reason = REASON_REGIME_CONFIDENCE
    else:
        reason = None
    if reason is not None or regime is None:
        return assemble_component(
            definition,
            weight=weight,
            inputs=(),
            raw=None,
            normalized=None,
            confidence=ZERO,
            direction=TradeDirection.NEUTRAL,
            used=0,
            expected=1,
            available=False,
            reason=reason,
            detail={"direction_input": direction.value},
        )
    base = _compatibility(regime.trend, direction)
    adjustment = (
        REGIME_HIGH_VOLATILITY_ADJUSTMENT if regime.volatility is RegimeVolatility.HIGH else ZERO
    )
    confidence = regime.confidence
    if confidence is None:  # pragma: no cover - guarded by the branch above
        raise AssertionError("an available regime component always has a confidence")
    with localcontext(CONTEXT):
        normalized = quantize(clip(base + adjustment, ZERO, HUNDRED), COMPONENT_QUANTUM)
    return assemble_component(
        definition,
        weight=weight,
        inputs=(),
        raw=base,
        normalized=normalized,
        confidence=confidence,
        direction=TradeDirection.NEUTRAL,
        used=1,
        expected=1,
        available=True,
        detail={
            "regime": regime.regime.value,
            "regime_confidence": confidence,
            "trend": regime.trend.value,
            "volatility": regime.volatility.value,
            "direction_input": direction.value,
            "base": base,
            "adjustment": adjustment,
            "classifier_version": regime.classifier_version,
        },
    )


def score_consensus_component(
    definition: ComponentDefinition,
    *,
    weight: Decimal,
    agreeing_signals: int = 0,
) -> ComponentScore:
    """Zero until M4 — a *known* zero while the weight is zero, unavailable if not.

    ``reason`` is the field that says **why a component could not be read**, so
    the available branch leaves it empty and states the build gap in ``detail``
    instead: a reason next to an available component reads like a defect
    (cross review, nice-to-have 6).
    """
    weighted = weight > 0
    return assemble_component(
        definition,
        weight=weight,
        inputs=(),
        raw=ZERO if not weighted else None,
        normalized=quantize(ZERO, COMPONENT_QUANTUM) if not weighted else None,
        confidence=Decimal(1) if not weighted else ZERO,
        direction=TradeDirection.NEUTRAL,
        used=0,
        expected=0,
        available=not weighted,
        reason=REASON_NO_AGENTS if weighted else None,
        detail={"agreeing_signals": agreeing_signals, "status": REASON_NO_AGENTS},
    )


def score_external_component(definition: ComponentDefinition, *, weight: Decimal) -> ComponentScore:
    """Registered with weight zero (``PIPELINE.md`` §5), and nothing behind it."""
    return assemble_component(
        definition,
        weight=weight,
        inputs=(),
        raw=None,
        normalized=None,
        confidence=ZERO,
        direction=TradeDirection.NEUTRAL,
        used=0,
        expected=0,
        available=False,
        reason=REASON_NOT_IMPLEMENTED,
    )


__all__ = [
    "REGIME_COMPATIBLE",
    "REGIME_HIGH_VOLATILITY_ADJUSTMENT",
    "REGIME_NEUTRAL",
    "REGIME_OPPOSED",
    "score_anomaly_component",
    "score_consensus_component",
    "score_external_component",
    "score_regime_component",
]
