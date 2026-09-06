"""``hunter_indicators.regime`` — the v0 market regime of ``docs/PIPELINE.md`` §4.

Pure functions over what the caller already holds: the BTC feature vector, the
persisted 1-minute candles and the per-market readings that make the breadth.
Nothing here calls an exchange, reads a clock or touches the database — the
scanner (T2.5) resolves the inputs and persists the decision.

Four modules: ``model.py`` (thresholds, readings, state, decision), ``series.py``
(the internal statistics the feature set does not publish), ``breadth.py`` (the
confirmation and its composition) and ``classifier.py`` (the verdict, its
hysteresis and the stale stamp for display).
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
    "CONFIDENCE_QUANTUM",
    "EMPTY_BREADTH",
    "EMPTY_REGIME_STATE",
    "RATIO_QUANTUM",
    "REASON_ATR_WARMUP",
    "REASON_BREADTH_COVERAGE",
    "REASON_NO_DISPERSION",
    "REASON_NO_TREND_INPUT",
    "REASON_NO_VOLATILITY",
    "REASON_STALE_OBSERVATION",
    "REASON_VOLATILITY_WARMUP",
    "REGIME_CLASSIFIER_VERSION",
    "REGIME_PROJECTION",
    "VOLATILITY_QUANTUM",
    "Breadth",
    "BreadthObservation",
    "HourlySample",
    "MarketTrendReading",
    "RegimeDecision",
    "RegimeDisplay",
    "RegimeObservation",
    "RegimeReading",
    "RegimeState",
    "RegimeThresholds",
    "RegimeTrend",
    "RegimeVolatility",
    "VolatilityReference",
    "advance_regime",
    "classify_market_trend",
    "classify_regime",
    "compute_breadth",
    "evaluate_regime",
    "final_candles",
    "hourly_samples",
    "regime_for_display",
    "return_over",
    "trailing_volatility",
    "trend_of",
    "volatility_reference",
]
