"""``hunter_risk_meme`` — the pure admission engine of ``docs/RISK_ENGINE_MEME.md`` (T4.14).

A sibling of ``hunter_risk`` that never imports it (§13; ``test_boundary.py``):
same discipline (frozen, closed, float-free models; every check recorded; the
binding ceiling published; ``unavailable`` rejects), different doctrine (risk =
the whole spend, caps in SOL, a latched daily kill switch, no book and no beta).
"""

from hunter_risk_meme.checks import REFUSAL_NAMES
from hunter_risk_meme.decision import (
    CheckState,
    Counterfactual,
    LimitCap,
    MemeCheck,
    MemeDecision,
    MemeExitPlan,
    MemeSizing,
)
from hunter_risk_meme.evaluate import evaluate_meme_entry, evaluate_meme_exit
from hunter_risk_meme.exits import (
    EXIT_REASONS,
    ExitParams,
    PositionForExit,
    decide_exit,
    exit_route,
)
from hunter_risk_meme.inputs import (
    PUMP_PROGRAM,
    PUMPSWAP_PROGRAM,
    CurveState,
    MemeContext,
    MemeEntryProposal,
    MemeExitProposal,
    MemeKillSwitchInputs,
    MemeWalletState,
    OpenMemePosition,
    PendingMemeIntent,
)
from hunter_risk_meme.kill_switch import (
    MemeKillSwitchAssessment,
    MemeResumeAuthorization,
    MemeResumeRefused,
    assess,
    most_restrictive,
    resume,
)
from hunter_risk_meme.limits import (
    MEME_PAPER_V0,
    POLICY_ENV,
    MemeLimits,
    MemePolicyMissing,
    limits_from_env,
)
from hunter_risk_meme.sizing import CAP_ORDER, size_entry

__all__ = [
    "CAP_ORDER",
    "EXIT_REASONS",
    "MEME_PAPER_V0",
    "POLICY_ENV",
    "PUMPSWAP_PROGRAM",
    "PUMP_PROGRAM",
    "REFUSAL_NAMES",
    "CheckState",
    "Counterfactual",
    "CurveState",
    "ExitParams",
    "LimitCap",
    "MemeCheck",
    "MemeContext",
    "MemeDecision",
    "MemeEntryProposal",
    "MemeExitPlan",
    "MemeExitProposal",
    "MemeKillSwitchAssessment",
    "MemeKillSwitchInputs",
    "MemeLimits",
    "MemePolicyMissing",
    "MemeResumeAuthorization",
    "MemeResumeRefused",
    "MemeSizing",
    "MemeWalletState",
    "OpenMemePosition",
    "PendingMemeIntent",
    "PositionForExit",
    "assess",
    "decide_exit",
    "evaluate_meme_entry",
    "evaluate_meme_exit",
    "exit_route",
    "limits_from_env",
    "most_restrictive",
    "resume",
    "size_entry",
]
