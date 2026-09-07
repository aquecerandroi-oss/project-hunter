"""``orders`` — the attempt, and everything it has to agree with — DATABASE.md §7/§18.3.

Split out of ``execution.py`` for the reason ``execution_fills.py`` and
``execution_trades.py`` were (``infra/scripts/check_file_size.py``, 350 lines):
the T3.1b security review gave the order two more composite foreign keys and a
CHECK, and the proposal next to it is already the longest model in the package.
``execution.py`` **re-exports** ``Order``, so
``from hunter_core.db.models.execution import Order`` keeps working — a module
split that breaks an import is a refactor that broke something (§18.10).

What the review changed here, all of it must-fix 4: ``position_id`` names the
position by its full ``(id, organization_id, portfolio_id, market_id)`` scope
instead of by a bare id any organization's row satisfies, and the durable exit
intention this attempt serves has to be an intention *of that same position*.
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    JSONB_EMPTY,
    SQL_FALSE,
    org_fk,
    pg_enum,
    tenant_scoped_fk,
)
from hunter_core.domain.enums import (
    ExecutionMode,
    OrderPurpose,
    OrderSide,
    OrderStatus,
    OrderType,
)

_MARKET_FK = "markets.id"

_AGENT_SET_NULL = "SET NULL (agent_id)"
"""Only ``agent_id`` is nulled when an agent goes: ``organization_id`` is NOT NULL."""


class Order(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """An order in any execution mode. ``client_order_id`` is unique per portfolio."""

    __tablename__ = "orders"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        tenant_scoped_fk("agent_id", "agents", ondelete=_AGENT_SET_NULL),
        # proposal -> order, on organization, wallet *and market*. A
        # single-column FK is satisfied by a proposal of any organization, any
        # wallet and any market, and RLS only ever reads the row's own
        # ``organization_id``, so nothing catches the mismatch. The market is in
        # the key because an order placed in a market the decision never
        # evaluated is an unpriced entry wearing an approval.
        # ``SET NULL`` names the column (Postgres 15+) because a bare one would
        # also null ``organization_id`` and ``portfolio_id``, both NOT NULL —
        # the §15.4 precedent, and the action ``0001`` already used here.
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
        # order -> exit intent: which durable intention this attempt serves.
        ForeignKeyConstraint(
            ["exit_intent_id", "organization_id", "portfolio_id", "market_id"],
            [
                "portfolio_exit_intents.id",
                "portfolio_exit_intents.organization_id",
                "portfolio_exit_intents.portfolio_id",
                "portfolio_exit_intents.market_id",
            ],
            ondelete="SET NULL (exit_intent_id)",
        ),
        # order -> position, on the same quadruple. A single-column FK let
        # organization A's order name organization B's position: the FK was
        # satisfied and RLS only ever reads the row's own ``organization_id``
        # (security review, must-fix 4).
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
        # And the two have to agree. ``exit_intent_id`` and ``position_id`` were
        # independent: an attempt could name a real intention protecting position
        # X while declaring position Y, so the fill reduced one position and the
        # intention's ``filled_qty`` credited the other. Named by hand because the
        # convention would collide with the quadruple FK above.
        ForeignKeyConstraint(
            ["exit_intent_id", "position_id"],
            ["portfolio_exit_intents.id", "portfolio_exit_intents.position_id"],
            ondelete="SET NULL (exit_intent_id)",
            name="fk_orders_exit_intent_matches_position",
        ),
        UniqueConstraint("portfolio_id", "client_order_id", name="uq_orders_client_order_id"),
        # The target of the composite FK from ``fills`` (which has no market of
        # its own) and, with the market, of the participation ledger's.
        UniqueConstraint("id", "organization_id", "portfolio_id", name="uq_orders_id_scope"),
        UniqueConstraint(
            "id",
            "organization_id",
            "portfolio_id",
            "market_id",
            name="uq_orders_id_market_scope",
        ),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("price IS NULL OR price > 0", name="price_positive"),
        CheckConstraint("stop_price IS NULL OR stop_price > 0", name="stop_price_positive"),
        CheckConstraint("filled_qty >= 0 AND filled_qty <= qty", name="filled_qty_within_qty"),
        # An entry is one attempt and is never part of a protection.
        CheckConstraint(
            "purpose <> 'entry' OR exit_intent_id IS NULL", name="an_entry_serves_no_exit_intent"
        ),
        # A composite FK is MATCH SIMPLE: with ``position_id`` null it is not
        # checked at all, so this is what makes the pair FK above bite. An attempt
        # at a durable protection always knows which position it is protecting.
        CheckConstraint(
            "exit_intent_id IS NULL OR position_id IS NOT NULL",
            name="an_exit_attempt_names_its_position",
        ),
        Index("ix_orders_org_portfolio_created", "organization_id", "portfolio_id", "created_at"),
        Index("ix_orders_status", "status"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    exit_intent_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    """The intention this attempt is for. Null for entries and for anything not
    driven by a durable protection. Each attempt keeps its own identity, so a
    second attempt at the same intention is a second order, never a rewrite of
    the first (RISK_ENGINE.md §10)."""

    agent_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="RESTRICT"), index=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
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
