"""Risk profiles, portfolios and equity curve — DATABASE.md §7.

``risk_profiles.organization_id`` is nullable on purpose: ``NULL`` marks the
system presets seeded by ``infra/scripts/seed.py`` (RISK_ENGINE.md §2), which
every organization can read and copy. The migration therefore adds a second,
SELECT-only policy for those rows on top of ``tenant_isolation``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, PERCENT, SQL_FALSE, org_fk, pg_enum
from hunter_core.domain.enums import (
    KillSwitchState,
    PortfolioStatus,
    PortfolioType,
    RiskPreset,
    Timeframe,
)


class RiskProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named set of risk limits. ``organization_id IS NULL`` = system preset."""

    __tablename__ = "risk_profiles"
    __table_args__ = (
        org_fk(),
        Index("ix_risk_profiles_org_preset", "organization_id", "preset"),
        # one system preset per name, so infra/scripts/seed.py can upsert on it
        Index(
            "uq_risk_profiles_system_preset",
            "preset",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID | None]
    name: Mapped[str] = mapped_column(Text)
    preset: Mapped[RiskPreset] = mapped_column(
        pg_enum("risk_preset"), server_default=RiskPreset.BALANCED.value
    )
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class Portfolio(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """The money container. ``type`` is paper/shadow/live; live stays disabled
    until Phase 4 (``LiveExecutionAdapter`` raises ``LiveTradingDisabled``).
    """

    __tablename__ = "portfolios"
    __table_args__ = (
        org_fk(),
        Index("ix_portfolios_org_type_status", "organization_id", "type", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[PortfolioType] = mapped_column(
        pg_enum("portfolio_type"), server_default=PortfolioType.PAPER.value
    )
    base_currency: Mapped[str] = mapped_column(Text, server_default="USDT")
    initial_capital: Mapped[Decimal]
    risk_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_profiles.id", ondelete="RESTRICT"), index=True
    )
    exchange_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exchange_connections.id", ondelete="SET NULL"), index=True
    )
    execution_config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    status: Mapped[PortfolioStatus] = mapped_column(
        pg_enum("portfolio_status"), server_default=PortfolioStatus.ACTIVE.value
    )
    kill_switch_state: Mapped[KillSwitchState] = mapped_column(
        pg_enum("kill_switch_state"), server_default=KillSwitchState.ACTIVE.value
    )
    kill_switch_reason: Mapped[str | None] = mapped_column(Text)
    is_arena: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    deleted_at: Mapped[datetime | None]


class PortfolioEquitySnapshot(Base):
    """The equity curve. PK ``(portfolio_id, resolution, ts)``, partitioned on ``ts``."""

    __tablename__ = "portfolio_equity_snapshots"
    __table_args__ = {"postgresql_partition_by": "RANGE (ts)"}

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True
    )
    resolution: Mapped[Timeframe] = mapped_column(pg_enum("candle_timeframe"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(primary_key=True)
    cash: Mapped[Decimal]
    equity: Mapped[Decimal]
    exposure_notional: Mapped[Decimal]
    exposure_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    unrealized_pnl: Mapped[Decimal]
    realized_pnl_cum: Mapped[Decimal]
    peak_equity: Mapped[Decimal]
    drawdown_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    open_positions: Mapped[int] = mapped_column(Integer, server_default="0")
