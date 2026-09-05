"""Reading ``exchanges``/``assets``/``markets``/``candles``/``ingestion_gaps`` —
global tables, no RLS (``hunter_core/db/models/markets.py`` module docstring).
Every query here is read-only; the transaction runs as ``hunter_app`` and
that role never holds anything but ``SELECT`` on these tables.

Not a ``TenantRepository`` (``repositories/base.py``): there is no
organization to scope by. Any authenticated principal may read every row.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastapi import status
from sqlalchemy import any_, bindparam, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import aliased

from hunter_api.errors import HunterError
from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

MAX_CURSOR_LENGTH = 64


class InvalidMarketCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_market_cursor(row_id: uuid.UUID) -> str:
    """A page-2+ request names the last row's id it already has; the ordering
    below (``exchange code, symbol, id``) is deterministic and ``id`` is
    unique, so the id alone is enough to resume after it.
    """
    return base64.urlsafe_b64encode(str(row_id).encode()).decode()


def decode_market_cursor(cursor: str | None) -> uuid.UUID | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidMarketCursorError
    try:
        return uuid.UUID(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidMarketCursorError from None


@dataclass(frozen=True, slots=True)
class MarketRow:
    """One ``markets`` row joined to its exchange/asset identity columns —
    everything Postgres knows about a market, before Redis hot state is merged in.
    """

    id: uuid.UUID
    exchange: str
    symbol: str
    base_asset: str | None
    quote_asset: str | None
    market_type: MarketType
    status: MarketStatus
    is_monitored: bool
    monitor_rank: int | None


def _base_select():
    base = aliased(Asset)
    quote = aliased(Asset)
    return (
        select(
            Market.id,
            Exchange.code.label("exchange"),
            Market.symbol,
            base.symbol.label("base_asset"),
            quote.symbol.label("quote_asset"),
            Market.market_type,
            Market.status,
            Market.is_monitored,
            Market.monitor_rank,
        )
        .join(Exchange, Exchange.id == Market.exchange_id)
        .outerjoin(base, base.id == Market.base_asset_id)
        .outerjoin(quote, quote.id == Market.quote_asset_id)
    )


def _row_to_market(row: Any) -> MarketRow:
    """Every column ``_base_select`` labels matches a ``MarketRow`` field name,
    so this is a straight attribute copy off the SQLAlchemy ``Row``. Typed
    ``Any`` because SQLAlchemy's ``Row`` does not carry per-label attribute
    types for a hand-built column list — the fields are validated at the
    ``MarketRow`` dataclass boundary instead.
    """
    return MarketRow(
        id=row.id,
        exchange=row.exchange,
        symbol=row.symbol,
        base_asset=row.base_asset,
        quote_asset=row.quote_asset,
        market_type=row.market_type,
        status=row.status,
        is_monitored=row.is_monitored,
        monitor_rank=row.monitor_rank,
    )


class MarketRepository:
    """Global, read-only access to market reference data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_markets(
        self,
        *,
        exchange: str | None = None,
        q: str | None = None,
        monitored: bool | None = None,
    ) -> list[MarketRow]:
        """Every market matching the filters, ordered ``(exchange, symbol, id)``.

        Unpaginated on purpose: ``services/markets.py`` needs the *whole*
        filtered set to compute the ``summary`` counts and to merge in Redis
        state before paginating, and at M1 scale (``MARKET_UNIVERSE_SIZE``
        default 200) that is one cheap query, not a scalability risk.
        """
        statement = _base_select()
        if exchange:
            statement = statement.where(Exchange.code == exchange)
        if monitored is not None:
            statement = statement.where(Market.is_monitored.is_(monitored))
        if q:
            statement = statement.where(Market.symbol.ilike(f"%{q}%"))
        statement = statement.order_by(Exchange.code, Market.symbol, Market.id)
        rows = (await self.session.execute(statement)).all()
        return [_row_to_market(row) for row in rows]

    async def get_market(self, exchange: str, symbol: str) -> MarketRow | None:
        """The market for ``(exchange, symbol)``, or ``None``.

        M1 only ever seeds Binance USDS-M perpetuals, so ``(exchange, symbol)``
        is unambiguous today; a future exchange with both spot and perpetual
        listings under the same symbol would need ``market_type`` in the path
        too — out of scope until that market type actually exists.
        """
        statement = (
            _base_select().where(Exchange.code == exchange, Market.symbol == symbol).limit(1)
        )
        row = (await self.session.execute(statement)).first()
        return _row_to_market(row) if row is not None else None

    async def list_exchange_codes(self) -> list[str]:
        rows = (await self.session.execute(select(Exchange.code).order_by(Exchange.code))).all()
        return [row[0] for row in rows]

    async def monitored_market_counts(self) -> dict[str, int]:
        """``exchange code -> count of is_monitored markets``, for
        ``system/market-status``.
        """
        statement = (
            select(Exchange.code, func.count(Market.id))
            .join(Market, Market.exchange_id == Exchange.id)
            .where(Market.is_monitored.is_(True))
            .group_by(Exchange.code)
        )
        rows = (await self.session.execute(statement)).all()
        return {code: count for code, count in rows}

    async def gapped_market_ids(self, market_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Markets with an ``open`` or ``failed`` ``ingestion_gaps`` row —
        the "gap" input to the ``data_quality`` aggregate rule
        (``services/markets.py``): both a gap actively being recovered and one
        that exhausted its retries and gave up degrade the market, unlike
        ``open_gap_counts`` below, which only counts the former.

        (F6) ``= ANY(:ids)`` over a single ``ARRAY`` bind parameter, not
        ``.in_(market_ids)`` — ``.in_()`` expands to one bind parameter per
        id, so once ``markets`` grows past asyncpg's ~65535 bind-parameter
        ceiling this call would 500 every ``GET /api/v1/markets`` request.
        One array parameter has no such ceiling, regardless of list length.
        """
        if not market_ids:
            return set()
        ids_param = bindparam(
            "gap_market_ids",
            value=list(market_ids),
            type_=postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
        )
        statement = (
            select(IngestionGap.market_id)
            .where(
                IngestionGap.market_id == any_(ids_param),
                IngestionGap.status.in_(("open", "failed")),
            )
            .distinct()
        )
        rows = (await self.session.execute(statement)).scalars().all()
        return set(rows)

    async def open_gap_counts(self) -> dict[str, int]:
        """``exchange code -> count of ingestion_gaps with status = 'open'``."""
        statement = (
            select(Exchange.code, func.count(IngestionGap.id))
            .select_from(IngestionGap)
            .join(Market, Market.id == IngestionGap.market_id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(IngestionGap.status == "open")
            .group_by(Exchange.code)
        )
        rows = (await self.session.execute(statement)).all()
        return {code: count for code, count in rows}


class CandleRepository:
    """``candles`` — ``is_final = true`` only (DATABASE.md §4 anti-look-ahead)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_candles(
        self,
        market_id: uuid.UUID,
        timeframe: Timeframe,
        *,
        limit: int,
        before: datetime | None = None,
    ) -> Sequence[Candle]:
        """The ``limit`` most recent final candles strictly before ``before``
        (or the newest ``limit`` overall), returned oldest-first — chart order.
        """
        statement = select(Candle).where(
            Candle.market_id == market_id,
            Candle.timeframe == timeframe,
            Candle.is_final.is_(True),
        )
        if before is not None:
            statement = statement.where(Candle.open_time < before)
        statement = statement.order_by(Candle.open_time.desc()).limit(limit)
        rows = (await self.session.execute(statement)).scalars().all()
        return list(reversed(rows))
