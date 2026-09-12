"""``meme_board_observations`` and ``meme_risk_snapshots`` — what the site showed,
and what its risk read said (DATABASE.md §35, revision ``0023_meme_boards_trades``).

**Global tables** (§1.1), monthly ``RANGE`` parents (§1.3): a board is what
every visitor sees and a risk read is about a coin on the chain; neither
belongs to an organization.

``meme_board_observations`` is **one row per mint per board per closed
minute** — the last version of the entry seen inside the minute, how many
patches touched it, its position, and the **exposure interval** A4.0g asked for
(``docs/plans/T4-CANTOS.md`` §2): ``first_seen_in_board_at``/
``last_seen_in_board_at`` as observed, ``left_board_at`` only when a ``remove``
patch was seen, and ``exposure_censored = true`` when the coin disappeared
while the socket was down — a disappearance nobody watched is censoring, not
an exit. ``observed_at`` is the ``serverTs`` of the last board message of the
minute (the board still listed the mint then); ``mint_updated_at`` is the
``serverTs`` of the last patch that touched the mint itself, which can be
older. ``minute_end`` is the closed minute the row summarises, bucketed by
**our** ``received_at`` (the non-anticipation clock).

``meme_risk_snapshots`` keeps the 65-field ``/in-memory-coin`` object **raw**
(``raw jsonb``) beside the few columns whose key names state their meaning;
nothing in the raw object is promoted to a column by guess.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import JSONB_EMPTY, PERCENT

BOARDS = ("new", "graduating", "graduated", "movers")
"""``PRO_SCREENER_BOARDS`` of the site's bundle (``docs/PUMPFUN.md`` §3.1)."""


class MemeBoardObservation(Base):
    """One coin on one board, summarised over one closed minute."""

    __tablename__ = "meme_board_observations"
    __table_args__ = (
        Index("ix_meme_board_observations_mint_observed", "mint", "observed_at"),
        Index("ix_meme_board_observations_minute_end_board", "minute_end", "board"),
        CheckConstraint(
            "board IN ('new', 'graduating', 'graduated', 'movers')",
            name="board_is_a_known_label",
        ),
        CheckConstraint(
            "char_length(mint) > 0 AND char_length(source) > 0",
            name="provenance_is_not_empty",
        ),
        CheckConstraint("position >= 0", name="position_is_not_negative"),
        CheckConstraint("patches >= 0", name="patches_are_not_negative"),
        CheckConstraint(
            "last_seen_in_board_at >= first_seen_in_board_at",
            name="exposure_is_an_interval",
        ),
        CheckConstraint(
            "NOT (exposure_censored AND left_board_at IS NOT NULL)",
            name="a_censored_exposure_has_no_exit",
        ),
        {"postgresql_partition_by": "RANGE (observed_at)"},
    )

    observed_at: Mapped[datetime] = mapped_column(primary_key=True)
    board: Mapped[str] = mapped_column(Text, primary_key=True)
    mint: Mapped[str] = mapped_column(Text, primary_key=True)
    minute_end: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    mint_updated_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer)
    patches: Mapped[int] = mapped_column(Integer, server_default="0")
    chain: Mapped[str | None] = mapped_column(Text)
    program: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    quote_asset: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    symbol: Mapped[str | None] = mapped_column(Text)
    market_cap_usd: Mapped[Decimal | None]
    progress_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    volume_sol: Mapped[Decimal | None]
    volume_usd: Mapped[Decimal | None]
    volume_5m_sol: Mapped[Decimal | None]
    volume_15m_sol: Mapped[Decimal | None]
    volume_1h_sol: Mapped[Decimal | None]
    volume_24h_sol: Mapped[Decimal | None]
    volume_5m_usd: Mapped[Decimal | None]
    volume_15m_usd: Mapped[Decimal | None]
    volume_1h_usd: Mapped[Decimal | None]
    volume_24h_usd: Mapped[Decimal | None]
    tx_5m: Mapped[int | None] = mapped_column(Integer)
    age_s: Mapped[int | None] = mapped_column(Integer)
    kol_count: Mapped[int | None] = mapped_column(Integer)
    snipers: Mapped[int | None] = mapped_column(Integer)
    is_mayhem: Mapped[bool | None]
    mayhem_state: Mapped[str | None] = mapped_column(Text)
    has_social: Mapped[bool | None]
    has_twitter: Mapped[bool | None]
    has_website: Mapped[bool | None]
    has_telegram: Mapped[bool | None]
    graduated_at: Mapped[datetime | None]
    ath_market_cap_usd: Mapped[Decimal | None]
    buys: Mapped[int | None] = mapped_column(Integer)
    sells: Mapped[int | None] = mapped_column(Integer)
    txs: Mapped[int | None] = mapped_column(Integer)
    holders: Mapped[int | None] = mapped_column(Integer)
    top10_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    dev_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    cashback: Mapped[bool | None]
    dev_wallet: Mapped[str | None] = mapped_column(Text)
    is_live: Mapped[bool | None]
    participants: Mapped[int | None] = mapped_column(Integer)
    fees_sol: Mapped[Decimal | None]
    fees_usd: Mapped[Decimal | None]
    first_seen_in_board_at: Mapped[datetime]
    last_seen_in_board_at: Mapped[datetime]
    left_board_at: Mapped[datetime | None]
    exposure_censored: Mapped[bool] = mapped_column(server_default="false")
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    source: Mapped[str] = mapped_column(Text)


class MemeRiskSnapshot(Base):
    """One ``/in-memory-coin`` read: the raw object and the extracted shares."""

    __tablename__ = "meme_risk_snapshots"
    __table_args__ = (
        Index("ix_meme_risk_snapshots_mint_observed", "mint", "observed_at"),
        CheckConstraint(
            "char_length(mint) > 0 AND char_length(source) > 0",
            name="provenance_is_not_empty",
        ),
        CheckConstraint(
            "(holders IS NULL OR holders >= 0) AND (snipers IS NULL OR snipers >= 0)",
            name="counts_are_not_negative",
        ),
        {"postgresql_partition_by": "RANGE (observed_at)"},
    )

    observed_at: Mapped[datetime] = mapped_column(primary_key=True)
    mint: Mapped[str] = mapped_column(Text, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    source: Mapped[str] = mapped_column(Text)
    program: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(Text)
    quote_mint: Mapped[str | None] = mapped_column(Text)
    quote_asset: Mapped[str | None] = mapped_column(Text)
    holders: Mapped[int | None] = mapped_column(Integer)
    top10_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    dev_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    snipers: Mapped[int | None] = mapped_column(Integer)
    sniper_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    bundled_share: Mapped[Decimal | None] = mapped_column(PERCENT)
    progress_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    graduated_at: Mapped[datetime | None]
    is_mayhem: Mapped[bool | None]
    mayhem_state: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
