"""Unit tests for hunter_core.domain.enums: completeness and exact values.

Guards against a future edit silently dropping or renaming a member — the
values here are copied from docs/DATABASE.md and docs/RISK_ENGINE.md and must
keep matching them (and, from T04 onward, the real Postgres enums).
"""

import uuid
from enum import StrEnum

import pytest

from hunter_core.domain import enums
from hunter_core.domain.enums import (
    ALL_ENUMS,
    AnomalyEvaluationState,
    AnomalyType,
    BaselineSampling,
    BaselineSource,
    ExecutionMode,
    KillSwitchState,
    MarketRegime,
    OpportunityStage,
    OpportunityStatus,
    OrganizationRole,
    PortfolioType,
    ShadowCohort,
    ShadowTrackingState,
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
    "ShadowTrackingState",
    "OpportunityStage",
    "AnomalyEvaluationState",
    "BaselineSource",
    "BaselineSampling",
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
        "UNKNOWN",
    ]


def test_market_regime_unknown_is_last_because_0003_appended_it() -> None:
    """``ALTER TYPE ... ADD VALUE`` appends, and ``pg_enum.enumsortorder`` is what
    ``test_migrations`` compares against. Declaration order here *is* the label
    order in the database, so a member inserted in the middle of this class
    without a matching ``BEFORE``/``AFTER`` in the migration is drift.
    """
    assert list(MarketRegime)[-1] is MarketRegime.UNKNOWN


def test_opportunity_status_gains_only_extended_and_keeps_it_before_expired() -> None:
    """The joint M2 decision adds exactly one global status: ``EXTENDED``.

    ``IN_POSITION`` and ``BLOCKED_BY_RISK`` stay derived per organization at read
    time (DATABASE.md §5), so they are still absent. ``EXTENDED`` sits before
    ``EXPIRED`` because ``0003`` adds it with ``BEFORE 'EXPIRED'`` — this class
    and ``enumsortorder`` have to agree.
    """
    assert [member.value for member in OpportunityStatus] == [
        "NORMAL",
        "WATCHING",
        "ANOMALY",
        "HOT",
        "ENTRY_CANDIDATE",
        "EXTENDED",
        "EXPIRED",
    ]


def test_anomaly_type_gains_the_two_missing_mvp_detectors_before_phase_two() -> None:
    assert [member.value for member in AnomalyType] == [
        "VOLUME_SPIKE",
        "PRICE_ACCELERATION",
        "VOLATILITY_EXPANSION",
        "ORDERBOOK_IMBALANCE",
        "OPEN_INTEREST_SPIKE",
        "FUNDING_ANOMALY",
        "LIQUIDATION_CLUSTER",
        "CROSS_EXCHANGE_DIVERGENCE",
        "TRADE_VELOCITY_SPIKE",
        "MOMENTUM_SHIFT",
        "SOCIAL_SPIKE",
        "WHALE_ACTIVITY",
    ]


def test_opportunity_stage_matches_the_joint_decision() -> None:
    """``NONE`` is a real stage, not a NULL: during ATR warm-up there is no stage
    yet, and the Radar has to say so instead of implying EARLY.
    """
    assert [member.value for member in OpportunityStage] == [
        "EARLY",
        "DEVELOPING",
        "EXTENDED",
        "NONE",
    ]


def test_anomaly_evaluation_state_separates_quality_from_lifecycle() -> None:
    """``active + unknown`` is what an anomaly holds when its data stopped
    arriving: still active, not eligible, and never resolved by absence.
    """
    assert [member.value for member in AnomalyEvaluationState] == ["ok", "stale", "unknown"]


def test_baseline_source_and_sampling_match_the_joint_decision() -> None:
    assert [member.value for member in BaselineSource] == ["live", "bootstrap"]
    assert [member.value for member in BaselineSampling] == ["per_minute"]


def test_shadow_tracking_state_matches_the_shadow_lab_decision() -> None:
    assert [member.value for member in ShadowTrackingState] == [
        "pending_entry",
        "active",
        "terminal",
        "no_entry",
        "censored",
    ]


def test_a_replay_cohort_round_trips_its_run_id() -> None:
    run_id = uuid.UUID("0199e4a0-1c3d-7a11-8f0a-2b3c4d5e6f70")
    cohort = ShadowCohort.replay(run_id)
    assert cohort == f"replay:{run_id}"
    assert ShadowCohort.run_id(cohort) == run_id
    assert ShadowCohort.run_id(ShadowCohort.PROSPECTIVE) is None


@pytest.mark.parametrize(
    "cohort",
    ["", "replay", "replay:", "replay:nope", "prospective ", "x", "prospective\n"],
)
def test_an_unparseable_cohort_is_rejected_in_python_too(cohort: str) -> None:
    """The same shape the CHECK constraint enforces — a cohort that the database
    would refuse must not reach it looking valid."""
    assert not ShadowCohort.is_valid(cohort)
    with pytest.raises(ValueError, match="not a valid shadow cohort"):
        ShadowCohort.run_id(cohort)
