"""The durable half of the kill switch — RISK_ENGINE.md §5, DATABASE.md §18.7.

:mod:`hunter_risk` is the pure machine: given a portfolio state and the limits it
says what the switch *is*. Nothing in it persists, locks or authenticates. This
package is the other half — the latch that survives a restart, the audited
transition that has to exist for the column the workers read to move, the daily
reference in ``America/Sao_Paulo``, and the peak that never falls.

The dependency is one-directional: everything here imports ``hunter_risk`` and
nothing there imports this.
"""

from hunter_core.risk.daily import (
    DayReference,
    DayReferenceReason,
    PersistedRiskState,
    next_peak,
    resolve_day_reference,
)
from hunter_core.risk.kill_switch import KillSwitchEvaluation, evaluate_and_persist
from hunter_core.risk.resume import (
    RESUME_EVIDENCE_MAX_AGE_S,
    ResumeOutcome,
    ResumeRefused,
    resume,
)
from hunter_core.risk.scopes import (
    EffectiveKillSwitch,
    RiskStateMissing,
    effective_state,
    load_locked_state,
)
from hunter_core.risk.transitions import (
    ConcurrentTransition,
    build_evidence,
    latest_transition,
    record_transition,
)

__all__ = [
    "RESUME_EVIDENCE_MAX_AGE_S",
    "ConcurrentTransition",
    "DayReference",
    "DayReferenceReason",
    "EffectiveKillSwitch",
    "KillSwitchEvaluation",
    "PersistedRiskState",
    "ResumeOutcome",
    "ResumeRefused",
    "RiskStateMissing",
    "build_evidence",
    "effective_state",
    "evaluate_and_persist",
    "latest_transition",
    "load_locked_state",
    "next_peak",
    "record_transition",
    "resolve_day_reference",
    "resume",
]
