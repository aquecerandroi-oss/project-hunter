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

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr
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
    cash: DecimalStr
    equity: DecimalStr
    exposure_notional: DecimalStr
    exposure_pct: DecimalStr | None
    unrealized_pnl: DecimalStr
    realized_pnl_cum: DecimalStr
    peak_equity: DecimalStr
    drawdown_pct: DecimalStr | None
    open_positions: int
    fx_observation_id: uuid.UUID | None
    brl_equity: DecimalStr | None
    brl_unavailable_reason: str | None


class PositionOut(BaseModel):
    """One ``positions`` row. Empty today — no writer exists yet (T3.4/T3.5)."""

    id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    qty: DecimalStr
    avg_entry_price: DecimalStr
    mark_price: DecimalStr | None
    stop_price: DecimalStr | None
    unrealized_pnl: DecimalStr
    realized_pnl: DecimalStr
    fees_paid: DecimalStr
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
    qty: DecimalStr
    price: DecimalStr | None
    stop_price: DecimalStr | None
    filled_qty: DecimalStr
    avg_fill_price: DecimalStr | None
    created_at: datetime
    completed_at: datetime | None


class PortfolioTradeOut(BaseModel):
    """One ``trades`` row. Empty today — no writer exists yet (T3.4/T3.5)."""

    id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    entry_price: DecimalStr
    exit_price: DecimalStr
    qty: DecimalStr
    fees: DecimalStr
    pnl: DecimalStr
    pnl_pct: DecimalStr | None
    exit_reason: ExitReason | None
    opened_at: datetime
    closed_at: datetime
