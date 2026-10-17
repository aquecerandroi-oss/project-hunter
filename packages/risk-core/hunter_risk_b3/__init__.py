"""``hunter_risk_b3`` — the pure risk engine of the B3 robot (docs/RISK_ENGINE_B3.md v1.0).

Sibling of ``hunter_risk`` (SPOT paper) and ``hunter_risk_meme`` in the same distribution;
none of the three imports another (``tests/unit/b3/test_boundary.py``, the T4.14
precedent). No network, database or clock: everything comes in as arguments and the
instant is ``broker.as_of``. Money, prices, volumes and limits are ``Decimal`` (a float
does not construct); every instant is UTC.

Entry point: :func:`evaluate` (25 checks + sizing with ``binding_constraint``) and
:func:`evaluate_exit` (always approves). Kill-switch resolution, the day-loss ledger, the
limits profile and pure session/calendar builders are exported for the service (R5) and
the API (R4).
"""

from __future__ import annotations

from hunter_risk_b3.context import (
    SPEC_FIELDS,
    ArmedStrategy,
    AuthorityView,
    CalendarB3,
    ClockCheck,
    CurrentContract,
    KillSwitchB3,
    MarginInputs,
    OrderCheckResult,
    SessionContext,
    SpecInputs,
    SpecNow,
    SpecPin,
)
from hunter_risk_b3.daily_loss import DayDeal, DaySummary, DealKind, summarize_deals
from hunter_risk_b3.decision import CHECK_NAMES, SIZING_ZERO, B3Check, B3Sizing, RiskDecision
from hunter_risk_b3.enums import (
    AuthorityPhase,
    CheckState,
    DecisionKind,
    ExitReason,
    KillCause,
    KillSwitchState,
    Side,
    SpecStatus,
    TradeMode,
)
from hunter_risk_b3.evaluate import ExitRequest, evaluate, evaluate_exit
from hunter_risk_b3.frame import limit_price_for
from hunter_risk_b3.inputs import (
    AccountSnapshot,
    B3EntryProposal,
    BrokerOrder,
    BrokerPosition,
    BrokerSnapshot,
    QuoteSnapshot,
    TerminalState,
)
from hunter_risk_b3.kill_switch import (
    RESTRICTION_ORDER,
    KillPolicy,
    automatic_state,
    blocks_entries,
    effective_state,
    halve_for_warning,
    kill_policy,
    most_restrictive,
)
from hunter_risk_b3.limits import (
    LimitsInvalid,
    RiskLimitsB3,
    initial_limits,
    parse_limits,
    parse_limits_json,
)
from hunter_risk_b3.ops import AuditPath, DayPnl, FeeSchedule, LastReconcile, RobotOpsState
from hunter_risk_b3.session import (
    SAO_PAULO,
    ContractRow,
    GridRow,
    build_calendar,
    build_session,
    grid_for,
    local_to_utc,
    session_date_of,
)
from hunter_risk_b3.sizing import CAP_ORDER, normalize_volume, risk_per_contract_brl

__all__ = [
    "CAP_ORDER",
    "CHECK_NAMES",
    "RESTRICTION_ORDER",
    "SAO_PAULO",
    "SIZING_ZERO",
    "SPEC_FIELDS",
    "AccountSnapshot",
    "ArmedStrategy",
    "AuditPath",
    "AuthorityPhase",
    "AuthorityView",
    "B3Check",
    "B3EntryProposal",
    "B3Sizing",
    "BrokerOrder",
    "BrokerPosition",
    "BrokerSnapshot",
    "CalendarB3",
    "CheckState",
    "ClockCheck",
    "ContractRow",
    "CurrentContract",
    "DayDeal",
    "DayPnl",
    "DaySummary",
    "DealKind",
    "DecisionKind",
    "ExitReason",
    "ExitRequest",
    "FeeSchedule",
    "GridRow",
    "KillCause",
    "KillPolicy",
    "KillSwitchB3",
    "KillSwitchState",
    "LastReconcile",
    "LimitsInvalid",
    "MarginInputs",
    "OrderCheckResult",
    "QuoteSnapshot",
    "RiskDecision",
    "RiskLimitsB3",
    "RobotOpsState",
    "SessionContext",
    "Side",
    "SpecInputs",
    "SpecNow",
    "SpecPin",
    "SpecStatus",
    "TerminalState",
    "TradeMode",
    "automatic_state",
    "blocks_entries",
    "build_calendar",
    "build_session",
    "effective_state",
    "evaluate",
    "evaluate_exit",
    "grid_for",
    "halve_for_warning",
    "initial_limits",
    "kill_policy",
    "limit_price_for",
    "local_to_utc",
    "most_restrictive",
    "normalize_volume",
    "parse_limits",
    "parse_limits_json",
    "risk_per_contract_brl",
    "session_date_of",
    "summarize_deals",
]
