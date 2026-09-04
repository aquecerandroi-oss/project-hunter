"""Market reference data — DATABASE.md §3. Global tables: no ``organization_id``,
no RLS; tenants read them through the API only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, SQL_FALSE, pg_enum
from hunter_core.domain.enums import ExchangeStatus, MarketStatus, MarketType


class Exchange(Base, UUIDPrimaryKeyMixin):
    """A venue. ``capabilities`` says which data streams it actually provides."""

    __tablename__ = "exchanges"

    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[ExchangeStatus] = mapped_column(
        pg_enum("exchange_status"), server_default=ExchangeStatus.ACTIVE.value
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Asset(Base, UUIDPrimaryKeyMixin):
    """A base or quote asset (BTC, USDT), independent of the venue."""

    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    coingecko_id: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Market(Base, UUIDPrimaryKeyMixin):
    """A tradable symbol on one exchange. ``is_monitored``/``monitor_rank`` drive
    the monitored universe (MARKET_UNIVERSE_SIZE).
    """

    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("exchange_id", "symbol", "market_type", name="uq_markets_exchange_symbol"),
        Index("ix_markets_monitored_rank", "is_monitored", "monitor_rank"),
    )

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exchanges.id", ondelete="RESTRICT"), index=True
    )
    symbol: Mapped[str] = mapped_column(Text)
    market_type: Mapped[MarketType] = mapped_column(pg_enum("market_type"))
    base_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    quote_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[MarketStatus] = mapped_column(
        pg_enum("market_status"), server_default=MarketStatus.ACTIVE.value
    )
    tick_size: Mapped[Decimal | None]
    step_size: Mapped[Decimal | None]
    min_notional: Mapped[Decimal | None]
    contract_size: Mapped[Decimal | None]
    max_leverage: Mapped[int | None] = mapped_column(Integer)
    is_monitored: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    monitor_rank: Mapped[int | None] = mapped_column(Integer)
    volume_24h_usd: Mapped[Decimal | None]
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime | None]
    delisted_at: Mapped[datetime | None]
