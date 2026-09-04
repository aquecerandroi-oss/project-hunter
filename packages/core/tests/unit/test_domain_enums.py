"""Unit tests for hunter_core.domain.enums: completeness and exact values.

Guards against a future edit silently dropping or renaming a member — the
values here are copied from docs/DATABASE.md and docs/RISK_ENGINE.md and must
keep matching them (and, from T04 onward, the real Postgres enums).
"""

from enum import StrEnum

import pytest

from hunter_core.domain import enums
from hunter_core.domain.enums import (
    ALL_ENUMS,
    ExecutionMode,
    KillSwitchState,
    MarketRegime,
    OrganizationRole,
    PortfolioType,
)

pytestmark = pytest.mark.unit

EXPECTED_ENUM_CLASSES = {
    "OrganizationRole",
    "Plan",
    "KillSwitchState",
    "MemberStatus",
    "WorkspaceObjective",
    "SubscriptionStatus",
    "ExchangeStatus",
    "MarketType",
    "MarketStatus",
    "Timeframe",
    "OrderSide",
    "FeatureCategory",
    "AnomalyType",
    "AnomalyStatus",
    "RegimeScope",
    "MarketRegime",
    "TradeDirection",
    "OpportunityStatus",
    "StrategyVersionStatus",
    "SignalStatus",
    "OutcomeResult",
    "AgentStatus",
    "StatsWindow",
    "RiskPreset",
    "PortfolioType",
    "PortfolioStatus",
    "ProposalStatus",
    "OrderType",
    "OrderPurpose",
    "ExecutionMode",
    "OrderStatus",
    "PositionStatus",
    "ExitReason",
    "RiskEventType",
    "RiskEventSeverity",
    "KillSwitchScope",
    "ConnectionStatus",
    "BacktestStatus",
    "BacktestWarningCode",
    "IntelligenceSourceKind",
    "AlertChannel",
    "NotificationStatus",
    "WorkerHeartbeatStatus",
}


def test_every_expected_enum_class_exists() -> None:
    for name in EXPECTED_ENUM_CLASSES:
        cls = getattr(enums, name)
        assert issubclass(cls, StrEnum), f"{name} must be a StrEnum"


def test_signal_direction_aliases_trade_direction() -> None:
    assert enums.SignalDirection is enums.TradeDirection


def test_all_enums_registry_covers_expected_classes() -> None:
    registered_classes = set(ALL_ENUMS.values())
    for name in EXPECTED_ENUM_CLASSES:
        cls = getattr(enums, name)
        assert cls in registered_classes, f"{name} missing from ALL_ENUMS"


def test_kill_switch_state_matches_database_md() -> None:
    assert [member.value for member in KillSwitchState] == [
        "ACTIVE",
        "WARNING",
        "TRADING_DISABLED",
        "EMERGENCY",
    ]


def test_organization_role_matches_database_md() -> None:
    assert [member.value for member in OrganizationRole] == [
        "OWNER",
        "ADMIN",
        "TRADER",
        "ANALYST",
        "VIEWER",
    ]


def test_execution_mode_matches_database_md() -> None:
    assert [member.value for member in ExecutionMode] == ["paper", "shadow", "live"]


def test_portfolio_type_matches_database_md() -> None:
    assert [member.value for member in PortfolioType] == ["paper", "shadow", "live"]


def test_market_regime_matches_pipeline_md_v0_and_v1() -> None:
    assert [member.value for member in MarketRegime] == [
        "BTC_BULL",
        "BTC_BEAR",
        "SIDEWAYS",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "RISK_ON",
        "RISK_OFF",
        "ALT_EXPANSION",
        "PANIC",
        "LIQUIDITY_CONTRACTION",
    ]
