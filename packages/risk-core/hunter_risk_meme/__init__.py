"""``hunter_risk_meme`` — the pure admission engine of ``docs/RISK_ENGINE_MEME.md`` (T4.14).

A sibling of ``hunter_risk`` that never imports it (§13; ``test_boundary.py``):
same discipline (frozen, closed, float-free models; every check recorded; the
binding ceiling published; ``unavailable`` rejects), different doctrine (risk =
the whole spend, caps in SOL, a latched daily kill switch, no book and no beta).
"""

from hunter_risk_meme.checks import REFUSAL_NAMES
from hunter_risk_meme.checks_wallet import MINT_COOLDOWN_AFTER_LOSS
from hunter_risk_meme.conviction import (
    CONVICTION_REFUSALS,
    LADDER_REFUSALS,
    MemeConviction,
    conviction_cap,
    conviction_check,
)
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
from hunter_risk_meme.profile import (
    LAUNCH_LANE,
    LAUNCH_RELAXED_CHECKS,
    LAUNCH_SKIPPED_CHECKS,
    MemeLaunchProfile,
    launch_open_cap_check,
)
from hunter_risk_meme.sizing import CAP_ORDER, size_entry
from hunter_risk_meme.spot_profile import (
    SPOT_CAP_ORDER,
    SPOT_CHECK_NAMES,
    SPOT_LANE,
    SPOT_REFUSAL_NAMES,
    MemeSpotProfile,
    SpotSignalInputs,
    evaluate_spot_entry,
)

__all__ = [
    "CAP_ORDER",
    "CONVICTION_REFUSALS",
    "EXIT_REASONS",
    "LADDER_REFUSALS",
    "MINT_COOLDOWN_AFTER_LOSS",
    "LAUNCH_LANE",
    "LAUNCH_RELAXED_CHECKS",
    "LAUNCH_SKIPPED_CHECKS",
    "MEME_PAPER_V0",
    "POLICY_ENV",
    "PUMPSWAP_PROGRAM",
    "PUMP_PROGRAM",
    "REFUSAL_NAMES",
    "SPOT_CAP_ORDER",
    "SPOT_CHECK_NAMES",
    "SPOT_LANE",
    "SPOT_REFUSAL_NAMES",
    "CheckState",
    "Counterfactual",
    "CurveState",
    "ExitParams",
    "LimitCap",
    "MemeCheck",
    "MemeContext",
    "MemeConviction",
    "MemeDecision",
    "MemeEntryProposal",
    "MemeExitPlan",
    "MemeExitProposal",
    "MemeKillSwitchAssessment",
    "MemeKillSwitchInputs",
    "MemeLaunchProfile",
    "MemeLimits",
    "MemePolicyMissing",
    "MemeResumeAuthorization",
    "MemeResumeRefused",
    "MemeSizing",
    "MemeSpotProfile",
    "MemeWalletState",
    "OpenMemePosition",
    "PendingMemeIntent",
    "PositionForExit",
    "SpotSignalInputs",
    "assess",
    "conviction_cap",
    "conviction_check",
    "decide_exit",
    "evaluate_meme_entry",
    "evaluate_meme_exit",
    "evaluate_spot_entry",
    "exit_route",
    "launch_open_cap_check",
    "limits_from_env",
    "most_restrictive",
    "resume",
    "size_entry",
]
