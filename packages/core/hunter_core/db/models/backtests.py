"""Backtests — DATABASE.md §9 (tenant; M6, schema in M0).

``backtest_results.warnings`` carries the overfitting/leakage/lookahead codes
(``backtest_warning_code``) as JSONB objects with a ``detail``, so a run is never
reported as clean when the engine detected a methodological problem.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    JSONB_EMPTY,
    JSONB_EMPTY_LIST,
    SCORE,
    UUID_ARRAY_EMPTY,
    org_fk,
    pg_enum,
)
from hunter_core.domain.enums import BacktestStatus, ExitReason, Timeframe, TradeDirection


class Backtest(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """A queued or finished backtest run."""

    __tablename__ = "backtests"
    __table_args__ = (
        org_fk(),
        Index("ix_backtests_org_created", "organization_id", "created_at"),
        Index("ix_backtests_status", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"), index=True
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    market_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default=UUID_ARRAY_EMPTY
    )
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum("candle_timeframe"))
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    initial_capital: Mapped[Decimal]
    risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_profiles.id", ondelete="SET NULL"), index=True
    )
    fee_model: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    slippage_model: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    status: Mapped[BacktestStatus] = mapped_column(
        pg_enum("backtest_status"), server_default=BacktestStatus.QUEUED.value
    )
    progress_pct: Mapped[Decimal] = mapped_column(SCORE, server_default="0")
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BacktestResult(Base, UUIDPrimaryKeyMixin):
    """Metrics for one segment (full, train, validation, oos, wf_1..n)."""

    __tablename__ = "backtest_results"
    __table_args__ = (UniqueConstraint("backtest_id", "segment"),)

    backtest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtests.id", ondelete="CASCADE"))
    segment: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    equity_curve: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    trades_count: Mapped[int] = mapped_column(Integer, server_default="0")


class BacktestTrade(Base, UUIDPrimaryKeyMixin):
    """A simulated trade of a backtest run."""

    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_backtest_trades_backtest_segment", "backtest_id", "segment"),)

    backtest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backtests.id", ondelete="CASCADE"))
    segment: Mapped[str] = mapped_column(Text)
    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("markets.id", ondelete="RESTRICT"), index=True
    )
    direction: Mapped[TradeDirection] = mapped_column(pg_enum("trade_direction"))
    entry_ts: Mapped[datetime]
    exit_ts: Mapped[datetime | None]
    entry_price: Mapped[Decimal]
    exit_price: Mapped[Decimal | None]
    qty: Mapped[Decimal]
    pnl: Mapped[Decimal | None]
    r_multiple: Mapped[Decimal | None]
    mfe: Mapped[Decimal | None]
    mae: Mapped[Decimal | None]
    exit_reason: Mapped[ExitReason | None] = mapped_column(pg_enum("exit_reason"))
