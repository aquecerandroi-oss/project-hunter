"""Equity curve, positions, orders and trades — cursor-paginated reads.

``positions``/``orders``/``trades`` are real queries against real (today,
empty) tables: T3.4/T3.5 have not landed a writer yet
(``docs/plans/M3.md``, "O que nao existe"), so an honestly empty page is what
these return — never a hand-built placeholder.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_

from hunter_api.repositories.base import (
    MAX_CURSOR_LENGTH,
    InvalidCursorError,
    clamp_page_size,
    decode_cursor,
)
from hunter_api.repositories.base import encode_cursor as encode_id_cursor
from hunter_api.schemas.portfolio_lists import (
    EquityCurvePointOut,
    OrderOut,
    PortfolioTradeOut,
    PositionOut,
)
from hunter_api.services.portfolio_trade_extras import brl_amount, load_exit_intents
from hunter_core.db.models.execution_fills import Position
from hunter_core.db.models.execution_orders import Order
from hunter_core.db.models.execution_trades import Trade
from hunter_core.db.models.portfolios import PortfolioEquitySnapshot
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.repositories.portfolio import PortfolioRepository
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.types import ensure_utc
from hunter_core.portfolio.attribution import attribute_brl

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.db.models.fx import FxObservation

DEFAULT_CURVE_RESOLUTION = Timeframe.H1
"""``hunter_core.db.repositories.equity.REFERENCE_RESOLUTION`` — the lane the
opening point and the daily reference live in (the only one any writer fills
today)."""


def _encode_ts_cursor(ts: datetime) -> str:
    return base64.urlsafe_b64encode(ensure_utc(ts).isoformat().encode()).decode()


def _decode_ts_cursor(cursor: str | None) -> datetime | None:
    """A cursor over ``ts`` alone — the equity curve's key has no row id to
    pair it with (``portfolio_equity_snapshots``' PK is ``(portfolio, resolution,
    ts)``), unlike the ``(created_at, id)`` keyset ``hunter_api.repositories.base``
    uses everywhere else.
    """
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        return ensure_utc(datetime.fromisoformat(raw))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidCursorError from None


async def list_equity_curve(
    session: AsyncSession,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    *,
    resolution: Timeframe = DEFAULT_CURVE_RESOLUTION,
    since: datetime | None,
    until: datetime | None,
    limit: int | None,
    cursor: str | None,
) -> tuple[list[EquityCurvePointOut], str | None]:
    size = clamp_page_size(limit)
    conditions = [
        PortfolioEquitySnapshot.organization_id == org_id,
        PortfolioEquitySnapshot.portfolio_id == portfolio_id,
        PortfolioEquitySnapshot.resolution == resolution,
    ]
    if since is not None:
        conditions.append(PortfolioEquitySnapshot.ts >= since)
    if until is not None:
        conditions.append(PortfolioEquitySnapshot.ts <= until)
    after = _decode_ts_cursor(cursor)
    if after is not None:
        conditions.append(PortfolioEquitySnapshot.ts > after)
    statement = (
        select(PortfolioEquitySnapshot)
        .where(*conditions)
        .order_by(PortfolioEquitySnapshot.ts)
        .limit(size + 1)
    )
    rows: Sequence[PortfolioEquitySnapshot] = (await session.execute(statement)).scalars().all()
    page = rows[:size]
    next_cursor = _encode_ts_cursor(page[-1].ts) if len(rows) > size else None

    anchor = await PortfolioRepository(session, org_id).get_anchor(portfolio_id)
    fx_cache: dict[uuid.UUID, FxObservation] = {}
    items: list[EquityCurvePointOut] = []
    for row in page:
        brl_equity: Decimal | None = None
        reason: str | None = "no_fx_at_recording"
        if row.fx_observation_id is not None and anchor is not None:
            fx: FxObservation | None = fx_cache.get(row.fx_observation_id)
            if fx is None:
                fx = await FxObservationRepository(session).get(row.fx_observation_id)
                if fx is not None:
                    fx_cache[row.fx_observation_id] = fx
            if fx is not None:
                brl_equity = attribute_brl(
                    equity=row.equity,
                    credited=anchor.credited_amount,
                    opening_rate=anchor.rate,
                    current_rate=fx.rate,
                ).equity_brl
                reason = None
        items.append(
            EquityCurvePointOut(
                ts=ensure_utc(row.ts),
                resolution=row.resolution,
                cash=row.cash,
                equity=row.equity,
                exposure_notional=row.exposure_notional,
                exposure_pct=row.exposure_pct,
                unrealized_pnl=row.unrealized_pnl,
                realized_pnl_cum=row.realized_pnl_cum,
                peak_equity=row.peak_equity,
                drawdown_pct=row.drawdown_pct,
                open_positions=row.open_positions,
                fx_observation_id=row.fx_observation_id,
                brl_equity=brl_equity,
                brl_unavailable_reason=reason,
            )
        )
    return items, next_cursor


async def list_positions(
    session: AsyncSession,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    *,
    limit: int | None,
    cursor: str | None,
) -> tuple[list[PositionOut], str | None]:
    size = clamp_page_size(limit)
    statement = (
        select(Position)
        .where(Position.organization_id == org_id, Position.portfolio_id == portfolio_id)
        .order_by(Position.opened_at, Position.id)
    )
    after = decode_cursor(cursor)
    if after is not None:
        statement = statement.where(tuple_(Position.opened_at, Position.id) > after)
    rows: Sequence[Position] = (await session.execute(statement.limit(size + 1))).scalars().all()
    page = rows[:size]
    next_cursor = encode_id_cursor(page[-1].opened_at, page[-1].id) if len(rows) > size else None
    intents_by_position = await load_exit_intents(
        session, org_id, portfolio_id, [row.id for row in page]
    )
    items = [
        PositionOut(
            id=row.id,
            market_id=row.market_id,
            direction=row.direction,
            qty=row.qty,
            avg_entry_price=row.avg_entry_price,
            mark_price=row.mark_price,
            stop_price=row.stop_price,
            unrealized_pnl=row.unrealized_pnl,
            realized_pnl=row.realized_pnl,
            fees_paid=row.fees_paid,
            status=row.status,
            opened_at=ensure_utc(row.opened_at),
            closed_at=None if row.closed_at is None else ensure_utc(row.closed_at),
            protection_intents=intents_by_position.get(row.id, []),
        )
        for row in page
    ]
    return items, next_cursor


async def list_orders(
    session: AsyncSession,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    *,
    limit: int | None,
    cursor: str | None,
) -> tuple[list[OrderOut], str | None]:
    size = clamp_page_size(limit)
    statement = (
        select(Order)
        .where(Order.organization_id == org_id, Order.portfolio_id == portfolio_id)
        .order_by(Order.created_at, Order.id)
    )
    after = decode_cursor(cursor)
    if after is not None:
        statement = statement.where(tuple_(Order.created_at, Order.id) > after)
    rows: Sequence[Order] = (await session.execute(statement.limit(size + 1))).scalars().all()
    page = rows[:size]
    next_cursor = encode_id_cursor(page[-1].created_at, page[-1].id) if len(rows) > size else None
    items = [
        OrderOut(
            id=row.id,
            market_id=row.market_id,
            side=row.side,
            type=row.type,
            purpose=row.purpose,
            execution_mode=row.execution_mode,
            status=row.status,
            qty=row.qty,
            price=row.price,
            stop_price=row.stop_price,
            filled_qty=row.filled_qty,
            avg_fill_price=row.avg_fill_price,
            created_at=ensure_utc(row.created_at),
            completed_at=None if row.completed_at is None else ensure_utc(row.completed_at),
        )
        for row in page
    ]
    return items, next_cursor


async def list_trades(
    session: AsyncSession,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    *,
    limit: int | None,
    cursor: str | None,
) -> tuple[list[PortfolioTradeOut], str | None]:
    size = clamp_page_size(limit)
    statement = (
        select(Trade)
        .where(Trade.organization_id == org_id, Trade.portfolio_id == portfolio_id)
        .order_by(Trade.closed_at, Trade.id)
    )
    after = decode_cursor(cursor)
    if after is not None:
        statement = statement.where(tuple_(Trade.closed_at, Trade.id) > after)
    rows: Sequence[Trade] = (await session.execute(statement.limit(size + 1))).scalars().all()
    page = rows[:size]
    next_cursor = encode_id_cursor(page[-1].closed_at, page[-1].id) if len(rows) > size else None
    position_ids = [row.position_id for row in page if row.position_id is not None]
    intents_by_position = await load_exit_intents(session, org_id, portfolio_id, position_ids)
    items: list[PortfolioTradeOut] = []
    for row in page:
        closed_at = ensure_utc(row.closed_at)
        fees_brl, fees_reason = await brl_amount(session, row.fees, as_of=closed_at)
        pnl_brl, pnl_reason = await brl_amount(session, row.pnl, as_of=closed_at)
        items.append(
            PortfolioTradeOut(
                id=row.id,
                market_id=row.market_id,
                direction=row.direction,
                entry_price=row.entry_price,
                exit_price=row.exit_price,
                qty=row.qty,
                fees=row.fees,
                fees_brl=fees_brl,
                fees_brl_unavailable_reason=fees_reason,
                pnl=row.pnl,
                pnl_brl=pnl_brl,
                pnl_brl_unavailable_reason=pnl_reason,
                pnl_pct=row.pnl_pct,
                exit_reason=row.exit_reason,
                entry_snapshot=dict(row.entry_snapshot or {}),
                exit_snapshot=dict(row.exit_snapshot or {}),
                protection_intents=(
                    [] if row.position_id is None else intents_by_position.get(row.position_id, [])
                ),
                opened_at=ensure_utc(row.opened_at),
                closed_at=closed_at,
            )
        )
    return items, next_cursor
