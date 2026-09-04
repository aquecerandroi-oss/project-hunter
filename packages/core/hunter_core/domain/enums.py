"""Every enum defined in docs/DATABASE.md (plus docs/RISK_ENGINE.md §5-6, which
DATABASE.md references without spelling out values), as ``StrEnum``.

Member values are exactly as the docs spell them. Two casing families exist in
the docs themselves and are preserved on purpose:

- Enums given as an explicit ``name = A, B, C`` assignment (org_role,
  plan_tier, kill_switch_state, opportunity_status) or as backtick lists
  (anomaly_type, market_regime) are UPPER_SNAKE_CASE.
- Enums shown inline as ``column type (a|b|c)`` are lower_snake_case.

``ALL_ENUMS`` maps each Postgres enum type name (as named in DATABASE.md) to
its Python class, for a later test that keeps this module in sync with the
actual database enums created in T04.

A few DB columns are typed as an enum in DATABASE.md but the doc never spells
out their members (``market_status``, ``exchange_status``,
``subscription_status``, ``feature_category``). Those are marked INFERRED
below with the reasoning; T04 (database-architect) must confirm or correct
before the migration is written — see the T03 report's CONCERNS section.
"""

from __future__ import annotations

from enum import StrEnum


class OrganizationRole(StrEnum):
    """``org_role`` — DATABASE.md §2."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class Plan(StrEnum):
    """``plan_tier`` — DATABASE.md §2."""

    FREE = "FREE"
    PRO = "PRO"
    QUANT = "QUANT"
    ENTERPRISE = "ENTERPRISE"


class KillSwitchState(StrEnum):
    """``kill_switch_state`` — DATABASE.md §2, RISK_ENGINE.md §5. Ordered least to
    most restrictive: ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY.
    """

    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    TRADING_DISABLED = "TRADING_DISABLED"
    EMERGENCY = "EMERGENCY"


class MemberStatus(StrEnum):
    """``member_status`` — DATABASE.md §2 (organization_members.status)."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class WorkspaceObjective(StrEnum):
    """``workspace_objective`` — DATABASE.md §2 (workspaces.objective)."""

    EXPLORE = "explore"
    PAPER_TRADING = "paper_trading"
    RESEARCH = "research"
    AUTOMATED_TRADING = "automated_trading"


class SubscriptionStatus(StrEnum):
    """``subscription_status`` — DATABASE.md §2 (subscriptions.status).

    INFERRED: the doc types the column but never lists members. Modeled after
    the standard Stripe subscription lifecycle since ``ENABLE_STRIPE`` and
    ``subscriptions.provider`` (null|stripe) are the only hints. Confirm with
    database-architect before the migration.
    """

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class ExchangeStatus(StrEnum):
    """``exchange_status`` — DATABASE.md §3 (exchanges.status).

    INFERRED: no members listed in the doc; minimal lifecycle. Confirm with
    database-architect before the migration.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


class MarketType(StrEnum):
    """``market_type`` — DATABASE.md §3 (markets.market_type)."""

    SPOT = "spot"
    PERPETUAL = "perpetual"


class MarketStatus(StrEnum):
    """``market_status`` — DATABASE.md §3 (markets.status).

    INFERRED: no members listed in the doc; ``markets.delisted_at`` implies at
    least ACTIVE/DELISTED. Confirm with database-architect before the migration.
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"


class Timeframe(StrEnum):
    """``candle_timeframe`` — DATABASE.md §4 (candles.timeframe)."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class OrderSide(StrEnum):
    """``order_side`` — DATABASE.md §4 (liquidations.side) and §7 (orders.side)."""

    BUY = "buy"
    SELL = "sell"


class FeatureCategory(StrEnum):
    """``feature_category`` — DATABASE.md §5 (feature_definitions.category).

    INFERRED: no members listed in the doc; mapped 1:1 from the feature
    groups in PIPELINE.md §2 (Preço, Volume, Volatilidade, Microestrutura,
    Momentum, Derivativos, Cross). Confirm with database-architect.
    """

    PRICE = "price"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    MICROSTRUCTURE = "microstructure"
    MOMENTUM = "momentum"
    DERIVATIVES = "derivatives"
    CROSS = "cross"


class AnomalyType(StrEnum):
    """``anomaly_type`` — DATABASE.md §5, PIPELINE.md §3. MVP (v1) plus the two
    Phase 2/3 types the pipeline doc already names.
    """

    VOLUME_SPIKE = "VOLUME_SPIKE"
    PRICE_ACCELERATION = "PRICE_ACCELERATION"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    ORDERBOOK_IMBALANCE = "ORDERBOOK_IMBALANCE"
    OPEN_INTEREST_SPIKE = "OPEN_INTEREST_SPIKE"
    FUNDING_ANOMALY = "FUNDING_ANOMALY"
    LIQUIDATION_CLUSTER = "LIQUIDATION_CLUSTER"
    CROSS_EXCHANGE_DIVERGENCE = "CROSS_EXCHANGE_DIVERGENCE"
    SOCIAL_SPIKE = "SOCIAL_SPIKE"
    WHALE_ACTIVITY = "WHALE_ACTIVITY"


class AnomalyStatus(StrEnum):
    """``anomaly_status`` — DATABASE.md §5 (anomalies.status)."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class RegimeScope(StrEnum):
    """``regime_scope`` — DATABASE.md §5 (market_regimes.scope)."""

    GLOBAL = "global"
    BTC = "btc"


class MarketRegime(StrEnum):
    """``market_regime`` — DATABASE.md §5, PIPELINE.md §4. v0 (M2) plus the v1
    (Phase 2) values the pipeline doc already names.
    """

    BTC_BULL = "BTC_BULL"
    BTC_BEAR = "BTC_BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    ALT_EXPANSION = "ALT_EXPANSION"
    PANIC = "PANIC"
    LIQUIDITY_CONTRACTION = "LIQUIDITY_CONTRACTION"


class TradeDirection(StrEnum):
    """``trade_direction`` — DATABASE.md §5 (opportunities.direction) and §6
    (agent_signals.direction, agents.allowed_directions).
    """

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


SignalDirection = TradeDirection
"""``agent_signals.direction`` reuses the ``trade_direction`` Postgres enum; this
alias is exported under the name used for signals, per the T03 brief. It is
intentionally NOT a second entry in ``ALL_ENUMS`` — there is only one DB type.
"""


class OpportunityStatus(StrEnum):
    """``opportunity_status`` — DATABASE.md §5. ``IN_POSITION`` and
    ``BLOCKED_BY_RISK`` are deliberately excluded: the doc states they are
    derived per-organization at read time and are never stored in this column.
    """

    NORMAL = "NORMAL"
    WATCHING = "WATCHING"
    ANOMALY = "ANOMALY"
    HOT = "HOT"
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    EXPIRED = "EXPIRED"


class StrategyVersionStatus(StrEnum):
    """``strategy_version_status`` — DATABASE.md §6 (strategy_versions.status)."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SignalStatus(StrEnum):
    """``signal_status`` — DATABASE.md §6 (agent_signals.status)."""

    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class OutcomeResult(StrEnum):
    """``outcome_result`` — DATABASE.md §6 (signal_outcomes.result)."""

    TARGET = "target"
    STOP = "stop"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    OPEN = "open"


class AgentStatus(StrEnum):
    """``agent_status`` — DATABASE.md §6 (agents.status)."""

    ENABLED = "enabled"
    PAUSED = "paused"
    DISABLED = "disabled"


class StatsWindow(StrEnum):
    """``stats_window`` — DATABASE.md §6 (agent_stats.window)."""

    ALL = "all"
    D7 = "7d"
    D30 = "30d"
    D90 = "90d"


class RiskPreset(StrEnum):
    """``risk_preset`` — DATABASE.md §7 (risk_profiles.preset)."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class PortfolioType(StrEnum):
    """``portfolio_type`` — DATABASE.md §7 (portfolios.type)."""

    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class PortfolioStatus(StrEnum):
    """``portfolio_status`` — DATABASE.md §7 (portfolios.status)."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProposalStatus(StrEnum):
    """``proposal_status`` — DATABASE.md §7 (trade_proposals.status)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"


class OrderType(StrEnum):
    """``order_type`` — DATABASE.md §7 (orders.type)."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"


class OrderPurpose(StrEnum):
    """``order_purpose`` — DATABASE.md §7 (orders.purpose)."""

    ENTRY = "entry"
    STOP = "stop"
    TARGET = "target"
    EXIT = "exit"
    REDUCE = "reduce"


class ExecutionMode(StrEnum):
    """``execution_mode`` — DATABASE.md §7 (orders.execution_mode)."""

    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class OrderStatus(StrEnum):
    """``order_status`` — DATABASE.md §7 (orders.status)."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionStatus(StrEnum):
    """``position_status`` — DATABASE.md §7 (positions.status)."""

    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class ExitReason(StrEnum):
    """``exit_reason`` — DATABASE.md §7 (trades.exit_reason)."""

    TARGET = "target"
    STOP = "stop"
    INVALIDATION = "invalidation"
    MANUAL = "manual"
    KILL_SWITCH = "kill_switch"
    EXPIRED = "expired"
    RISK_EVENT = "risk_event"


class RiskEventType(StrEnum):
    """``risk_event_type`` — DATABASE.md §7 (risk_events.type); members spelled
    out in RISK_ENGINE.md §6 (v1).
    """

    LIMITS_CHANGED = "limits_changed"
    PROPOSAL_REJECTED = "proposal_rejected"
    DAILY_LOSS_WARNING = "daily_loss_warning"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_LIMIT = "drawdown_limit"
    EXPOSURE_LIMIT = "exposure_limit"
    DATA_DEGRADED_IN_POSITION = "data_degraded_in_position"
    KILL_SWITCH_CHANGED = "kill_switch_changed"
    STOP_SLIPPAGE_EXCESS = "stop_slippage_excess"
    POSITION_STALE_PRICE = "position_stale_price"


class RiskEventSeverity(StrEnum):
    """``event_severity`` — DATABASE.md §7 (risk_events.severity) and §12
    (system_events.level) share this Postgres enum. RISK_ENGINE.md §6 notes
    risk events in practice only ever use info/warning/critical, but the
    column type (also used by system_events) has all five levels.
    """

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class KillSwitchScope(StrEnum):
    """``ks_scope`` — DATABASE.md §7 (kill_switch_transitions.scope)."""

    SYSTEM = "system"
    ORGANIZATION = "organization"
    PORTFOLIO = "portfolio"


class ConnectionStatus(StrEnum):
    """``connection_status`` — DATABASE.md §8 (exchange_connections.status)."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    REVOKED = "revoked"


class BacktestStatus(StrEnum):
    """``backtest_status`` — DATABASE.md §9 (backtests.status)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestWarningCode(StrEnum):
    """``backtest_results.warnings[].code`` — DATABASE.md §9."""

    OVERFITTING = "overfitting"
    LEAKAGE = "leakage"
    LOOKAHEAD = "lookahead"


class IntelligenceSourceKind(StrEnum):
    """``intelligence_sources.key`` — DATABASE.md §10. The doc gives one unique
    identifier per source; it doubles as the source's kind.
    """

    NEWS = "news"
    REDDIT = "reddit"
    X = "x"
    GOOGLE_TRENDS = "google_trends"
    ONCHAIN = "onchain"
    WHALES = "whales"
    LISTINGS = "listings"
    UNLOCKS = "unlocks"
    ANNOUNCEMENTS = "announcements"


class AlertChannel(StrEnum):
    """``notifications.channel`` — DATABASE.md §11."""

    IN_APP = "in_app"
    EMAIL = "email"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    PUSH = "push"


class NotificationStatus(StrEnum):
    """``notifications.status`` — DATABASE.md §11."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class WorkerHeartbeatStatus(StrEnum):
    """``worker_heartbeats.status`` — DATABASE.md §12."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    DOWN = "down"


ALL_ENUMS: dict[str, type[StrEnum]] = {
    "org_role": OrganizationRole,
    "plan_tier": Plan,
    "kill_switch_state": KillSwitchState,
    "member_status": MemberStatus,
    "workspace_objective": WorkspaceObjective,
    "subscription_status": SubscriptionStatus,
    "exchange_status": ExchangeStatus,
    "market_type": MarketType,
    "market_status": MarketStatus,
    "candle_timeframe": Timeframe,
    "order_side": OrderSide,
    "feature_category": FeatureCategory,
    "anomaly_type": AnomalyType,
    "anomaly_status": AnomalyStatus,
    "regime_scope": RegimeScope,
    "market_regime": MarketRegime,
    "trade_direction": TradeDirection,
    "opportunity_status": OpportunityStatus,
    "strategy_version_status": StrategyVersionStatus,
    "signal_status": SignalStatus,
    "outcome_result": OutcomeResult,
    "agent_status": AgentStatus,
    "stats_window": StatsWindow,
    "risk_preset": RiskPreset,
    "portfolio_type": PortfolioType,
    "portfolio_status": PortfolioStatus,
    "proposal_status": ProposalStatus,
    "order_type": OrderType,
    "order_purpose": OrderPurpose,
    "execution_mode": ExecutionMode,
    "order_status": OrderStatus,
    "position_status": PositionStatus,
    "exit_reason": ExitReason,
    "risk_event_type": RiskEventType,
    "event_severity": RiskEventSeverity,
    "ks_scope": KillSwitchScope,
    "connection_status": ConnectionStatus,
    "backtest_status": BacktestStatus,
    "backtest_warning_code": BacktestWarningCode,
    "intelligence_source_kind": IntelligenceSourceKind,
    "notification_channel": AlertChannel,
    "notification_status": NotificationStatus,
    "worker_heartbeat_status": WorkerHeartbeatStatus,
}
