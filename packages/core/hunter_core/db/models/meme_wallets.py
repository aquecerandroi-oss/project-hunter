"""The observed wallet — real pump.fun fills read from the chain and the positions
derived from them (DATABASE.md §39, revision ``0027_meme_wallets``).

**Global tables** (§1.1), the shape of ``meme_tokens``/``meme_paper_bets``: a
public wallet's fills belong to the radar, not to an organization — no
``organization_id``, no RLS. Nothing here is written by anything that signs:
the meme-worker's wallet loop reads ``getSignaturesForAddress`` +
``getTransaction`` for the addresses in ``MEME_WATCH_WALLETS`` and records
what it decoded, or — ``side = 'unknown'`` with ``raw`` — that it could not.

Three decisions live here rather than in prose:

- **A fill carries its numbers; an unknown carries its raw.** ``side <>
  'unknown'`` ⟹ mint, venue, block time, SOL leg, fee and tokens are all set;
  ``side = 'unknown'`` ⟺ ``decode = 'none'`` and ``raw`` is present. There is
  no row that half-decoded.
- **``lab_context`` belongs to a buy.** It is the answer to "would the Lab
  have bought this?" and a sell asks no such question.
- **A position's mark names its source, or its absence its reason.**
  ``mark_sol``, ``mark_at``, ``mark_source`` and ``unrealized_pnl_sol`` are
  null together or set together, and exactly then ``mark_reason`` is set.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base

WALLET_TRADE_SIDES = ("buy", "sell", "unknown")
WALLET_TRADE_VENUES = ("curve", "pool")
"""``curve``: the pump program's ``TradeEvent`` (exact fees). ``pool``: a
PumpSwap swap read from the wallet's own balance deltas."""

WALLET_TRADE_DECODES = ("trade_event", "balance_delta", "none")
WALLET_POSITION_STATUSES = ("open", "closed")
WALLET_MARK_SOURCES = ("curve_snapshot", "tape")


class MemeWalletTrade(Base):
    """One fill of a watched wallet — or one signature nothing decoded."""

    __tablename__ = "meme_wallet_trades"
    __table_args__ = (
        Index("ix_meme_wallet_trades_wallet_block_time", "wallet", "block_time"),
        Index("ix_meme_wallet_trades_wallet_mint", "wallet", "mint"),
        Index("ix_meme_wallet_trades_mint_block_time", "mint", "block_time"),
        CheckConstraint("side IN ('buy', 'sell', 'unknown')", name="side_is_a_known_label"),
        CheckConstraint(
            "venue IS NULL OR venue IN ('curve', 'pool')", name="venue_is_a_known_label"
        ),
        CheckConstraint(
            "decode IN ('trade_event', 'balance_delta', 'none')", name="decode_is_a_known_label"
        ),
        CheckConstraint(
            "(side = 'unknown') = (decode = 'none')", name="an_unknown_is_what_nothing_decoded"
        ),
        CheckConstraint("side <> 'unknown' OR raw IS NOT NULL", name="an_unknown_keeps_the_raw"),
        CheckConstraint(
            "side = 'unknown' OR (mint IS NOT NULL AND venue IS NOT NULL "
            "AND block_time IS NOT NULL AND sol_lamports IS NOT NULL "
            "AND fee_lamports IS NOT NULL AND token_amount IS NOT NULL)",
            name="a_fill_carries_its_numbers",
        ),
        CheckConstraint(
            "slot >= 0 AND event_index >= 0 "
            "AND (sol_lamports IS NULL OR sol_lamports >= 0) "
            "AND (fee_lamports IS NULL OR fee_lamports >= 0) "
            "AND (token_amount IS NULL OR token_amount >= 0)",
            name="chain_counters_are_not_negative",
        ),
        CheckConstraint("lab_context IS NULL OR side = 'buy'", name="lab_context_belongs_to_a_buy"),
        CheckConstraint(
            "hype_score IS NULL OR (hype_score >= 0 AND hype_score <= 1)",
            name="hype_score_is_a_fraction",
        ),
        CheckConstraint(
            "line_reason IS NULL OR line_reason IN "
            "('too_few_points', 'no_snapshot', 'flat', 'out_of_range')",
            name="line_reason_is_a_known_label",
        ),
        CheckConstraint(
            "char_length(wallet) > 0 AND char_length(signature) > 0",
            name="identity_is_not_empty",
        ),
    )

    wallet: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(Text, primary_key=True)
    event_index: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, server_default=text("0")
    )
    """The ordinal of the fill inside its transaction — dedupe is by signature,
    and a bundle of two fills in one transaction is not halved."""

    slot: Mapped[int] = mapped_column(BigInteger)
    block_time: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    mint: Mapped[str | None] = mapped_column(Text)
    side: Mapped[str] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(Text)
    sol_lamports: Mapped[int | None] = mapped_column(BigInteger)
    """The trade leg as the chain reports it (``sol_amount`` of the event, or
    the wallet's SOL delta net of the network fee on the balance path)."""

    token_amount: Mapped[Decimal | None]
    fee_lamports: Mapped[int | None] = mapped_column(BigInteger)
    """Every deduction on top of the leg: protocol, creator, cashback, and the
    network fee when this wallet paid it. A buy cost ``sol + fee``; a sell
    netted ``sol − fee``."""

    decode: Mapped[str] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lab_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    hype_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    line_reason: Mapped[str | None] = mapped_column(Text)


class MemeWalletPosition(Base):
    """Per wallet × mint, recomputed from the ledger — never a memory of a process."""

    __tablename__ = "meme_wallet_positions"
    __table_args__ = (
        Index("ix_meme_wallet_positions_status_last_trade_at", "status", "last_trade_at"),
        CheckConstraint("status IN ('open', 'closed')", name="status_is_a_known_label"),
        CheckConstraint(
            "(status = 'closed') = (tokens_held = 0)", name="a_closed_position_holds_nothing"
        ),
        CheckConstraint(
            "(mark_sol IS NULL) = (mark_at IS NULL) "
            "AND (mark_sol IS NULL) = (mark_source IS NULL) "
            "AND (mark_sol IS NULL) = (mark_reason IS NOT NULL) "
            "AND (mark_sol IS NULL) = (unrealized_pnl_sol IS NULL)",
            name="a_mark_names_its_source_and_when",
        ),
        CheckConstraint(
            "mark_source IS NULL OR mark_source IN ('curve_snapshot', 'tape')",
            name="mark_source_is_a_known_label",
        ),
        CheckConstraint(
            "tokens_held >= 0 AND sol_spent >= 0 AND sol_received >= 0 "
            "AND open_cost_sol >= 0 AND unmatched_sell_tokens >= 0 "
            "AND buys >= 0 AND sells >= 0",
            name="amounts_are_not_negative",
        ),
        CheckConstraint("(buys = 0) = (first_buy_at IS NULL)", name="a_buy_says_when"),
        CheckConstraint(
            "char_length(wallet) > 0 AND char_length(mint) > 0", name="identity_is_not_empty"
        ),
    )

    wallet: Mapped[str] = mapped_column(Text, primary_key=True)
    mint: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    tokens_held: Mapped[Decimal]
    sol_spent: Mapped[Decimal]
    """Σ buys, fees included — the risk of the position (RISK_ENGINE_MEME §5)."""

    sol_received: Mapped[Decimal]
    open_cost_sol: Mapped[Decimal]
    """FIFO cost of the tokens still held."""

    avg_cost_sol_per_token: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    realized_pnl_sol: Mapped[Decimal]
    unmatched_sell_tokens: Mapped[Decimal] = mapped_column(server_default=text("0"))
    """Tokens sold with no observed buy behind them (held before the watch
    began): their proceeds are in ``sol_received`` and nowhere else."""

    buys: Mapped[int] = mapped_column(Integer)
    sells: Mapped[int] = mapped_column(Integer)
    first_buy_at: Mapped[datetime | None]
    last_trade_at: Mapped[datetime]
    mark_sol: Mapped[Decimal | None]
    """What a full sell of ``tokens_held`` would net now on the curve (fees at
    the wallet's own observed rate), or tokens × the last tape price."""

    mark_at: Mapped[datetime | None]
    mark_source: Mapped[str | None] = mapped_column(Text)
    mark_reason: Mapped[str | None] = mapped_column(Text)
    unrealized_pnl_sol: Mapped[Decimal | None]
    r_multiple: Mapped[Decimal | None]
    """``(realized + unrealized) / sol_spent``; closed: ``realized / sol_spent``."""

    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


__all__ = [
    "WALLET_MARK_SOURCES",
    "WALLET_POSITION_STATUSES",
    "WALLET_TRADE_DECODES",
    "WALLET_TRADE_SIDES",
    "WALLET_TRADE_VENUES",
    "MemeWalletPosition",
    "MemeWalletTrade",
]
