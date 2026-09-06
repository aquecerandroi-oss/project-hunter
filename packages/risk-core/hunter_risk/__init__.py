"""hunter_risk - the pure core of the Risk Engine.

``evaluate`` and ``evaluate_exit`` are functions of their arguments and nothing
else: no clock, no Redis, no Postgres, no HTTP. The numbers they enforce are
Everton's, frozen in :data:`hunter_risk.limits.PAPER_V1`.
"""

from hunter_risk.checks import gate_checks
from hunter_risk.confirmations import post_sizing_checks
from hunter_risk.decision import CheckState, ExitPlan, LimitCap, RiskCheck, RiskDecision, Sizing
from hunter_risk.evaluate import ENTRY_CHECKS, evaluate, evaluate_exit
from hunter_risk.exposure import (
    OpenPosition,
    PendingEntry,
    PortfolioState,
    advance_peak,
    sao_paulo_day_start_utc,
)
from hunter_risk.inputs import (
    BetaEstimate,
    BookLevel,
    EntryProposal,
    ExitProposal,
    MarketIdentity,
    MarketLiquidity,
    MarketSpec,
)
from hunter_risk.kill_switch import (
    KillSwitchAssessment,
    KillSwitchInputs,
    ResumeAuthorization,
    assess,
    entry_size_multiplier,
    most_restrictive,
    resume,
)
from hunter_risk.limits import PAPER_V1, RiskLimits
from hunter_risk.observations import book_capacity_qty, observed_price, worst_entry_price
from hunter_risk.sizing import round_trip_cost_fraction, size_entry

__version__ = "0.0.0"

__all__ = [
    "ENTRY_CHECKS",
    "PAPER_V1",
    "BetaEstimate",
    "BookLevel",
    "CheckState",
    "EntryProposal",
    "ExitPlan",
    "ExitProposal",
    "KillSwitchAssessment",
    "KillSwitchInputs",
    "LimitCap",
    "MarketIdentity",
    "MarketLiquidity",
    "MarketSpec",
    "OpenPosition",
    "PendingEntry",
    "PortfolioState",
    "ResumeAuthorization",
    "RiskCheck",
    "RiskDecision",
    "RiskLimits",
    "Sizing",
    "advance_peak",
    "assess",
    "book_capacity_qty",
    "entry_size_multiplier",
    "evaluate",
    "evaluate_exit",
    "gate_checks",
    "most_restrictive",
    "observed_price",
    "post_sizing_checks",
    "resume",
    "round_trip_cost_fraction",
    "sao_paulo_day_start_utc",
    "size_entry",
    "worst_entry_price",
]
