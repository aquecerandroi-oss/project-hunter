"""Every ORM model. Importing this package populates ``Base.metadata`` in full —
Alembic's ``env.py``, the seed script and the partition script all rely on that.

Two helpers derive schema policy from the metadata itself instead of repeating a
hand-kept list: :func:`tenant_tables` (every table with ``organization_id``, i.e.
every table that needs Row Level Security, DATABASE.md §1.1/§1.2) and
:func:`partitioned_tables` (every RANGE-partitioned parent and its partition key,
§1.3).
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.dialects import postgresql

from hunter_core.db.base import Base
from hunter_core.db.models._partitions import (
    APP_ROLE,
    AUDIT_SYSTEM_POLICY,
    ORG_MATCH,
    ORG_SETTING,
    SUBPARTITION_KEY,
    TENANT_POLICY,
    WORKER_ROLE,
    create_list_partition_sql,
    create_partition_sql,
    detach_partition_sql,
    drop_partition_sql,
    harden_partition_sql,
    list_partition_name,
    month_bounds,
    months_before,
    months_from,
    partition_name,
)
from hunter_core.db.models.agents import (
    Agent,
    AgentSignal,
    AgentStats,
    SignalOutcome,
    Strategy,
    StrategyVersion,
)
from hunter_core.db.models.agents_shadow import ShadowEpisode, ShadowOutbox
from hunter_core.db.models.alerts import AlertRule, Notification
from hunter_core.db.models.analysis import (
    Anomaly,
    FeatureDefinition,
    FeatureSnapshot,
    MarketRegimeRow,
    Opportunity,
    OpportunityHistory,
    OpportunityWeights,
)
from hunter_core.db.models.backtests import Backtest, BacktestResult, BacktestTrade
from hunter_core.db.models.billing import (
    FeatureFlag,
    OrganizationFeatureOverride,
    PlanEntitlement,
    Subscription,
)
from hunter_core.db.models.exchanges import ExchangeConnection
from hunter_core.db.models.execution import Fill, Order, Position, Trade, TradeProposal
from hunter_core.db.models.identity import (
    ApiKey,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    User,
    Workspace,
)
from hunter_core.db.models.intelligence import IntelligenceEvent, IntelligenceSource
from hunter_core.db.models.market_data import (
    Candle,
    FundingRate,
    IngestionGap,
    Liquidation,
    MarketSnapshot,
    OpenInterestHistory,
)
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.db.models.portfolios import Portfolio, PortfolioEquitySnapshot, RiskProfile
from hunter_core.db.models.risk import KillSwitchTransition, RiskEvent
from hunter_core.db.models.system import AuditLog, ProcessedEvent, SystemEvent, WorkerHeartbeat

TENANT_COLUMN = "organization_id"


def tenant_tables() -> list[str]:
    """Names of every table carrying ``organization_id`` — the RLS set."""
    return [t.name for t in Base.metadata.sorted_tables if TENANT_COLUMN in t.columns]


def _partition_key(spec: str) -> str:
    """``RANGE (open_time)`` -> ``open_time``."""
    return spec.split("(", 1)[1].rsplit(")", 1)[0].strip()


def partitioned_tables() -> dict[str, str]:
    """Monthly-RANGE parent table -> partition key column (``RANGE (<col>)``)."""
    result: dict[str, str] = {}
    for table in Base.metadata.sorted_tables:
        spec = table.kwargs.get("postgresql_partition_by")
        if isinstance(spec, str) and spec.upper().startswith("RANGE"):
            result[table.name] = _partition_key(spec)
    return result


def list_partitioned_tables() -> dict[str, tuple[str, tuple[str, ...], str]]:
    """LIST parent -> (list column, its enum labels, the RANGE sub-partition key).

    ``candles`` is ``LIST (timeframe)`` and every ``candles_<tf>`` is in turn
    ``RANGE (open_time)``, so retention drops ``candles_1m_2026_05`` whole
    without touching 1h history (DATABASE.md §1.3).
    """
    result: dict[str, tuple[str, tuple[str, ...], str]] = {}
    for table in Base.metadata.sorted_tables:
        spec = table.kwargs.get("postgresql_partition_by")
        if not (isinstance(spec, str) and spec.upper().startswith("LIST")):
            continue
        column_name = _partition_key(spec)
        column_type = cast("postgresql.ENUM[Any]", table.columns[column_name].type)
        result[table.name] = (column_name, tuple(column_type.enums), SUBPARTITION_KEY[table.name])
    return result


def monthly_partition_parents() -> dict[str, str]:
    """Relation that directly owns monthly children -> the top-level table.

    ``{"audit_logs": "audit_logs", ..., "candles_1m": "candles", ...}``. The
    value is what decides tenancy — and therefore whether a child needs its own
    RLS — because an intermediate LIST partition carries the parent's columns.
    """
    parents: dict[str, str] = {table: table for table in partitioned_tables()}
    for table, (_column, labels, _sub_key) in list_partitioned_tables().items():
        for label in labels:
            parents[list_partition_name(table, label)] = table
    return parents


__all__ = [
    "APP_ROLE",
    "AUDIT_SYSTEM_POLICY",
    "ORG_MATCH",
    "ORG_SETTING",
    "SUBPARTITION_KEY",
    "TENANT_POLICY",
    "WORKER_ROLE",
    "Agent",
    "AgentSignal",
    "AgentStats",
    "AlertRule",
    "Anomaly",
    "ApiKey",
    "Asset",
    "AuditLog",
    "Backtest",
    "BacktestResult",
    "BacktestTrade",
    "Base",
    "Candle",
    "Exchange",
    "ExchangeConnection",
    "FeatureDefinition",
    "FeatureFlag",
    "FeatureSnapshot",
    "Fill",
    "FundingRate",
    "IngestionGap",
    "IntelligenceEvent",
    "IntelligenceSource",
    "KillSwitchTransition",
    "Liquidation",
    "Market",
    "MarketRegimeRow",
    "MarketSnapshot",
    "Notification",
    "OpenInterestHistory",
    "Opportunity",
    "OpportunityHistory",
    "OpportunityWeights",
    "Order",
    "Organization",
    "OrganizationFeatureOverride",
    "OrganizationInvitation",
    "OrganizationMember",
    "PlanEntitlement",
    "Portfolio",
    "PortfolioEquitySnapshot",
    "Position",
    "ProcessedEvent",
    "RiskEvent",
    "RiskProfile",
    "ShadowEpisode",
    "ShadowOutbox",
    "SignalOutcome",
    "Strategy",
    "StrategyVersion",
    "Subscription",
    "SystemEvent",
    "Trade",
    "TradeProposal",
    "User",
    "WorkerHeartbeat",
    "Workspace",
    "create_list_partition_sql",
    "create_partition_sql",
    "detach_partition_sql",
    "drop_partition_sql",
    "harden_partition_sql",
    "list_partition_name",
    "list_partitioned_tables",
    "month_bounds",
    "monthly_partition_parents",
    "months_before",
    "months_from",
    "partition_name",
    "partitioned_tables",
    "tenant_tables",
]
