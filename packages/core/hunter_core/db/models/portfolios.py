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

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    JSONB_EMPTY,
    PERCENT,
    SQL_FALSE,
    org_fk,
    pg_enum,
    tenant_scoped_fk,
)
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
        # the target of every (portfolio_id, organization_id) composite FK
        UniqueConstraint("id", "organization_id", name="uq_portfolios_id_org"),
        CheckConstraint("initial_capital >= 0", name="initial_capital_non_negative"),
        Index("ix_portfolios_org_type_status", "organization_id", "type", "status"),
        # **One principal paper wallet per organization, for ever.**
        # RISK_ENGINE.md §11 and the M3 joint decision, item 2 (D7: "uma carteira
        # principal"). The predicate is exactly ``type = 'paper' AND NOT
        # is_arena`` and deliberately does *not* mention ``status`` and does
        # *not* exclude ``deleted_at IS NOT NULL``: archiving or soft-deleting
        # the wallet and opening another one would preserve the old rows and
        # still restart the equity and the peak, and would release a
        # TRADING_DISABLED kill switch nobody authorised — the same substitution
        # the directive forbids when it forbids a reset.
        #
        # **The key is the organization, not (organization, workspace)** —
        # security review of ``0006``, blocking 2. Per pair, the index stopped
        # nothing that mattered: ``hunter_app`` creates a workspace and opens a
        # second principal wallet inside it with a fresh R$100.000, no ``DELETE``
        # and no audit entry (reproduced). Workspaces are a user-facing grouping,
        # so anything keyed on them is a permanence guarantee a UI button can
        # dissolve. Several principal wallets, if they are ever wanted, are an
        # audited OWNER act and a migration, not a side effect.
        Index(
            "uq_portfolios_principal_paper",
            "organization_id",
            unique=True,
            postgresql_where=text("type = 'paper' AND NOT is_arena"),
        ),
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


class PortfolioEquitySnapshot(Base, TenantMixin):
    """The equity curve. PK ``(portfolio_id, resolution, ts)``.

    ``LIST (resolution)`` then ``RANGE (ts)`` per resolution, so the 1m curve can
    be dropped at 30 days while the 1h curve is kept forever (DATABASE.md §1.3)
    — a single monthly RANGE could only expire both at once.

    It is a tenant table: it holds one organization's equity, so it carries
    ``organization_id`` and is policed by RLS like everything else that is money
    (the review found it readable across tenants through the missing column).
    """

    __tablename__ = "portfolio_equity_snapshots"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        # "The largest equity this wallet ever showed" — the ceiling
        # ``portfolio_risk_state_guard`` measures a rising peak and a new day
        # reference against (§18.7). The PK is ``(portfolio_id, resolution,
        # ts)``, which finds the wallet's rows but cannot answer ``max(equity)``
        # without reading them all; this makes it an index scan instead, on a
        # check that runs once per sampling interval per wallet. Declared on the
        # partitioned parent, so Postgres propagates it to every partition,
        # including the ones ``create_partitions.py`` adds later.
        Index("ix_portfolio_equity_snapshots_peak_lookup", "portfolio_id", "equity"),
        {"postgresql_partition_by": "LIST (resolution)"},
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
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
    fx_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fx_observations.id", ondelete="RESTRICT"), index=True
    )
    """The FX observation this point of the curve was converted with (§18.2).

    Every point names the rate it used, so the past is never recomputed with
    today's rate — the joint M3 decision, item 1. **Nullable on purpose**: when
    FX is unavailable after the wallet opened, USDT stays computable and BRL
    becomes *unavailable with a reason*, never extrapolated. ``RESTRICT``
    because the observation is the explanation for a stored number."""
