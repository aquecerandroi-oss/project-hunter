"""Strategies, signals and agents — DATABASE.md §6.

``strategies``, ``strategy_versions``, ``agent_signals`` and ``signal_outcomes``
are global: a signal is produced once per ``strategy_version`` and read by every
organization. ``agents`` and ``agent_stats`` are tenant tables — an agent is an
instance of a strategy version inside one portfolio.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    CONFIDENCE,
    JSONB_EMPTY,
    JSONB_EMPTY_LIST,
    PERCENT,
    SCORE,
    SQL_FALSE,
    org_fk,
    pg_enum,
    tenant_scoped_fk,
)
from hunter_core.domain.enums import (
    AgentStatus,
    OutcomeResult,
    ShadowTrackingState,
    SignalStatus,
    StatsWindow,
    StrategyVersionStatus,
    TradeDirection,
)

_DIRECTION_ARRAY: ARRAY[Any] = ARRAY(pg_enum("trade_direction"))
"""``trade_direction[]`` for ``agents.allowed_directions``."""


class Strategy(Base, UUIDPrimaryKeyMixin):
    """The global strategy catalogue (momentum, breakout, ...)."""

    __tablename__ = "strategies"

    key: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StrategyVersion(Base, UUIDPrimaryKeyMixin):
    """A frozen, code-referenced version of a strategy. Replaces `agent_versions`."""

    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version"),)

    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(Text)
    status: Mapped[StrategyVersionStatus] = mapped_column(
        pg_enum("strategy_version_status"), server_default=StrategyVersionStatus.DRAFT.value
    )
    parameters_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    default_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    code_ref: Mapped[str | None] = mapped_column(Text)
    params_format: Mapped[int] = mapped_column(Integer, server_default="1")
    """Which canonical serialisation ``params_hash`` was computed with.

    ``hunter_core.strategies.canonical`` owns format 1. It is part of what the
    first activation freezes: rehashing an active version under a new format
    would silently split one experiment in two (SHADOW-LAB.md §1).
    """

    changelog: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    activated_at: Mapped[datetime | None]
    deprecated_at: Mapped[datetime | None]


class AgentSignal(Base, UUIDPrimaryKeyMixin):
    """A proposal-grade signal. Never an order: AGENT -> PROPOSAL -> RISK -> EXECUTION."""

    __tablename__ = "agent_signals"
    __table_args__ = (
        # the target of shadow_episodes' composite FK: an episode may only hold a
        # signal of its own strategy version and market (0002_shadow_lab)
        UniqueConstraint("id", "strategy_version_id", "market_id", name="uq_agent_signals_id_slot"),
        Index("ix_agent_signals_market_emitted", "market_id", "emitted_at"),
        Index("ix_agent_signals_version_emitted", "strategy_version_id", "emitted_at"),
        Index("ix_agent_signals_status_expires", "status", "expires_at"),
    )

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE")
    )
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"))
    params_hash: Mapped[str] = mapped_column(Text)
    direction: Mapped[TradeDirection] = mapped_column(pg_enum("trade_direction"))
    confidence: Mapped[Decimal] = mapped_column(CONFIDENCE)
    entry_zone: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    stop: Mapped[Decimal | None]
    targets: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    invalidations: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    expected_holding_s: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    supporting_features: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    regime_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("market_regimes.id", ondelete="SET NULL"), index=True
    )
    emitted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime | None]
    status: Mapped[SignalStatus] = mapped_column(
        pg_enum("signal_status"), server_default=SignalStatus.ACTIVE.value
    )


class SignalOutcome(Base):
    """System shadow, 1:1 with a signal — the evidence behind "shadow performance"."""

    __tablename__ = "signal_outcomes"
    __table_args__ = (
        CheckConstraint(
            "(tracking_state = 'no_entry') = (no_entry_reason IS NOT NULL) "
            "AND (tracking_state = 'censored') = (censored_reason IS NOT NULL) "
            "AND (no_entry_reason IS NULL OR char_length(no_entry_reason) BETWEEN 1 AND 64) "
            "AND (censored_reason IS NULL OR char_length(censored_reason) BETWEEN 1 AND 64)",
            name="no_entry_and_censored_reasons",
        ),
        CheckConstraint(
            "(result = 'open') = (tracking_state <> 'terminal')",
            name="tracking_state_matches_result",
        ),
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_signals.id", ondelete="CASCADE"), primary_key=True
    )
    virtual_entry: Mapped[Decimal | None]
    virtual_stop: Mapped[Decimal | None]
    virtual_targets: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    entry_ts: Mapped[datetime | None]
    mfe: Mapped[Decimal | None]
    mae: Mapped[Decimal | None]
    mfe_ts: Mapped[datetime | None]
    mae_ts: Mapped[datetime | None]
    result: Mapped[OutcomeResult] = mapped_column(
        pg_enum("outcome_result"), server_default=OutcomeResult.OPEN.value
    )
    exit_price: Mapped[Decimal | None]
    exit_ts: Mapped[datetime | None]
    r_multiple: Mapped[Decimal | None]
    tracked_until: Mapped[datetime | None]
    tracking_state: Mapped[ShadowTrackingState] = mapped_column(
        pg_enum("shadow_tracking_state"), server_default=ShadowTrackingState.PENDING_ENTRY.value
    )
    """Where the *tracking* is, independently of ``result`` (SHADOW-LAB.md §4).

    ``result`` is the financial outcome and ``OutcomeResult`` has no member for
    "unknown", so a ``no_entry`` or ``censored`` row keeps ``result = 'open'``
    and this column is what says it is not open. The CHECK above states the
    invariant the other way round: ``terminal`` if and only if the result
    resolved.
    """

    no_entry_reason: Mapped[str | None] = mapped_column(Text)
    """Why no entry happened (``late``, ``geometry``) — never null when
    ``tracking_state = 'no_entry'``, always null otherwise."""

    censored_reason: Mapped[str | None] = mapped_column(Text)
    """Why the outcome cannot be resolved (an unrecoverable bar). Censorship is
    never turned into ``expired``."""

    meta: Mapped[dict[str, Any]] = mapped_column("meta", JSONB, server_default=JSONB_EMPTY)
    """Excursion coverage and bounds, cost assumptions, funding availability —
    ``{unit, method, coverage, mfe_complete_bars, mae_complete_bars, bounds,
    bar_windows, ambiguous, initial_risk, reference_price}`` (SHADOW-LAB.md §5).
    The canonical ``mfe``/``mae`` columns stay NULL when the true extreme is
    undetermined; this is where the honest partial answer lives."""

    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Agent(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A strategy version running inside one portfolio, with its own limits."""

    __tablename__ = "agents"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        # the target of every (agent_id, organization_id) composite FK
        UniqueConstraint("id", "organization_id", name="uq_agents_id_org"),
        Index("ix_agents_org_portfolio_status", "organization_id", "portfolio_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(Text)
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"), index=True
    )
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    uses_custom_params: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    status: Mapped[AgentStatus] = mapped_column(
        pg_enum("agent_status"), server_default=AgentStatus.DISABLED.value
    )
    capital_allocation_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    max_open_positions: Mapped[int | None] = mapped_column(Integer)
    allowed_directions: Mapped[list[TradeDirection]] = mapped_column(
        _DIRECTION_ARRAY,
        server_default=text("'{long,short}'::trade_direction[]"),
    )
    market_filter: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    min_opportunity_score: Mapped[Decimal | None] = mapped_column(SCORE)
    min_confidence: Mapped[Decimal | None] = mapped_column(CONFIDENCE)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    deleted_at: Mapped[datetime | None]


class AgentStats(Base, TenantMixin):
    """Materialized by the analytics worker. PK ``(agent_id, window)``.

    A tenant table: these are one organization's realized statistics, so the
    review is right that leaving RLS to a join with ``agents`` in the repository
    was a single missing ``JOIN`` away from a cross-tenant read.
    """

    __tablename__ = "agent_stats"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("agent_id", "agents"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    window: Mapped[StatsWindow] = mapped_column(pg_enum("stats_window"), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    trades: Mapped[int] = mapped_column(Integer, server_default="0")
    wins: Mapped[int] = mapped_column(Integer, server_default="0")
    losses: Mapped[int] = mapped_column(Integer, server_default="0")
    win_rate: Mapped[Decimal | None] = mapped_column(PERCENT)
    profit_factor: Mapped[Decimal | None]
    expectancy: Mapped[Decimal | None]
    avg_win: Mapped[Decimal | None]
    avg_loss: Mapped[Decimal | None]
    sharpe: Mapped[Decimal | None]
    sortino: Mapped[Decimal | None]
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    pnl: Mapped[Decimal | None]
    pnl_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    by_regime: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    by_market: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    by_hour: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    by_volatility: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
