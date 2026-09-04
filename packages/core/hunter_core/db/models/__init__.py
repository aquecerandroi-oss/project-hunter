"""Every ORM model. Importing this package populates ``Base.metadata`` in full —
Alembic's ``env.py``, the seed script and the partition script all rely on that.

Two helpers derive schema policy from the metadata itself instead of repeating a
hand-kept list: :func:`tenant_tables` (every table with ``organization_id``, i.e.
every table that needs Row Level Security, DATABASE.md §1.1/§1.2) and
:func:`partitioned_tables` (every RANGE-partitioned parent and its partition key,
§1.3).
"""

from __future__ import annotations

from hunter_core.db.base import Base
from hunter_core.db.models._partitions import (
    create_partition_sql,
    drop_partition_sql,
    month_bounds,
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


def partitioned_tables() -> dict[str, str]:
    """Partitioned parent table -> partition key column (``RANGE (<col>)``)."""
    result: dict[str, str] = {}
    for table in Base.metadata.sorted_tables:
        spec = table.kwargs.get("postgresql_partition_by")
        if isinstance(spec, str) and spec.upper().startswith("RANGE"):
            result[table.name] = spec.split("(", 1)[1].rsplit(")", 1)[0].strip()
    return result


__all__ = [
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
    "create_partition_sql",
    "drop_partition_sql",
    "month_bounds",
    "months_from",
    "partition_name",
    "partitioned_tables",
    "tenant_tables",
]
