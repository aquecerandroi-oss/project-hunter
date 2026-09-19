"""The ``spot/1`` desk — the Binance -> Solana market map, the real orders and
the real positions (DATABASE.md §63, revision ``0057_spot_desk``, T4.74-1;
design ``docs/design/spot1-lab-solana.md`` §2/§5).

**Global tables** (§1.1), the shape of ``meme_live_*``: an order signed
against a Jupiter route belongs to no organization. Written by
``hunter_worker`` (the meme-executor's ``spot_*`` lane) only; ``hunter_app``
reads, and may set exactly ``sell_requested_at``/``sell_requested_by`` on a
position. The market map is edited only through the audited script
``infra/scripts/spot_desk_markets.py``.

Three decisions live here rather than in prose:

- **A signal has one buy, a signature has one order, a signal has one
  position.** The partial unique index on ``(signal_id) WHERE side = 'buy'``
  is the ``NOT EXISTS`` of the candidate query (§2); the partial unique on
  ``tx_signature`` is what makes a redelivered confirmation find its row;
  ``spot_positions.signal_id`` unique is one position per signal.
- **A sell names the position it closes, a buy never does.**
  ``(side = 'sell') = (position_id IS NOT NULL)`` — the cycle orders ->
  positions -> orders is closed with ``use_alter`` and an ``ALTER TABLE`` in
  the DDL after both tables exist (``ddl/spot_desk.py``).
- **The R of the row is the signal's R.** ``initial_risk_sol`` is
  ``r_unit_sol = ticket × stop_frac`` (§4), not the SOL spent; the ATA rent a
  sell leaves behind is ``ata_rent_lamports`` and stays **out** of ``pnl_sol``.
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
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, JSONB_EMPTY_LIST, PERCENT, SQL_FALSE

SPOT_DESK_LABEL = "spot/1"
SPOT_MARKET_KINDS = ("nativo", "ponte", "representacao")
SPOT_MARKET_TIERS = ("A", "B", "C")
SPOT_ORDER_SIDES = ("buy", "sell")
SPOT_ORDER_STATUSES = (
    "admitted",
    "refused",
    "simulated",
    "submitted_unconfirmed",
    "confirmed",
    "failed",
)
SPOT_POSITION_STATUSES = ("open", "closed")
SPOT_MARK_SOURCES = ("jupiter_quote",)


class SpotDeskMarket(Base):
    """One executable Binance market and the Solana mint it maps to (R63 §2a)."""

    __tablename__ = "spot_desk_markets"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('nativo', 'ponte', 'representacao')", name="kind_is_a_known_label"
        ),
        CheckConstraint("tier IN ('A', 'B', 'C')", name="tier_is_a_known_label"),
        CheckConstraint(
            "char_length(binance_symbol) > 0 AND char_length(base) > 0 "
            "AND char_length(mint) > 0 AND char_length(updated_by) > 0",
            name="identity_is_not_empty",
        ),
        CheckConstraint("units_per_binance_unit > 0", name="units_are_positive"),
        CheckConstraint("liquidity_usd_at_seed >= 0", name="liquidity_is_not_negative"),
        CheckConstraint(
            "decimals IS NULL OR (decimals >= 0 AND decimals <= 18)",
            name="decimals_are_a_token_scale",
        ),
    )

    binance_symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    base: Mapped[str] = mapped_column(Text)
    mint: Mapped[str] = mapped_column(Text)
    units_per_binance_unit: Mapped[Decimal] = mapped_column(server_default=text("1"))
    """1000 for ``1000BONK``/``1000PEPE`` (one Binance unit is 1 000 tokens), else 1."""
    kind: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text)
    liquidity_usd_at_seed: Mapped[Decimal]
    round_trip_cost_pct_at_seed: Mapped[Decimal] = mapped_column(PERCENT)
    """A fraction (``0.00193`` = 0,193 %), §1 — the R63 round trip of 0,05 SOL."""
    decimals: Mapped[int | None] = mapped_column(SmallInteger)
    """``NULL`` until the executor reads the mint once over RPC and writes it back."""
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=SQL_FALSE)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[str] = mapped_column(Text)


class SpotOrder(Base, UUIDPrimaryKeyMixin):
    """One attempt of the spot lane: the admission, the quote, the signatures, the state."""

    __tablename__ = "spot_orders"
    __table_args__ = (
        Index(
            "uq_spot_orders_one_buy_per_signal",
            "signal_id",
            unique=True,
            postgresql_where=text("side = 'buy'"),
        ),
        Index(
            "uq_spot_orders_tx_signature",
            "tx_signature",
            unique=True,
            postgresql_where=text("tx_signature IS NOT NULL"),
        ),
        Index("ix_spot_orders_status_received_at", "status", "received_at"),
        Index("ix_spot_orders_signal_id_side", "signal_id", "side"),
        Index("ix_spot_orders_market_symbol_status", "market_symbol", "status"),
        Index(
            "ix_spot_orders_position_id",
            "position_id",
            postgresql_where=text("position_id IS NOT NULL"),
        ),
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
        CheckConstraint(
            "(side = 'sell') = (position_id IS NOT NULL)", name="a_sell_names_its_position"
        ),
        CheckConstraint("attempt >= 1", name="attempt_is_positive"),
        CheckConstraint(
            "char_length(client_order_id) > 0 AND char_length(desk) > 0 AND char_length(mint) > 0",
            name="identity_is_not_empty",
        ),
    )

    desk: Mapped[str] = mapped_column(Text, server_default=text("'spot/1'"))
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_signals.id"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "spot_positions.id",
            use_alter=True,
            name="fk_spot_orders_position_id_spot_positions",
        )
    )
    """A sell's position; closes the cycle orders -> positions -> orders."""
    market_symbol: Mapped[str] = mapped_column(Text, ForeignKey("spot_desk_markets.binance_symbol"))
    mint: Mapped[str] = mapped_column(Text)
    side: Mapped[str] = mapped_column(Text)
    client_order_id: Mapped[str] = mapped_column(Text, unique=True)
    attempt: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    quote: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """The Jupiter quote that produced the transaction — never the fill."""
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    admission: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    tx_signature: Mapped[str | None] = mapped_column(Text)
    signatures: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    last_valid_block_height: Mapped[int | None] = mapped_column(BigInteger)
    signing_at: Mapped[datetime | None]
    fill: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Real deltas read from the chain after ``confirmed`` (wallet lamports and
    ATA atoms, before/after) — never the quote."""
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    admitted_at: Mapped[datetime | None]
    simulated_at: Mapped[datetime | None]
    submitted_at: Mapped[datetime | None]
    settled_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SpotPosition(Base, UUIDPrimaryKeyMixin):
    """One real spot position, from the confirmed buy to the confirmed sell."""

    __tablename__ = "spot_positions"
    __table_args__ = (
        Index("ix_spot_positions_status_entry_at", "status", "entry_at"),
        Index("ix_spot_positions_market_symbol_status", "market_symbol", "status"),
        Index(
            "ix_spot_positions_exit_order_id",
            "exit_order_id",
            postgresql_where=text("exit_order_id IS NOT NULL"),
        ),
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
            "mark_source IS NULL OR mark_source IN ('jupiter_quote')",
            name="mark_source_is_a_known_label",
        ),
        CheckConstraint(
            "(sell_requested_at IS NULL) = (sell_requested_by IS NULL)",
            name="a_sell_request_names_who",
        ),
        CheckConstraint(
            "initial_risk_sol > 0 AND sol_spent_lamports > 0 AND tokens >= 0",
            name="the_risk_is_the_signal_s_r",
        ),
        CheckConstraint("ata_rent_lamports >= 0", name="rent_is_not_negative"),
        CheckConstraint("char_length(mint) > 0", name="mint_is_not_empty"),
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_signals.id"), unique=True)
    entry_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spot_orders.id"), unique=True)
    market_symbol: Mapped[str] = mapped_column(Text, ForeignKey("spot_desk_markets.binance_symbol"))
    mint: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    entry_at: Mapped[datetime]
    entry: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tokens: Mapped[int] = mapped_column(BigInteger)
    sol_spent_lamports: Mapped[int] = mapped_column(BigInteger)
    initial_risk_sol: Mapped[Decimal]
    """``r_unit_sol = ticket × stop_frac`` — the signal's R in SOL (§4), not the spend."""
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    """The geometry written at entry: ``ref``, ``stop_frac``, ``target_frac``,
    ``horizon_s``, ``entry_sol_per_atom``, ``r_unit_sol``, the three prices."""
    ata_rent_lamports: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    """The 0,00204 SOL a Jupiter sell leaves in the token ATA; out of ``pnl_sol``."""
    mark_sol: Mapped[Decimal | None]
    mark_at: Mapped[datetime | None]
    mark_source: Mapped[str | None] = mapped_column(Text)
    mark_reason: Mapped[str | None] = mapped_column(Text)
    high_water_sol: Mapped[Decimal | None]
    exit_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sell_requested_at: Mapped[datetime | None]
    sell_requested_by: Mapped[str | None] = mapped_column(Text)
    exit_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spot_orders.id"))
    exit_at: Mapped[datetime | None]
    exit_: Mapped[dict[str, Any] | None] = mapped_column("exit", JSONB)
    sol_received_lamports: Mapped[int | None] = mapped_column(BigInteger)
    pnl_sol: Mapped[Decimal | None]
    r_multiple: Mapped[Decimal | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


__all__ = [
    "SPOT_DESK_LABEL",
    "SPOT_MARKET_KINDS",
    "SPOT_MARKET_TIERS",
    "SPOT_MARK_SOURCES",
    "SPOT_ORDER_SIDES",
    "SPOT_ORDER_STATUSES",
    "SPOT_POSITION_STATUSES",
    "SpotDeskMarket",
    "SpotOrder",
    "SpotPosition",
]
