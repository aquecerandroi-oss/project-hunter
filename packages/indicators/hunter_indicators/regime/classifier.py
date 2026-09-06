"""The verdict: one reading, the hysteresis over it, and the stamp for display.

Three rules, each with its reason:

- **the warm-up is a classification, not a gap.** Until thirty days of persisted
  1-minute candles support the volatility reference, the regime is
  ``MarketRegime.UNKNOWN`` with the reason in ``supporting_features``
  (``hunter_core.domain.enums``: "``UNKNOWN`` is the classifier's warm-up state").
  The trend it *could* compute survives as evidence and is deliberately not
  published as a regime: half a classification is not a classification;
- **three readings to change, none to stop claiming.** ``docs/PIPELINE.md`` §4
  asks for three consecutive readings before a transition; losing the ability to
  classify publishes ``UNKNOWN`` immediately, the same doctrine the stage
  classifier follows — the hysteresis protects against flapping, not against
  blindness;
- **the hysteresis follows the pair ``{trend, volatility}``**, not the projected
  label. ``bull+high`` and ``bear+high`` both project onto ``HIGH_VOLATILITY``,
  and letting the trend flip underneath an unchanged label would move every
  direction-sensitive consumer with no confirmation at all (Astra, T2.4 design
  review, 9e).

``confidence`` is the breadth confirmation and nothing else: the reading either
had every input it needs (or it would be ``UNKNOWN``), so what is left to grade
is whether the rest of the market agrees. The three values are declared policy in
:class:`RegimeThresholds`, not calibration.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.domain.enums import MarketRegime
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.vector import seconds_between
from hunter_indicators.regime.breadth import trend_of
from hunter_indicators.regime.decision import (
    RegimeDecision,
    RegimeDisplay,
    RegimeReading,
    RegimeState,
)
from hunter_indicators.regime.model import (
    CONFIDENCE_QUANTUM,
    EMPTY_BREADTH,
    RATIO_QUANTUM,
    REASON_NO_VOLATILITY,
    REASON_STALE_OBSERVATION,
    Breadth,
    RegimeObservation,
    RegimeThresholds,
    RegimeTrend,
    RegimeVolatility,
    VolatilityReference,
)


def _volatility_of(
    volatility: Decimal | None,
    reference: VolatilityReference | None,
    thresholds: RegimeThresholds,
) -> tuple[RegimeVolatility, str | None, Decimal | None]:
    """The volatility dimension as a ratio against the 30-day median."""
    if volatility is None:
        return RegimeVolatility.UNKNOWN, REASON_NO_VOLATILITY, None
    if reference is None or not reference.usable or reference.median is None:
        reason = None if reference is None else reference.reason
        return RegimeVolatility.UNKNOWN, reason, None
    with localcontext(CONTEXT):
        ratio = (volatility / reference.median).quantize(RATIO_QUANTUM)
    if ratio >= thresholds.volatility_high_multiple:
        return RegimeVolatility.HIGH, None, ratio
    if ratio <= thresholds.volatility_low_multiple:
        return RegimeVolatility.LOW, None, ratio
    return RegimeVolatility.NORMAL, None, ratio


def evaluate_regime(
    *,
    observation: RegimeObservation,
    reference: VolatilityReference | None,
    breadth: Breadth = EMPTY_BREADTH,
    thresholds: RegimeThresholds,
) -> RegimeReading:
    """One reading of the reference market — before any hysteresis."""
    trend, trend_reason, r_4h, r_1d = trend_of(
        return_4h=observation.return_4h,
        return_1d=observation.return_1d,
        atr_pct=observation.atr_pct,
        thresholds=thresholds,
    )
    volatility, volatility_reason, ratio = _volatility_of(
        observation.volatility, reference, thresholds
    )
    values: dict[str, Decimal | None] = {
        "return_4h": observation.return_4h,
        "return_1d": observation.return_1d,
        "atr_14_pct": observation.atr_pct,
        "r_4h": r_4h,
        "r_1d": r_1d,
        "volatility": observation.volatility,
        "volatility_median_30d": None if reference is None else reference.median,
        "volatility_ratio": ratio,
        "breadth": breadth.fraction,
    }
    return RegimeReading(
        observation_ts=observation.observation_ts,
        trend=trend,
        volatility=volatility,
        reason=trend_reason or volatility_reason,
        values=values,
        breadth=breadth,
        volatility_reference=reference,
    )


def _confidence(reading: RegimeReading, thresholds: RegimeThresholds) -> Decimal | None:
    """How much the rest of the market confirms the reading. ``None`` if unknown."""
    if not reading.known:
        return None
    breadth = reading.breadth
    if not breadth.usable or breadth.fraction is None:
        with localcontext(CONTEXT):
            return thresholds.confidence_without_breadth.quantize(CONFIDENCE_QUANTUM)
    # The threshold belongs to the **upside**: at exactly
    # ``breadth_agreement_min`` the bull is confirmed and the bear is not. With
    # ``>=`` on one side and ``<=`` on the other, a tie confirmed whichever trend
    # it was asked about — and a number that confirms both sides confirms nothing
    # (cross review, nice-to-have 4). The asymmetry is declared, not calibrated:
    # ``breadth_agreement_min`` reads as "this much of the universe advancing is
    # a broad advance", so reaching it is the advance and the decline has to be
    # strictly under it.
    agrees = (
        reading.trend is RegimeTrend.SIDEWAYS
        or (
            reading.trend is RegimeTrend.BULL
            and breadth.fraction >= thresholds.breadth_agreement_min
        )
        or (
            reading.trend is RegimeTrend.BEAR
            and breadth.fraction < thresholds.breadth_agreement_min
        )
    )
    value = thresholds.confidence_full if agrees else thresholds.confidence_breadth_disagrees
    with localcontext(CONTEXT):
        return value.quantize(CONFIDENCE_QUANTUM)


def _decide(
    state_in: RegimeState,
    state_out: RegimeState,
    reading: RegimeReading,
    thresholds: RegimeThresholds,
    *,
    changed: bool,
    reason: str | None = None,
) -> RegimeDecision:
    return RegimeDecision(
        regime=state_out.regime,
        trend=state_out.trend,
        volatility=state_out.volatility,
        observation_ts=reading.observation_ts,
        state_in=state_in,
        state_out=state_out,
        classifier_version=thresholds.identity,
        confidence=_confidence(reading, thresholds) if state_out.pair == reading.pair else None,
        changed=changed,
        reason=reason if reason is not None else reading.reason,
        reading=reading,
        thresholds=thresholds,
    )


def advance_regime(
    state: RegimeState,
    reading: RegimeReading,
    thresholds: RegimeThresholds,
) -> RegimeDecision:
    """``state`` plus one reading: what is published now, and what is pending."""
    if (
        state.last_observation_ts is not None
        and reading.observation_ts <= state.last_observation_ts
    ):
        return _decide(
            state, state, reading, thresholds, changed=False, reason=REASON_STALE_OBSERVATION
        )

    if not reading.known:
        changed = state.pair != (RegimeTrend.UNKNOWN, RegimeVolatility.UNKNOWN)
        state_out = RegimeState(
            trend=RegimeTrend.UNKNOWN,
            volatility=RegimeVolatility.UNKNOWN,
            candidate_trend=RegimeTrend.UNKNOWN,
            candidate_volatility=RegimeVolatility.UNKNOWN,
            confirmations=0,
            last_observation_ts=reading.observation_ts,
            published_at=reading.observation_ts if changed else state.published_at,
        )
        return _decide(state, state_out, reading, thresholds, changed=changed)

    if reading.pair == state.pair:
        state_out = RegimeState(
            trend=state.trend,
            volatility=state.volatility,
            candidate_trend=state.trend,
            candidate_volatility=state.volatility,
            confirmations=0,
            last_observation_ts=reading.observation_ts,
            published_at=state.published_at,
        )
        return _decide(state, state_out, reading, thresholds, changed=False)

    same_candidate = reading.pair == (state.candidate_trend, state.candidate_volatility)
    confirmations = state.confirmations + 1 if same_candidate else 1
    if confirmations >= thresholds.confirmations:
        state_out = RegimeState(
            trend=reading.trend,
            volatility=reading.volatility,
            candidate_trend=reading.trend,
            candidate_volatility=reading.volatility,
            confirmations=0,
            last_observation_ts=reading.observation_ts,
            published_at=reading.observation_ts,
        )
        return _decide(state, state_out, reading, thresholds, changed=True)
    state_out = RegimeState(
        trend=state.trend,
        volatility=state.volatility,
        candidate_trend=reading.trend,
        candidate_volatility=reading.volatility,
        confirmations=confirmations,
        last_observation_ts=reading.observation_ts,
        published_at=state.published_at,
    )
    return _decide(state, state_out, reading, thresholds, changed=False)


def classify_regime(
    *,
    state: RegimeState,
    observation: RegimeObservation,
    reference: VolatilityReference | None,
    breadth: Breadth = EMPTY_BREADTH,
    thresholds: RegimeThresholds,
) -> RegimeDecision:
    """The public door: evaluate the reading, then advance the hysteresis."""
    reading = evaluate_regime(
        observation=observation,
        reference=reference,
        breadth=breadth,
        thresholds=thresholds,
    )
    return advance_regime(state, reading, thresholds)


def regime_for_display(
    state: RegimeState,
    *,
    as_of: datetime,
    thresholds: RegimeThresholds,
) -> RegimeDisplay:
    """The last regime for a screen, stamped ``stale`` when it stopped being fresh.

    Display only: a stale regime is shown, never fed to a score. The scorer reads
    the decision of the current evaluation, which is why this returns no
    confidence — a number that old is not evidence.
    """
    as_of = ensure_utc(as_of)
    last = state.last_observation_ts
    if last is None:
        return RegimeDisplay(
            regime=MarketRegime.UNKNOWN, observation_ts=None, age_s=None, stale=True
        )
    age = seconds_between(last, as_of)
    return RegimeDisplay(
        regime=state.regime,
        observation_ts=last,
        age_s=age,
        stale=age > Decimal(int(thresholds.display_max_age.total_seconds())),
    )


__all__ = [
    "advance_regime",
    "classify_regime",
    "evaluate_regime",
    "regime_for_display",
]
