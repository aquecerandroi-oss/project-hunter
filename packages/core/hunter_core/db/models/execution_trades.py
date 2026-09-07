"""``trades`` — one row per closed position, the truth analytics reads.

Split out of ``execution.py`` for the reason ``analysis_baselines.py`` was split
out of ``analysis.py``: ``0006_paper_wallet`` gives the proposal its reservation
and the order and fill their composite identities, and folding all of that in
next to ``trades`` pushed the module past the 350-line budget
(``infra/scripts/check_file_size.py``). Nothing about the table changed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    CONFIDENCE,
    JSONB_EMPTY,
    PERCENT,
    SCORE,
    org_fk,
    pg_enum,
    tenant_scoped_fk,
)
from hunter_core.domain.enums import ExecutionMode, ExitReason, TradeDirection

_MARKET_FK = "markets.id"

_AGENT_SET_NULL = "SET NULL (agent_id)"
"""Only ``agent_id`` is nulled when an agent goes: ``organization_id`` is NOT NULL."""


class Trade(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One row per closed position — the truth analytics reads."""

    __tablename__ = "trades"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        tenant_scoped_fk("agent_id", "agents", ondelete=_AGENT_SET_NULL),
        # Same correction as ``orders`` (security review, must-fix 4): the closed
        # position and the decision behind it are named by their full scope, not
        # by a bare id that any organization's row satisfies. ``trades`` is the
        # table analytics treats as the truth, so a row attributing another
        # tenant's position to this wallet is a number nobody can un-publish.
        ForeignKeyConstraint(
            ["position_id", "organization_id", "portfolio_id", "market_id"],
            [
                "positions.id",
                "positions.organization_id",
                "positions.portfolio_id",
                "positions.market_id",
            ],
            ondelete="SET NULL (position_id)",
        ),
        ForeignKeyConstraint(
            ["proposal_id", "organization_id", "portfolio_id", "market_id"],
            [
                "trade_proposals.id",
                "trade_proposals.organization_id",
                "trade_proposals.portfolio_id",
                "trade_proposals.market_id",
            ],
            ondelete="SET NULL (proposal_id)",
        ),
        UniqueConstraint("position_id"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("entry_price > 0", name="entry_price_positive"),
        CheckConstraint("exit_price > 0", name="exit_price_positive"),
        Index("ix_trades_org_portfolio_closed", "organization_id", "portfolio_id", "closed_at"),
        Index("ix_trades_agent_closed", "agent_id", "closed_at"),
        Index("ix_trades_market_closed", "market_id", "closed_at"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    agent_id: Mapped[uuid.UUID | None]
    strategy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL"), index=True
    )
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="RESTRICT"))
    position_id: Mapped[uuid.UUID | None]
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_signals.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
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
