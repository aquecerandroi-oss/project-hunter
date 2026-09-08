"""The score of ``regime_hourly_v1``, decomposed line by line, and the snapshot.

:mod:`hunter_indicators.regime.hourly` measures; this module weighs. The split
is the one the house rule asks for anyway: the statistics are arithmetic over a
series, the score is a **policy** over statistics, and a policy is the thing a
new version replaces.

The five components, each in the direction "higher is a healthier tape":

===========  =======================================  ==========================
component    raw                                      normalized (0-100)
===========  =======================================  ==========================
trend        the slope of the fast average            100 up / 50 flat / 0 down
breadth      % of usable markets advancing            itself
volatility   percentile of today's realised vol       100 - percentile
drawdown     % below the 30-day high                  100 - dd x (100/dd_zero)
funding      average 8 h funding of the universe      50 centred, saturating
===========  =======================================  ==========================

A component with no usable input is ``None``, its weight is redistributed over
the ones that answered, and ``confidence`` publishes how much weight that was.
Never a zero standing in for a missing reading: a funding feed that went away
must not read as neutral sentiment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.regime.hourly import (
    TrendVerdict,
    VolVerdict,
    classify_trend,
    classify_volatility,
    contiguous_closes,
    drawdown_from_high,
    sma,
)
from hunter_indicators.regime.hourly_model import (
    CONFIDENCE_QUANTUM,
    FUNDING_QUANTUM,
    REASON_BREADTH_COVERAGE,
    REASON_DRAWDOWN_WARMUP,
    REASON_FUNDING_UNAVAILABLE,
    REASON_SCORE_UNAVAILABLE,
    SCORE_QUANTUM,
    HourlyThresholds,
    HourlyTrend,
)
from hunter_indicators.regime.hourly_snapshot import (
    BreadthCount,
    FundingAverage,
    RegimeSnapshot,
    ScoreComponent,
    SnapshotInputs,
)

HUNDRED = Decimal(100)


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return min(max(value, low), high)


_TREND_SCORE = {
    HourlyTrend.UP: HUNDRED,
    HourlyTrend.FLAT: Decimal(50),
    HourlyTrend.DOWN: Decimal(0),
}
"""The trend on 0-100. Three points and not a continuum: the classification is
the decision, and interpolating between ``up`` and ``flat`` would invent a
precision the three-rule verdict does not have."""


def _component(
    name: str, raw: Decimal | None, normalized: Decimal | None, weight: Decimal, reason: str | None
) -> ScoreComponent:
    contribution = None
    if normalized is not None:
        with localcontext(CONTEXT):
            contribution = (weight * normalized).quantize(SCORE_QUANTUM)
    return ScoreComponent(
        name=name,
        raw=raw,
        normalized=normalized,
        weight=weight,
        contribution=contribution,
        reason=reason,
    )


def breadth_pct_of(breadth: BreadthCount, thresholds: HourlyThresholds) -> Decimal | None:
    """Advancing over **usable**, once enough of the universe could be read."""
    if breadth.usable == 0 or breadth.universe == 0:
        return None
    with localcontext(CONTEXT):
        coverage = Decimal(breadth.usable) / Decimal(breadth.universe)
        if coverage < thresholds.breadth_min_coverage:
            return None
        return ((Decimal(breadth.advancing) / Decimal(breadth.usable)) * HUNDRED).quantize(
            SCORE_QUANTUM
        )


def _funding_normalized(value: Decimal, thresholds: HourlyThresholds) -> Decimal:
    """50 at neutral funding, 0 at ``+funding_scale``, 100 at ``-funding_scale``.

    Positive funding is longs paying shorts — crowded, and therefore a *lower*
    score, which is the direction every other component already points in.
    """
    with localcontext(CONTEXT):
        ratio = _clamp(value / thresholds.funding_scale, Decimal(-1), Decimal(1))
        return (Decimal(50) - ratio * Decimal(50)).quantize(SCORE_QUANTUM)


def build_components(
    *,
    trend: TrendVerdict,
    vol: VolVerdict,
    breadth_pct: Decimal | None,
    funding: FundingAverage,
    drawdown_pct: Decimal | None,
    thresholds: HourlyThresholds,
) -> tuple[ScoreComponent, ...]:
    """The five lines of the decomposition, available or not, in a fixed order."""
    weights = thresholds.weights
    dd_normalized = None
    if drawdown_pct is not None:
        with localcontext(CONTEXT):
            scale = HUNDRED / thresholds.drawdown_zero_pct
            dd_normalized = max(Decimal(0), HUNDRED - drawdown_pct * scale).quantize(SCORE_QUANTUM)
    return (
        _component(
            "trend",
            trend.slope,
            _TREND_SCORE.get(trend.trend),
            weights.trend,
            trend.reason if trend.trend is HourlyTrend.UNKNOWN else None,
        ),
        _component(
            "breadth",
            breadth_pct,
            breadth_pct,
            weights.breadth,
            None if breadth_pct is not None else REASON_BREADTH_COVERAGE,
        ),
        _component(
            "volatility",
            vol.percentile,
            None if vol.percentile is None else HUNDRED - vol.percentile,
            weights.volatility,
            vol.reason,
        ),
        _component(
            "drawdown",
            drawdown_pct,
            dd_normalized,
            weights.drawdown,
            None if drawdown_pct is not None else REASON_DRAWDOWN_WARMUP,
        ),
        _component(
            "funding",
            funding.value,
            None if funding.value is None else _funding_normalized(funding.value, thresholds),
            weights.funding,
            None if funding.value is not None else REASON_FUNDING_UNAVAILABLE,
        ),
    )


def score_of(
    components: Sequence[ScoreComponent], thresholds: HourlyThresholds
) -> tuple[Decimal | None, Decimal]:
    """``(score, confidence)`` — the weighted mean of what was available.

    The weight of a missing component is **redistributed**, never treated as a
    zero: a funding feed that went away must not read as neutral-negative
    sentiment. How much weight was missing is exactly what ``confidence``
    publishes, and below ``min_weight_for_score`` there is no number at all.
    """
    available = [component for component in components if component.available]
    with localcontext(CONTEXT):
        total = sum((component.weight for component in components), Decimal(0))
        have = sum((component.weight for component in available), Decimal(0))
        confidence = (have / total).quantize(CONFIDENCE_QUANTUM) if total > 0 else Decimal(0)
        if total <= 0 or have < thresholds.min_weight_for_score * total:
            return None, confidence
        weighted = sum(
            (component.weight * (component.normalized or Decimal(0)) for component in available),
            Decimal(0),
        )
        return (weighted / have).quantize(SCORE_QUANTUM), confidence


def build_snapshot(
    *,
    ts: datetime,
    closes: Mapping[datetime, Decimal],
    breadth: BreadthCount,
    funding: FundingAverage,
    thresholds: HourlyThresholds,
) -> RegimeSnapshot:
    """One hour of context from the reference market's closes and the universe."""
    depth = max(
        thresholds.sma_slow_hours + thresholds.slope_lookback_hours,
        thresholds.vol_reference_hours + thresholds.vol_window_hours + 1,
        thresholds.drawdown_window_hours,
    )
    series = contiguous_closes(closes, ts=ts, limit=depth)
    trend = classify_trend(series, thresholds)
    vol = classify_volatility(series, thresholds)
    breadth_pct = breadth_pct_of(breadth, thresholds)
    drawdown_pct, high = drawdown_from_high(series, thresholds)
    funding_value = None if funding.value is None else funding.value.quantize(FUNDING_QUANTUM)
    resolved = FundingAverage(value=funding_value, markets=funding.markets)
    components = build_components(
        trend=trend,
        vol=vol,
        breadth_pct=breadth_pct,
        funding=resolved,
        drawdown_pct=drawdown_pct,
        thresholds=thresholds,
    )
    score, confidence = score_of(components, thresholds)
    reasons = [component.reason for component in components if component.reason is not None]
    if score is None:
        reasons.append(REASON_SCORE_UNAVAILABLE)
    return RegimeSnapshot(
        ts=ts,
        trend=trend.trend,
        vol_regime=vol.vol_regime,
        breadth_pct=breadth_pct,
        funding_avg=resolved.value,
        drawdown_pct=drawdown_pct,
        score_0_100=score,
        confidence=confidence,
        components=components,
        inputs=SnapshotInputs(
            closes=len(series),
            last_close=series[-1] if series else None,
            sma_fast=trend.sma_fast,
            sma_slow=trend.sma_slow,
            slope=trend.slope,
            vol_current=vol.current,
            vol_percentile=vol.percentile,
            vol_samples=vol.samples,
            high_30d=high,
            breadth=breadth,
            funding_markets=resolved.markets,
        ),
        reasons=tuple(reasons),
        version=thresholds.identity,
    )


def count_breadth[Key](
    closes_by_market: Mapping[Key, Mapping[datetime, Decimal]],
    *,
    ts: datetime,
    universe: int,
    thresholds: HourlyThresholds,
) -> BreadthCount:
    """How many markets are above their 24-hour average **and** up over 24 hours.

    Generic in the key because the breadth does not care how a caller addresses
    its markets — ``markets.id`` in the job, a symbol in a test — and ``Mapping``
    is invariant in its key type, so ``Mapping[object, ...]`` would refuse the
    ``dict[UUID, ...]`` the job actually holds.

    Both conditions, because either one alone is noise: a market can sit above a
    falling average, and a market can be up over a day while rolling over. A
    market needs the 25 contiguous hourly closes the pair of tests reads, or it is
    not counted at all — ``usable`` is the denominator, ``universe`` only decides
    whether the reading may be quoted (:func:`breadth_pct_of`).
    """
    window = thresholds.vol_window_hours + 1
    usable = 0
    advancing = 0
    for closes in closes_by_market.values():
        series = contiguous_closes(closes, ts=ts, limit=window)
        if len(series) < window:
            continue
        usable += 1
        average = sma(series, thresholds.vol_window_hours)
        if average is None:  # pragma: no cover - the length was just checked
            continue
        if series[-1] > average and series[-1] > series[0]:
            advancing += 1
    return BreadthCount(universe=universe, usable=usable, advancing=advancing)


__all__ = [
    "breadth_pct_of",
    "build_components",
    "build_snapshot",
    "count_breadth",
    "score_of",
]
