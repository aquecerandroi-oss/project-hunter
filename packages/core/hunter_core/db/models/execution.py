"""Proposals and orders — DATABASE.md §7 and §18.3 (tenant).

``trade_proposals`` is the PROPOSAL of AGENT -> PROPOSAL -> RISK ENGINE ->
EXECUTION: no entry order exists without a row here carrying
``risk_decision.approved = true`` (RISK_ENGINE.md §8). Exit orders are always
allowed and are the only ones that may reference a null proposal.

``0006_paper_wallet`` adds three things to this file and moves ``fills`` and
``positions`` to ``execution_fills.py`` and ``trades`` to
``execution_trades.py`` to stay inside the 350-line budget:

- the **reservation**, whose tenure is a different axis from the decision's
  label (``reservation_state`` next to ``status``), plus the durable ``fifo_v1``
  admission sequence;
- **composite identity** down the chain proposal -> order -> fill, so no row can
  claim one organization's wallet while pointing at another's parent;
- ``fills.execution_key``, the idempotency key that makes a redelivered
  execution a no-op rather than a second fill.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
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
    CONFIDENCE,
    JSONB_EMPTY,
    PERCENT,
    SCORE,
    SQL_FALSE,
    org_fk,
    pg_enum,
    tenant_scoped_fk,
)
from hunter_core.db.models.execution_fills import Fill, Position
from hunter_core.db.models.execution_trades import Trade
from hunter_core.domain.enums import (
    ExecutionMode,
    OrderPurpose,
    OrderSide,
    OrderStatus,
    OrderType,
    ProposalSource,
    ProposalStatus,
    ReservationState,
    TradeDirection,
)

__all__ = ["Fill", "Order", "Position", "Trade", "TradeProposal"]
"""``Fill``, ``Position`` and ``Trade`` are re-exported, not defined here.

The split above is a file-size measure, not a change of API:
``from hunter_core.db.models.execution import Position`` is a public path with
callers outside this package (``apps/api``), and a module split that breaks an
import is a refactor that broke something. Re-exporting keeps the old path
working while the classes live where they fit.
"""

_MARKET_FK = "markets.id"

_AGENT_SET_NULL = "SET NULL (agent_id)"
"""Only ``agent_id`` is nulled when an agent goes: ``organization_id`` is NOT NULL."""


class TradeProposal(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """The Risk Engine's decision record. ``risk_decision.checks[]`` is the
    Explanation Panel's source and is written even when the proposal is rejected.
    """

    __tablename__ = "trade_proposals"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        tenant_scoped_fk("agent_id", "agents", ondelete=_AGENT_SET_NULL),
        # scoped per organization: an idempotency key is minted by one tenant's
        # client, so a global unique lets tenant A's retry collide with — and be
        # silently swallowed as a duplicate of — tenant B's proposal.
        UniqueConstraint("organization_id", "idempotency_key", name="uq_trade_proposals_idem"),
        # The target of the composite FK from ``orders``: an order may not name a
        # proposal belonging to another organization or another wallet.
        UniqueConstraint(
            "id",
            "organization_id",
            "portfolio_id",
            "market_id",
            name="uq_trade_proposals_id_scope",
        ),
        # ``fifo_v1``: the wallet's admission order, assigned under the portfolio
        # lock from ``portfolio_risk_state.last_admission_seq``. Unique per
        # wallet, so a retry that recovers an existing proposal keeps its place
        # instead of taking a second one.
        UniqueConstraint(
            "organization_id",
            "portfolio_id",
            "admission_seq",
            name="uq_trade_proposals_admission_seq",
        ),
        Index(
            "ix_trade_proposals_org_portfolio_created",
            "organization_id",
            "portfolio_id",
            "created_at",
        ),
        Index("ix_trade_proposals_status_expires", "status", "expires_at"),
        # The expiry sweep, which competes for the same portfolio lock.
        Index(
            "ix_trade_proposals_reservation_expiry",
            "organization_id",
            "portfolio_id",
            "reserved_until",
            postgresql_where=text("reservation_state = 'held'"),
        ),
        # Quantified exactly when there is a reservation — stated as two
        # implications rather than one biconditional so that ``consumed``,
        # ``released`` and ``expired`` keep the *original* amounts as history.
        # What counts against a limit is gated by the state, never by the
        # columns going null.
        CheckConstraint(
            "reservation_state = 'none' OR (reserved_notional IS NOT NULL "
            "AND reserved_cash IS NOT NULL AND reserved_risk IS NOT NULL "
            "AND reserved_until IS NOT NULL)",
            name="a_reservation_is_quantified",
        ),
        CheckConstraint(
            "reservation_state <> 'none' OR (reserved_notional IS NULL "
            "AND reserved_cash IS NULL AND reserved_risk IS NULL "
            "AND reserved_until IS NULL)",
            name="an_unreserved_proposal_holds_nothing",
        ),
        # A slot only exists while the reservation is in force: the fill
        # *converts* the reserved slot into the position's slot, and a converted
        # reservation that kept counting would be two slots for one entry.
        CheckConstraint(
            "NOT reserved_slot OR reservation_state = 'held'", name="a_slot_is_held_or_gone"
        ),
        CheckConstraint(
            "(reserved_notional IS NULL OR reserved_notional > 0) "
            "AND (reserved_cash IS NULL OR reserved_cash > 0) "
            "AND (reserved_risk IS NULL OR reserved_risk >= 0)",
            name="reserved_amounts_are_sane",
        ),
        CheckConstraint(
            "admission_seq IS NULL OR admission_seq > 0", name="admission_seq_positive"
        ),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
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
    source: Mapped[ProposalSource] = mapped_column(
        pg_enum("proposal_source"), server_default=ProposalSource.MANUAL.value
    )
    """Which admission path this came in through — not who asked, which is
    ``agent_id`` plus the audit actor. ``MANUAL`` is the only live origin in M3."""

    admission_seq: Mapped[int | None] = mapped_column(BigInteger)
    """``fifo_v1``. Null until admitted; assigned once, under the portfolio lock."""

    reservation_state: Mapped[ReservationState] = mapped_column(
        pg_enum("reservation_state"), server_default=ReservationState.NONE.value
    )
    """The reservation's tenure, separate from ``status``, the decision's label.
    ``status`` records what the Risk Engine decided and never stops being true;
    this records whether the commitment is still standing."""

    reserved_notional: Mapped[Decimal | None]
    """What the entry commits to exposure and to the participation budget."""

    reserved_cash: Mapped[Decimal | None]
    """What it commits to *cash*, fees included — a separate number on purpose.
    With 100 of cash, a notional reservation of 100 and an estimated fee of 0,10,
    a single column passes every check and the purchase still needs 100,10;
    folding the fee into the notional would instead distort exposure and
    participation (Astra's counter-example)."""

    reserved_risk: Mapped[Decimal | None]
    """Planned loss at the stop, costs included, in the operating currency and
    **not** as a fraction: the aggregate ceiling is a percentage of an equity
    that moves, while the commitment already made is an amount. The aggregate is
    a sum of per-position non-negative risks — never ``max(0, Σ signed)``, which
    would let a −80 and a +100 net to a commitment of 20."""

    reserved_slot: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    reserved_until: Mapped[datetime | None]
    """The reservation's own validity, distinct from ``expires_at``, the
    proposal's. Expiry competes for the same lock as admission."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    decided_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]


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
