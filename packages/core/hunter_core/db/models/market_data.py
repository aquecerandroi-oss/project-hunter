"""Market data — DATABASE.md §4. Global tables; ``market_snapshots`` and
``liquidations`` are RANGE-partitioned by month and ``candles`` is
``LIST (timeframe)`` then ``RANGE (open_time)`` (§1.3).

Raw trades and the order book are deliberately not persisted (SPEC_REVIEW.md B3).
Partitioned tables carry every partition key inside the primary key, as Postgres
requires, and ``infra/scripts/create_partitions.py`` keeps 3 months of partitions
ahead of the current one.

Funding is money-shaped, not a percentage: ``market_snapshots.funding_rate`` and
``funding_rates.rate`` are ``NUMERIC(28,10)``. ``NUMERIC(9,6)`` would round a
0.0000125 (0.00125 %) funding rate to 0.000013 — a 4 % error on the number the
derivatives strategies key off, and exactly zero for the smaller rates that are
the common case.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import PERCENT, SQL_FALSE, pg_enum
from hunter_core.domain.enums import OrderSide, Timeframe

_MARKET_FK = "markets.id"


class Candle(Base):
    """OHLCV per market and timeframe. ``is_final`` gates anti-look-ahead.

    ``LIST (timeframe)`` first, then ``RANGE (open_time)`` inside each timeframe
    (``candles_1m_2026_09``). DATABASE.md §1.3 gives 1m 90 days, 5m a year and
    1h/1d no limit: a single monthly RANGE would force one retention for all of
    them, and pruning 1m by ``DELETE`` would rewrite partitions that hold the
    history we keep.
    """

    __tablename__ = "candles"
    __table_args__ = {"postgresql_partition_by": "LIST (timeframe)"}

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="CASCADE"), primary_key=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum("candle_timeframe"), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(primary_key=True)
    open: Mapped[Decimal]
    high: Mapped[Decimal]
    low: Mapped[Decimal]
    close: Mapped[Decimal]
    volume: Mapped[Decimal]
    quote_volume: Mapped[Decimal | None]
    trade_count: Mapped[int | None] = mapped_column(Integer)
    taker_buy_volume: Mapped[Decimal | None]
    is_final: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    source: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MarketSnapshot(Base):
    """One row per market per minute: price, book top, derivatives state."""

    __tablename__ = "market_snapshots"
    __table_args__ = {"postgresql_partition_by": "RANGE (ts)"}

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(primary_key=True)
    price: Mapped[Decimal | None]
    bid: Mapped[Decimal | None]
    ask: Mapped[Decimal | None]
    spread_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    volume_24h: Mapped[Decimal | None]
    quote_volume_24h: Mapped[Decimal | None]
    open_interest: Mapped[Decimal | None]
    open_interest_value: Mapped[Decimal | None]
    funding_rate: Mapped[Decimal | None]
    next_funding_time: Mapped[datetime | None]
    mark_price: Mapped[Decimal | None]
    index_price: Mapped[Decimal | None]
    liq_long_notional_1h: Mapped[Decimal | None]
    liq_short_notional_1h: Mapped[Decimal | None]


class FundingRate(Base):
    """Realized funding per settlement. Small and unbounded; not partitioned."""

    __tablename__ = "funding_rates"

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="CASCADE"), primary_key=True
    )
    funding_time: Mapped[datetime] = mapped_column(primary_key=True)
    rate: Mapped[Decimal]
    mark_price: Mapped[Decimal | None]


class OpenInterestHistory(Base):
    """Open interest sampled every 5 minutes."""

    __tablename__ = "open_interest_history"

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(primary_key=True)
    open_interest: Mapped[Decimal | None]
    open_interest_value: Mapped[Decimal | None]


class Liquidation(Base, UUIDPrimaryKeyMixin):
    """Forced liquidations. ``ts`` joins the PK because it is the partition key."""

    __tablename__ = "liquidations"
    __table_args__ = (
        Index("ix_liquidations_market_ts", "market_id", "ts"),
        {"postgresql_partition_by": "RANGE (ts)"},
    )

    ts: Mapped[datetime] = mapped_column(primary_key=True)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="CASCADE"))
    side: Mapped[OrderSide] = mapped_column(pg_enum("order_side"))
    qty: Mapped[Decimal]
    price: Mapped[Decimal]
    notional: Mapped[Decimal | None]
    source: Mapped[str | None] = mapped_column(Text)


class IngestionGap(Base, UUIDPrimaryKeyMixin):
    """A detected hole in a candle series and its recovery state."""

    __tablename__ = "ingestion_gaps"
    __table_args__ = (Index("ix_ingestion_gaps_status_detected", "status", "detected_at"),)

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="CASCADE"), index=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum("candle_timeframe"))
    gap_start: Mapped[datetime]
    gap_end: Mapped[datetime]
    detected_at: Mapped[datetime] = mapped_column(server_default=func.now())
    recovered_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(Text, server_default="open")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
