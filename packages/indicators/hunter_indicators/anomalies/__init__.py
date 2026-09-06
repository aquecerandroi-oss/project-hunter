"""``hunter_indicators.anomalies`` — the ten detectors of the joint M2 decision.

Three layers, none of which touches IO:

1. ``severity.py`` — ``d`` in MADs and the versioned piecewise transformation
   into a 0-100 severity, with direction carried apart;
2. ``detectors.py`` — the roster: what each detector reads, which tail it is
   about, and its versioned thresholds;
3. ``lifecycle.py`` — the pure state machine of ``active -> resolved/expired``
   plus the ``ok | stale | unknown`` axis, deduplicated by ``(market, type)``.

Persistence is T2.5's. What lives here decides; nothing here writes.
"""

from hunter_indicators.anomalies.detectors import (
    DEFAULT_DETECTORS,
    DETECTOR_VERSION,
    EXPIRE_AFTER,
    FIRE_MIN_SEVERITY,
    HOLD_MIN_SEVERITY,
    REASON_DISABLED,
    REASON_NO_FEATURE,
    RESOLVE_AFTER,
    RESOLVE_MIN_READINGS,
    DetectorDefinition,
    default_detectors,
    detector_for,
)
from hunter_indicators.anomalies.evaluation import (
    AnomalyEvaluation,
    evaluate_detector,
    evaluate_detectors,
)
from hunter_indicators.anomalies.lifecycle import (
    REASON_NO_DATA,
    AnomalyAction,
    AnomalyState,
    AnomalyTransition,
    advance,
    advance_all,
    no_data,
)
from hunter_indicators.anomalies.severity import (
    BASELINE_DAYS,
    CONFIDENCE_QUANTUM,
    NORMALIZATION_METHOD,
    REASON_MAD_ZERO,
    SEVERITY_QUANTUM,
    AnomalyDirection,
    DetectorSide,
    Deviation,
    NormalizationConfig,
    confidence_of,
    deviation_in_mads,
    direction_of,
    evaluate_deviation,
    severity_of,
)

__all__ = [
    "BASELINE_DAYS",
    "CONFIDENCE_QUANTUM",
    "DEFAULT_DETECTORS",
    "DETECTOR_VERSION",
    "EXPIRE_AFTER",
    "FIRE_MIN_SEVERITY",
    "HOLD_MIN_SEVERITY",
    "NORMALIZATION_METHOD",
    "REASON_DISABLED",
    "REASON_MAD_ZERO",
    "REASON_NO_DATA",
    "REASON_NO_FEATURE",
    "RESOLVE_AFTER",
    "RESOLVE_MIN_READINGS",
    "SEVERITY_QUANTUM",
    "AnomalyAction",
    "AnomalyDirection",
    "AnomalyEvaluation",
    "AnomalyState",
    "AnomalyTransition",
    "DetectorDefinition",
    "DetectorSide",
    "Deviation",
    "NormalizationConfig",
    "advance",
    "advance_all",
    "confidence_of",
    "default_detectors",
    "detector_for",
    "deviation_in_mads",
    "direction_of",
    "evaluate_detector",
    "evaluate_detectors",
    "evaluate_deviation",
    "no_data",
    "severity_of",
]
