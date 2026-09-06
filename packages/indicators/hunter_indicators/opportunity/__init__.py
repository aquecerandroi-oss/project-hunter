"""``hunter_indicators.opportunity`` — the score, its status and its explanation.

Everything here is a pure function of what the caller resolved: the feature
vector, the baseline projection at that cut, the stage decision, the regime
decision and the anomaly states. No clock, no IO — which is what makes
"recompute this score from the envelope it stored" a guarantee rather than a
hope (``docs/DATABASE.md`` §17.3).

Six modules: ``model.py`` (contract and quanta), ``profile.py`` (the frozen
roster of components), ``components.py`` (one component at a time), ``scorer.py``
(the score, the direction, the confidence and the envelope), ``status.py`` (the
episode machine) and ``explanation.py`` / ``history.py`` (the deterministic
pt-BR answer and the sampling rule).
"""

from hunter_indicators.opportunity.components import score_mad_component
from hunter_indicators.opportunity.envelope import envelope_bytes, opportunity_envelope
from hunter_indicators.opportunity.episode import (
    EpisodeAction,
    EpisodeState,
    StatusDecision,
    StatusSample,
    StatusThresholds,
)
from hunter_indicators.opportunity.explanation import EXPLANATION_VERSION, explain
from hunter_indicators.opportunity.history import (
    HISTORY_POLICY_VERSION,
    HistoryMark,
    HistoryPolicy,
    HistoryVerdict,
    quality_signature,
    should_record_history,
)
from hunter_indicators.opportunity.model import (
    COMPONENT_PROFILE_VERSION,
    COMPONENT_QUANTUM,
    CONFIDENCE_QUANTUM,
    REASON_ANOMALIES_UNKNOWN,
    REASON_DEGRADED,
    REASON_DIRECTIONAL_CANCELS,
    REASON_NO_AGENTS,
    REASON_NO_DIRECTIONAL_EVIDENCE,
    REASON_NO_EVIDENCE,
    REASON_NO_USABLE_INPUT,
    REASON_NOT_IMPLEMENTED,
    REASON_REGIME_CONFIDENCE,
    REASON_REGIME_STALE,
    REASON_REGIME_UNKNOWN,
    SCORE_QUANTUM,
    SCORER_VERSION,
    ComponentDefinition,
    ComponentInput,
    ComponentKind,
    ComponentScore,
    DirectionRule,
    EarlyMovement,
    InputScore,
    ScoreResult,
)
from hunter_indicators.opportunity.overlays import (
    REGIME_COMPATIBLE,
    REGIME_HIGH_VOLATILITY_ADJUSTMENT,
    REGIME_NEUTRAL,
    REGIME_OPPOSED,
    score_anomaly_component,
    score_consensus_component,
    score_external_component,
    score_regime_component,
)
from hunter_indicators.opportunity.profile import COMPONENTS, component_for
from hunter_indicators.opportunity.scorer import ScoreContext, score_opportunity
from hunter_indicators.opportunity.status import advance_status, candidate_status
from hunter_indicators.opportunity.weights import WeightProfile

__all__ = [
    "COMPONENTS",
    "COMPONENT_PROFILE_VERSION",
    "COMPONENT_QUANTUM",
    "CONFIDENCE_QUANTUM",
    "EXPLANATION_VERSION",
    "HISTORY_POLICY_VERSION",
    "REASON_ANOMALIES_UNKNOWN",
    "REASON_DEGRADED",
    "REASON_DIRECTIONAL_CANCELS",
    "REASON_NOT_IMPLEMENTED",
    "REASON_NO_AGENTS",
    "REASON_NO_DIRECTIONAL_EVIDENCE",
    "REASON_NO_EVIDENCE",
    "REASON_NO_USABLE_INPUT",
    "REASON_REGIME_CONFIDENCE",
    "REASON_REGIME_STALE",
    "REASON_REGIME_UNKNOWN",
    "REGIME_COMPATIBLE",
    "REGIME_HIGH_VOLATILITY_ADJUSTMENT",
    "REGIME_NEUTRAL",
    "REGIME_OPPOSED",
    "SCORER_VERSION",
    "SCORE_QUANTUM",
    "ComponentDefinition",
    "ComponentInput",
    "ComponentKind",
    "ComponentScore",
    "DirectionRule",
    "EarlyMovement",
    "EpisodeAction",
    "EpisodeState",
    "HistoryMark",
    "HistoryPolicy",
    "HistoryVerdict",
    "InputScore",
    "ScoreContext",
    "ScoreResult",
    "StatusDecision",
    "StatusSample",
    "StatusThresholds",
    "WeightProfile",
    "advance_status",
    "candidate_status",
    "component_for",
    "envelope_bytes",
    "explain",
    "opportunity_envelope",
    "quality_signature",
    "score_anomaly_component",
    "score_consensus_component",
    "score_external_component",
    "score_mad_component",
    "score_opportunity",
    "score_regime_component",
    "should_record_history",
]
