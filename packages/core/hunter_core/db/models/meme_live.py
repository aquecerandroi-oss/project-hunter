"""The executor's ledger — real orders, real positions, the durable daily latch
(DATABASE.md §40, revision ``0028_meme_live``, T4.14).

**Global tables** (§1.1), the shape of ``meme_paper_bets``: an order signed
against an on-chain curve belongs to no organization. Written by
``hunter_worker`` (the meme-executor) only; ``hunter_app`` reads, and may set
exactly ``sell_requested_at``/``sell_requested_by`` on a position.

Three decisions live here rather than in prose:

- **A proposal has one buy, a signature has one order.** The partial unique
  indexes are the two idempotency keys of ``docs/RISK_ENGINE_MEME.md`` §9.4: a
  retried loop finds the row, a redelivered stream event finds the row, neither
  creates a second one. Every signature ever emitted for the row is kept in
  ``signatures``; ``tx_signature`` is the latest.
- **A state carries its evidence.** ``refused``/``failed`` ⟹ ``reason``;
  ``submitted_unconfirmed``/``confirmed`` ⟹ ``tx_signature``; ``confirmed`` ⟹
  ``fill`` (the decoded ``TradeEvent``, §9.6 — never the quote, never the
  request).
- **A position's exit is all-or-nothing, and its mark names its source.**
  ``exit_at``/``exit``/``pnl_sol``/``r_multiple`` null together or set
  together; ``mark_sol``/``mark_at``/``mark_source`` likewise.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, JSONB_EMPTY_LIST

PROPOSAL_MODES = ("paper", "live")
LIVE_ORDER_SIDES = ("buy", "sell")
LIVE_ORDER_STATUSES = (
    "admitted",
    "refused",
    "simulated",
    "submitted_unconfirmed",
    "confirmed",
    "failed",
)
LIVE_POSITION_STATUSES = ("open", "closed")
LIVE_MARK_SOURCES = ("solana_rpc", "curve_snapshot", "tape")


class MemeLiveOrder(Base, UUIDPrimaryKeyMixin):
    """One attempt of the executor: the admission, the intent, the signatures, the state."""

    __tablename__ = "meme_live_orders"
    __table_args__ = (
        Index(
            "uq_meme_live_orders_one_buy_per_proposal",
            "proposal_id",
            unique=True,
            postgresql_where=text("side = 'buy'"),
        ),
        Index(
            "uq_meme_live_orders_tx_signature",
            "tx_signature",
            unique=True,
            postgresql_where=text("tx_signature IS NOT NULL"),
        ),
        Index("ix_meme_live_orders_status_received_at", "status", "received_at"),
        Index("ix_meme_live_orders_proposal_id_side", "proposal_id", "side"),
        CheckConstraint("side IN ('buy', 'sell')", name="side_is_a_known_label"),
        CheckConstraint(
            "status IN ('admitted', 'refused', 'simulated', 'submitted_unconfirmed', "
            "'confirmed', 'failed')",
            name="status_is_a_known_label",
        ),
        CheckConstraint(
            "status NOT IN ('refused', 'failed') OR reason IS NOT NULL",
            name="a_refusal_or_failure_names_its_reason",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR (fill IS NOT NULL AND tx_signature IS NOT NULL)",
            name="a_confirmed_order_carries_its_fill",
        ),
        CheckConstraint(
            "status NOT IN ('submitted_unconfirmed', 'confirmed') OR tx_signature IS NOT NULL",
            name="a_sent_order_has_a_signature",
        ),
        CheckConstraint("attempt >= 1", name="attempt_is_positive"),
        CheckConstraint("char_length(client_order_id) > 0", name="identity_is_not_empty"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_proposals.id"))
    side: Mapped[str] = mapped_column(Text)
    client_order_id: Mapped[str] = mapped_column(Text, unique=True)
    attempt: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    admission: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    tx_signature: Mapped[str | None] = mapped_column(Text)
    signatures: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    last_valid_block_height: Mapped[int | None] = mapped_column(BigInteger)
    signing_at: Mapped[datetime | None]
    fill: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    admitted_at: Mapped[datetime | None]
    simulated_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    settled_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MemeLivePosition(Base, UUIDPrimaryKeyMixin):
    """One real position, from the confirmed buy to the confirmed sell."""

    __tablename__ = "meme_live_positions"
    __table_args__ = (
        Index("ix_meme_live_positions_status_entry_at", "status", "entry_at"),
        Index("ix_meme_live_positions_mint", "mint"),
        CheckConstraint("status IN ('open', 'closed')", name="status_is_a_known_label"),
        CheckConstraint(
            "(status = 'closed') = (exit_at IS NOT NULL)", name="a_closed_position_says_when"
        ),
        CheckConstraint(
            "(exit_at IS NULL) = (exit IS NULL) AND (exit_at IS NULL) = (pnl_sol IS NULL) "
            "AND (exit_at IS NULL) = (r_multiple IS NULL)",
            name="an_exit_carries_its_numbers",
        ),
        CheckConstraint("exit_at IS NULL OR exit_at > entry_at", name="an_exit_is_after_the_entry"),
        CheckConstraint(
            "(mark_sol IS NULL) = (mark_at IS NULL) AND (mark_sol IS NULL) = (mark_source IS NULL)",
            name="a_mark_says_when_and_whence",
        ),
        CheckConstraint(
            "mark_source IS NULL OR mark_source IN ('solana_rpc', 'curve_snapshot', 'tape')",
            name="mark_source_is_a_known_label",
        ),
        CheckConstraint(
            "(sell_requested_at IS NULL) = (sell_requested_by IS NULL)",
            name="a_sell_request_names_who",
        ),
        CheckConstraint(
            "initial_risk_sol > 0 AND sol_spent_lamports > 0 AND tokens >= 0",
            name="the_risk_is_what_was_spent",
        ),
        CheckConstraint("char_length(mint) > 0", name="mint_is_not_empty"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_proposals.id"), unique=True)
    entry_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_live_orders.id"))
    mint: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    entry_at: Mapped[datetime]
    entry: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tokens: Mapped[int] = mapped_column(BigInteger)
    sol_spent_lamports: Mapped[int] = mapped_column(BigInteger)
    initial_risk_sol: Mapped[Decimal]
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    mark_sol: Mapped[Decimal | None]
    mark_at: Mapped[datetime | None]
    mark_source: Mapped[str | None] = mapped_column(Text)
    mark_reason: Mapped[str | None] = mapped_column(Text)
    high_water_sol: Mapped[Decimal | None]
    exit_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sell_requested_at: Mapped[datetime | None]
    sell_requested_by: Mapped[str | None] = mapped_column(Text)
    exit_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meme_live_orders.id"))
    exit_at: Mapped[datetime | None]
    exit_: Mapped[dict[str, Any] | None] = mapped_column("exit", JSONB)
    sol_received_lamports: Mapped[int | None] = mapped_column(BigInteger)
    pnl_sol: Mapped[Decimal | None]
    r_multiple: Mapped[Decimal | None]
    migrated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MemeLiveKillSwitch(Base):
    """The latched daily state per scope (§7). Released only by an owner's hand."""

    __tablename__ = "meme_live_kill_switch"
    __table_args__ = (
        CheckConstraint(
            "state IN ('ACTIVE', 'WARNING', 'TRADING_DISABLED', 'EMERGENCY')",
            name="state_is_a_known_label",
        ),
        CheckConstraint(
            "(released_at IS NULL) = (released_by IS NULL)", name="a_release_names_who"
        ),
        CheckConstraint(
            "(day_start_utc IS NULL) = (day_start_sol_equity IS NULL) "
            "AND (day_start_utc IS NULL) = (peak_sol_equity IS NULL) "
            "AND (day_start_utc IS NULL) = (anchor_observed_at IS NULL)",
            name="an_anchor_is_whole",
        ),
    )

    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    reason: Mapped[str | None] = mapped_column(Text)
    latched_at: Mapped[datetime | None]
    released_at: Mapped[datetime | None]
    released_by: Mapped[str | None] = mapped_column(Text)
    day_start_utc: Mapped[datetime | None]
    day_start_sol_equity: Mapped[Decimal | None]
    peak_sol_equity: Mapped[Decimal | None]
    anchor_observed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


__all__ = [
    "LIVE_MARK_SOURCES",
    "LIVE_ORDER_SIDES",
    "LIVE_ORDER_STATUSES",
    "LIVE_POSITION_STATUSES",
    "PROPOSAL_MODES",
    "MemeLiveKillSwitch",
    "MemeLiveOrder",
    "MemeLivePosition",
]
