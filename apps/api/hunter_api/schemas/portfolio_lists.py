"""Equity curve, positions, orders and trades — the lists T3.8a can show today.

There is no writer for ``positions``/``orders``/``trades`` yet (T3.4/T3.5 are
separate tasks; ``docs/plans/M3.md`` "O que nao existe"): the repository
queries in ``hunter_api.services.portfolio_lists`` are real, cursor-paginated
reads of those tables, and they return empty pages honestly because the tables
are empty — never a hand-built placeholder list. ``as_of`` on every page is the
instant the read was taken, so an empty page is legible as "nothing existed
yet" rather than "the endpoint is unfinished".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from hunter_core.domain.enums import (
    ExecutionMode,
    ExitReason,
    OrderPurpose,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    Timeframe,
    TradeDirection,
)


class AsOfPage[ItemT](BaseModel):
    """A cursor page that also states the instant it was read at.

    ``next_cursor`` is ``None`` exactly when there is no further page
    (``hunter_api.schemas.common.CursorPage``'s own contract); ``as_of`` is
    what lets an honestly empty ``items`` read as "nothing exists yet" instead
    of "this call failed silently".
    """

    as_of: datetime
    items: list[ItemT]
    next_cursor: str | None = None


class EquityCurvePointOut(BaseModel):
    """One ``portfolio_equity_snapshots`` row, with its BRL reading (or lack of one).

    ``brl_equity``/``brl_unavailable_reason`` mirror
    ``hunter_core.portfolio.ledger.EquityPoint``: the USDT side of a point is
    always present, and the BRL side is either the equity converted at the
    *observation the point itself was recorded with* or a named reason — never
    today's rate applied to yesterday's point (M3 joint decision, item 1).
    """

    ts: datetime
    resolution: Timeframe
    cash: Decimal
    equity: Decimal
    exposure_notional: Decimal
    exposure_pct: Decimal | None
    unrealized_pnl: Decimal
    realized_pnl_cum: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal | None
    open_positions: int
    fx_observation_id: uuid.UUID | None
    brl_equity: Decimal | None
    brl_unavailable_reason: str | None


class PositionOut(BaseModel):
    """One ``positions`` row. Empty today — no writer exists yet (T3.4/T3.5)."""

    id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    qty: Decimal
    avg_entry_price: Decimal
    mark_price: Decimal | None
    stop_price: Decimal | None
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    status: PositionStatus
    opened_at: datetime
    closed_at: datetime | None


class OrderOut(BaseModel):
    """One ``orders`` row. Empty today — no writer exists yet (T3.4/T3.5)."""

    id: uuid.UUID
    market_id: uuid.UUID
    side: OrderSide
    type: OrderType
    purpose: OrderPurpose
    execution_mode: ExecutionMode
    status: OrderStatus
    qty: Decimal
    price: Decimal | None
    stop_price: Decimal | None
    filled_qty: Decimal
    avg_fill_price: Decimal | None
    created_at: datetime
    completed_at: datetime | None


class PortfolioTradeOut(BaseModel):
    """One ``trades`` row. Empty today — no writer exists yet (T3.4/T3.5)."""

    id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    entry_price: Decimal
    exit_price: Decimal
    qty: Decimal
    fees: Decimal
    pnl: Decimal
    pnl_pct: Decimal | None
    exit_reason: ExitReason | None
    opened_at: datetime
    closed_at: datetime
