"""``hunter_indicators.regime`` — the v0 market regime of ``docs/PIPELINE.md`` §4.

Pure functions over what the caller already holds: the BTC feature vector, the
persisted 1-minute candles and the per-market readings that make the breadth.
Nothing here calls an exchange, reads a clock or touches the database — the
scanner (T2.5) resolves the inputs and persists the decision.

Four modules for ``regime_v0``: ``model.py`` (thresholds, readings, state,
decision), ``series.py`` (the internal statistics the feature set does not
publish), ``breadth.py`` (the confirmation and its composition) and
``classifier.py`` (the verdict, its hysteresis and the stale stamp for display).

Four more for ``regime_hourly_v1`` (T3.43), the *hourly* engine that answers a
different question — what the market was like during one hour, for every hour,
so a cohort can be cut by context: ``hourly_model.py`` (vocabulary and
thresholds), ``hourly_snapshot.py`` (the shapes), ``hourly.py`` (the statistics)
and ``hourly_score.py`` (the weighted decomposition). It writes its own
``classifier_version`` into the same table; it does not touch ``regime_v0``.
"""

from hunter_indicators.regime.breadth import classify_market_trend, compute_breadth, trend_of
from hunter_indicators.regime.classifier import (
    advance_regime,
    classify_regime,
    evaluate_regime,
    regime_for_display,
)
from hunter_indicators.regime.decision import (
    EMPTY_REGIME_STATE,
    RegimeDecision,
    RegimeDisplay,
    RegimeReading,
    RegimeState,
)
from hunter_indicators.regime.hourly import (
    TrendVerdict,
    VolVerdict,
    absolute_returns,
    classify_trend,
    classify_volatility,
    contiguous_closes,
    drawdown_from_high,
    percentile_rank,
    realised_vol,
    sma,
    vol_readings,
)
from hunter_indicators.regime.hourly_model import (
    DEFAULT_HOURLY_THRESHOLDS,
    REASON_DRAWDOWN_WARMUP,
    REASON_FUNDING_UNAVAILABLE,
    REASON_SCORE_UNAVAILABLE,
    REASON_TREND_WARMUP,
    REASON_VOL_WARMUP,
    REGIME_HOURLY_VERSION,
    ComponentWeights,
    HourlyThresholds,
    HourlyTrend,
    VolRegime,
    project_regime,
)
from hunter_indicators.regime.hourly_score import (
    breadth_pct_of,
    build_components,
    build_snapshot,
    count_breadth,
    score_of,
)
from hunter_indicators.regime.hourly_snapshot import (
    BreadthCount,
    FundingAverage,
    RegimeSnapshot,
    ScoreComponent,
    SnapshotInputs,
)
from hunter_indicators.regime.model import (
    CONFIDENCE_QUANTUM,
    EMPTY_BREADTH,
    RATIO_QUANTUM,
    REASON_ATR_WARMUP,
    REASON_BREADTH_COVERAGE,
    REASON_NO_DISPERSION,
    REASON_NO_TREND_INPUT,
    REASON_NO_VOLATILITY,
    REASON_STALE_OBSERVATION,
    REASON_VOLATILITY_WARMUP,
    REGIME_CLASSIFIER_VERSION,
    REGIME_PROJECTION,
    VOLATILITY_QUANTUM,
    Breadth,
    BreadthObservation,
    HourlySample,
    MarketTrendReading,
    RegimeObservation,
    RegimeThresholds,
    RegimeTrend,
    RegimeVolatility,
    VolatilityReference,
)
from hunter_indicators.regime.series import (
    final_candles,
    hourly_samples,
    return_over,
    trailing_volatility,
    volatility_reference,
)

__all__ = [
    "Breadth",
    "BreadthCount",
    "BreadthObservation",
    "CONFIDENCE_QUANTUM",
    "ComponentWeights",
    "DEFAULT_HOURLY_THRESHOLDS",
    "EMPTY_BREADTH",
    "EMPTY_REGIME_STATE",
    "FundingAverage",
    "HourlySample",
    "HourlyThresholds",
    "HourlyTrend",
    "MarketTrendReading",
    "RATIO_QUANTUM",
    "REASON_ATR_WARMUP",
    "REASON_BREADTH_COVERAGE",
    "REASON_DRAWDOWN_WARMUP",
    "REASON_FUNDING_UNAVAILABLE",
    "REASON_NO_DISPERSION",
    "REASON_NO_TREND_INPUT",
    "REASON_NO_VOLATILITY",
    "REASON_SCORE_UNAVAILABLE",
    "REASON_STALE_OBSERVATION",
    "REASON_TREND_WARMUP",
    "REASON_VOLATILITY_WARMUP",
    "REASON_VOL_WARMUP",
    "REGIME_CLASSIFIER_VERSION",
    "REGIME_HOURLY_VERSION",
    "REGIME_PROJECTION",
    "RegimeDecision",
    "RegimeDisplay",
    "RegimeObservation",
    "RegimeReading",
    "RegimeSnapshot",
    "RegimeState",
    "RegimeThresholds",
    "RegimeTrend",
    "RegimeVolatility",
    "ScoreComponent",
    "SnapshotInputs",
    "TrendVerdict",
    "VOLATILITY_QUANTUM",
    "VolRegime",
    "VolVerdict",
    "VolatilityReference",
    "absolute_returns",
    "advance_regime",
    "breadth_pct_of",
    "build_components",
    "build_snapshot",
    "classify_market_trend",
    "classify_regime",
    "classify_trend",
    "classify_volatility",
    "compute_breadth",
    "contiguous_closes",
    "count_breadth",
    "drawdown_from_high",
    "evaluate_regime",
    "final_candles",
    "hourly_samples",
    "percentile_rank",
    "project_regime",
    "realised_vol",
    "regime_for_display",
    "return_over",
    "score_of",
    "sma",
    "trailing_volatility",
    "trend_of",
    "vol_readings",
    "volatility_reference",
]
