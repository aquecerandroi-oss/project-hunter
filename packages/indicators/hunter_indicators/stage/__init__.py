"""``hunter_indicators.stage`` — EARLY / DEVELOPING / EXTENDED.

``r = |return_1h| / atr_14_pct``, both fractions, over the anchored Wilder ATR of
T2.2 (14 periods, complete 15-minute UTC bars). Thresholds come from
``opportunity_weights.weights["stage"]``: the joint M2 decision made them
versioned, and a stage decided by a constant in code could not be replayed once
the profile moved. The rationale is in ``.claude/state/notes-T2.3.md`` §4.

Two modules, one public door: ``model.py`` holds the contract (thresholds,
inputs, hysteresis state, decision) and ``classifier.py`` the pure function.
The split is the 350-line budget (``infra/scripts/check_file_size.py``), the same
reason ``analysis_baselines.py`` is not inside ``analysis.py``; the import path
``from hunter_indicators.stage import classify_stage`` is unchanged.

Pure: no clock, no IO. ``observation_ts`` is the identity of the observation, so
recomputing one instant cannot confirm twice.
"""

from hunter_indicators.stage.classifier import classify_stage
from hunter_indicators.stage.model import (
    ATR_KEY,
    CONFIRMATION_KEYS,
    EMPTY_STAGE_STATE,
    NO_STAGE_EXTRAS,
    READ_KEYS,
    REASON_ATR_DEGRADED,
    REASON_ATR_WARMUP,
    REASON_NOT_CONFIRMED,
    REASON_QUALITY_LOST,
    REASON_RETURN_UNAVAILABLE,
    REASON_STAGE_WITHDRAWN,
    REASON_STALE_OBSERVATION,
    RETURN_4H_KEY,
    RETURN_KEY,
    STAGE_BASIS_EXHAUSTION,
    STAGE_BASIS_RATIO,
    StageDecision,
    StageInputs,
    StageState,
    StageThresholds,
)

__all__ = [
    "ATR_KEY",
    "CONFIRMATION_KEYS",
    "EMPTY_STAGE_STATE",
    "NO_STAGE_EXTRAS",
    "READ_KEYS",
    "REASON_ATR_DEGRADED",
    "REASON_ATR_WARMUP",
    "REASON_NOT_CONFIRMED",
    "REASON_QUALITY_LOST",
    "REASON_RETURN_UNAVAILABLE",
    "REASON_STAGE_WITHDRAWN",
    "REASON_STALE_OBSERVATION",
    "RETURN_4H_KEY",
    "RETURN_KEY",
    "STAGE_BASIS_EXHAUSTION",
    "STAGE_BASIS_RATIO",
    "StageDecision",
    "StageInputs",
    "StageState",
    "StageThresholds",
    "classify_stage",
]
