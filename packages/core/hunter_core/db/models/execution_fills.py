"""``fills`` and ``positions`` — the execution outcome side of DATABASE.md §7.

Split out of ``execution.py`` by ``0006_paper_wallet`` for the reason
``analysis_baselines.py`` was split out of ``analysis.py``: the reservation, the
FIFO sequence and the composite identities grew the proposal and the order past
the 350-line budget (``infra/scripts/check_file_size.py``). The two tables are
unchanged except for what ``0006`` adds and documents here:

- ``fills.execution_key``, the per-tenant idempotency key of an execution, and
  the composite ``(order_id, organization_id, portfolio_id)`` foreign key that
  keeps a fill inside its order's organization *and* wallet;
- ``uq_positions_id_scope``, the target a durable exit intention points at with
  organization, wallet and market together.
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
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    JSONB_EMPTY,
    JSONB_EMPTY_LIST,
    SQL_FALSE,
    SQL_TRUE,
    org_fk,
    pg_enum,
    tenant_scoped_fk,
)
from hunter_core.domain.enums import LiquidityRole, PositionStatus, TradeDirection

_MARKET_FK = "markets.id"

_AGENT_SET_NULL = "SET NULL (agent_id)"
"""Only ``agent_id`` is nulled when an agent goes: ``organization_id`` is NOT NULL."""


class Fill(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One execution against an order. ``simulated`` is true for paper and shadow."""

    __tablename__ = "fills"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        # order -> fill, on the triple, preserving ``0001``'s ``CASCADE``: a fill
        # is part of its order and has no meaning without it.
        ForeignKeyConstraint(
            ["order_id", "organization_id", "portfolio_id"],
            ["orders.id", "orders.organization_id", "orders.portfolio_id"],
            ondelete="CASCADE",
        ),
        # Idempotency of *execution*, scoped per tenant for the same reason the
        # proposal's idempotency key is (§15.3): the key is minted by one
        # tenant's adapter, and a global unique would let tenant A's redelivery
        # be swallowed as a duplicate of tenant B's fill.
        UniqueConstraint("organization_id", "execution_key", name="uq_fills_execution_key"),
        # The target of the participation ledger's ``(fill_id, order_id)`` FK:
        # an execution entry has to name a fill *of the order it charges*.
        UniqueConstraint("id", "order_id", name="uq_fills_id_order"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("char_length(execution_key) > 0", name="execution_key_not_empty"),
        Index("ix_fills_org_portfolio_ts", "organization_id", "portfolio_id", "ts"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(index=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    execution_key: Mapped[str] = mapped_column(Text)
    """The adapter's key for *this execution*, stable across a retry. It is what
    makes a redelivered fill a no-op instead of a second one — the verification
    the directive asks for by name ("ordens simultâneas e fills duplicados")."""

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
        tenant_scoped_fk("portfolio_id", "portfolios"),
        tenant_scoped_fk("agent_id", "agents", ondelete=_AGENT_SET_NULL),
        # The target of the exit intention's composite FK — organization,
        # wallet *and* market, because an intention declares all three and each
        # of them, alone, would be satisfied by the wrong position.
        UniqueConstraint(
            "id", "organization_id", "portfolio_id", "market_id", name="uq_positions_id_scope"
        ),
        # a closing position legitimately reaches 0 before it becomes a trade
        CheckConstraint("qty >= 0", name="qty_non_negative"),
        CheckConstraint("avg_entry_price > 0", name="avg_entry_price_positive"),
        # ``0009_paper_geometry`` (§21.1): dust is a *closing* position and never
        # an open one. An ``open`` row claiming to be residual would be a
        # position the wallet believes it holds and no reader counts — the worst
        # of both; a ``closed`` one holds nothing, so it has no dust to declare.
        CheckConstraint(
            "NOT is_residual OR status = 'closing'", name="residual_is_a_closing_position"
        ),
        Index("ix_positions_org_portfolio_status", "organization_id", "portfolio_id", "status"),
        Index("ix_positions_market_status", "market_id", "status"),
        # The "live positions" question every reader of slots, exposure and
        # duplicate-market refusal actually asks, now that dust is none of the
        # three. Leads with ``organization_id`` because §1 requires it of every
        # composite index on a tenant table; Alembic never compares an index
        # *predicate* (§17.3), so ``test_schema_paper.py`` reads
        # ``pg_indexes.indexdef`` rather than trusting ``alembic check``.
        Index(
            "ix_positions_org_portfolio_live",
            "organization_id",
            "portfolio_id",
            postgresql_where=text("status <> 'closed' AND NOT is_residual"),
        ),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
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
    is_residual: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    """The leftover is dust: below the venue's minimum, unsellable at any price.

    A spot buy pays its fee in the coin, so the sellable quantity is almost never
    a multiple of ``step_size`` and a few ten-thousandths stay behind. They are
    **not a position**: they hold no slot, count as no exposure and make no
    market a duplicate — and they stay **visible and valued** at the mark, never
    zeroed as if they had been sold (``review-T3.5.md`` item 3, RISK_ENGINE.md
    §10). Before this column the same row was ``closing`` with ``qty > 0``, which
    every reader of live positions counted: a slot held for ever, four hours
    after the stop, and the next order in that coin refused as a duplicate.

    It is a *state of the leftover*, not a second lifecycle: the position is
    still ``closing`` (the CHECK says so) and settles when the accumulated dust
    of the coin reaches ``min_qty`` and a later exit carries it out."""

    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)
