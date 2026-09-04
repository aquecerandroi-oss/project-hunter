"""Proposals, orders, fills, positions and trades — DATABASE.md §7 (tenant).

``trade_proposals`` is the PROPOSAL of AGENT -> PROPOSAL -> RISK ENGINE ->
EXECUTION: no entry order exists without a row here carrying
``risk_decision.approved = true`` (RISK_ENGINE.md §7). Exit orders are always
allowed and are the only ones that may reference a null proposal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    CONFIDENCE,
    JSONB_EMPTY,
    JSONB_EMPTY_LIST,
    PERCENT,
    SCORE,
    SQL_FALSE,
    SQL_TRUE,
    org_fk,
    pg_enum,
)
from hunter_core.domain.enums import (
    ExecutionMode,
    ExitReason,
    LiquidityRole,
    OrderPurpose,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    ProposalStatus,
    TradeDirection,
)

_PORTFOLIO_FK = "portfolios.id"
_MARKET_FK = "markets.id"
_AGENT_FK = "agents.id"


class TradeProposal(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """The Risk Engine's decision record. ``risk_decision.checks[]`` is the
    Explanation Panel's source and is written even when the proposal is rejected.
    """

    __tablename__ = "trade_proposals"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("idempotency_key"),
        Index(
            "ix_trade_proposals_org_portfolio_created",
            "organization_id",
            "portfolio_id",
            "created_at",
        ),
        Index("ix_trade_proposals_status_expires", "status", "expires_at"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_PORTFOLIO_FK, ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_AGENT_FK, ondelete="SET NULL"), index=True
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_signals.id", ondelete="SET NULL"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="RESTRICT"), index=True
    )
    direction: Mapped[TradeDirection] = mapped_column(pg_enum("trade_direction"))
    requested_risk_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    status: Mapped[ProposalStatus] = mapped_column(
        pg_enum("proposal_status"), server_default=ProposalStatus.PENDING.value
    )
    risk_decision: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    kill_switch_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    regime_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("market_regimes.id", ondelete="SET NULL"), index=True
    )
    opportunity_score: Mapped[Decimal | None] = mapped_column(SCORE)
    confidence: Mapped[Decimal | None] = mapped_column(CONFIDENCE)
    idempotency_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    decided_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]


class Order(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """An order in any execution mode. ``client_order_id`` is unique per portfolio."""

    __tablename__ = "orders"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("portfolio_id", "client_order_id", name="uq_orders_client_order_id"),
        Index("ix_orders_org_portfolio_created", "organization_id", "portfolio_id", "created_at"),
        Index("ix_orders_status", "status"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_PORTFOLIO_FK, ondelete="CASCADE"))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trade_proposals.id", ondelete="SET NULL"), index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_AGENT_FK, ondelete="SET NULL"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="RESTRICT"), index=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL"), index=True
    )
    client_order_id: Mapped[str] = mapped_column(Text)
    exchange_order_id: Mapped[str | None] = mapped_column(Text)
    side: Mapped[OrderSide] = mapped_column(pg_enum("order_side"))
    type: Mapped[OrderType] = mapped_column(pg_enum("order_type"))
    purpose: Mapped[OrderPurpose] = mapped_column(pg_enum("order_purpose"))
    qty: Mapped[Decimal]
    price: Mapped[Decimal | None]
    stop_price: Mapped[Decimal | None]
    time_in_force: Mapped[str | None] = mapped_column(Text)
    reduce_only: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        pg_enum("execution_mode"), server_default=ExecutionMode.PAPER.value
    )
    status: Mapped[OrderStatus] = mapped_column(
        pg_enum("order_status"), server_default=OrderStatus.PENDING.value
    )
    filled_qty: Mapped[Decimal] = mapped_column(server_default="0")
    avg_fill_price: Mapped[Decimal | None]
    fees_paid: Mapped[Decimal] = mapped_column(server_default="0")
    submitted_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    reason: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Fill(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One execution against an order. ``simulated`` is true for paper and shadow."""

    __tablename__ = "fills"
    __table_args__ = (
        org_fk(),
        Index("ix_fills_org_portfolio_ts", "organization_id", "portfolio_id", "ts"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_PORTFOLIO_FK, ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(server_default=func.now())
    qty: Mapped[Decimal]
    price: Mapped[Decimal]
    fee: Mapped[Decimal] = mapped_column(server_default="0")
    fee_asset: Mapped[str | None] = mapped_column(Text)
    liquidity: Mapped[LiquidityRole | None] = mapped_column(pg_enum("liquidity_role"))
    slippage_bps: Mapped[Decimal | None]
    simulated: Mapped[bool] = mapped_column(server_default=SQL_TRUE)
    book_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)


class Position(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """An open (or closing) exposure. Closed positions also produce a ``trades`` row."""

    __tablename__ = "positions"
    __table_args__ = (
        org_fk(),
        Index("ix_positions_org_portfolio_status", "organization_id", "portfolio_id", "status"),
        Index("ix_positions_market_status", "market_id", "status"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_PORTFOLIO_FK, ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(_AGENT_FK, ondelete="SET NULL"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="RESTRICT"))
    direction: Mapped[TradeDirection] = mapped_column(pg_enum("trade_direction"))
    qty: Mapped[Decimal]
    avg_entry_price: Mapped[Decimal]
    mark_price: Mapped[Decimal | None]
    notional: Mapped[Decimal | None]
    leverage: Mapped[Decimal | None]
    unrealized_pnl: Mapped[Decimal] = mapped_column(server_default="0")
    realized_pnl: Mapped[Decimal] = mapped_column(server_default="0")
    fees_paid: Mapped[Decimal] = mapped_column(server_default="0")
    stop_price: Mapped[Decimal | None]
    targets: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    trailing: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mfe: Mapped[Decimal | None]
    mae: Mapped[Decimal | None]
    status: Mapped[PositionStatus] = mapped_column(
        pg_enum("position_status"), server_default=PositionStatus.OPEN.value
    )
    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)


class Trade(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One row per closed position — the truth analytics reads."""

    __tablename__ = "trades"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("position_id"),
        Index("ix_trades_org_portfolio_closed", "organization_id", "portfolio_id", "closed_at"),
        Index("ix_trades_agent_closed", "agent_id", "closed_at"),
        Index("ix_trades_market_closed", "market_id", "closed_at"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_PORTFOLIO_FK, ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(_AGENT_FK, ondelete="SET NULL"))
    strategy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="RESTRICT"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL")
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_signals.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trade_proposals.id", ondelete="SET NULL"), index=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    execution_mode: Mapped[ExecutionMode] = mapped_column(pg_enum("execution_mode"))
    direction: Mapped[TradeDirection] = mapped_column(pg_enum("trade_direction"))
    entry_price: Mapped[Decimal]
    exit_price: Mapped[Decimal]
    qty: Mapped[Decimal]
    notional: Mapped[Decimal | None]
    fees: Mapped[Decimal] = mapped_column(server_default="0")
    slippage_cost: Mapped[Decimal] = mapped_column(server_default="0")
    pnl: Mapped[Decimal]
    pnl_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    r_multiple: Mapped[Decimal | None]
    duration_s: Mapped[int | None] = mapped_column(Integer)
    mfe: Mapped[Decimal | None]
    mae: Mapped[Decimal | None]
    regime_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("market_regimes.id", ondelete="SET NULL"), index=True
    )
    opportunity_score: Mapped[Decimal | None] = mapped_column(SCORE)
    confidence: Mapped[Decimal | None] = mapped_column(CONFIDENCE)
    entry_reason: Mapped[str | None] = mapped_column(Text)
    exit_reason: Mapped[ExitReason | None] = mapped_column(pg_enum("exit_reason"))
    entry_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    exit_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    opened_at: Mapped[datetime]
    closed_at: Mapped[datetime]
