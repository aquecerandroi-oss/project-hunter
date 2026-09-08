"""Equity curve, positions, orders and trades — the lists T3.8a can show today.

``positions``/``orders``/``trades`` are real, cursor-paginated reads of tables
the execution worker writes (T3.4/T3.5 landed after this module's original
docstring was written) — an empty page still reads honestly as "nothing
happened yet" for a wallet that never traded. ``as_of`` on every page is the
instant the read was taken.

T3.25 adds what the Trades page promises beyond the bare row: fees and
realized PnL in both currencies (``_brl`` fields, ``None`` with a reason when
no FX observation covers ``closed_at`` — never extrapolated, the same
convention ``PortfolioSummaryOut.brl`` uses), the entry/exit feature snapshot
(PRODUCT.md §8, "snapshot de features na entrada e saída"), and the position's
protection intents (``portfolio_exit_intents``, DATABASE.md §18.4) — a
protection is not the same thing as any single attempt at it, and the page
that shows a stop needs to show what it actually did, not just the last order.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr
from hunter_core.domain.enums import (
    ExecutionMode,
    ExitIntentState,
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


class ExitIntentOut(BaseModel):
    """One ``portfolio_exit_intents`` row — a protection's durable identity,
    distinct from any single attempt at it (RISK_ENGINE.md §10, DATABASE.md §18.4)."""

    id: uuid.UUID
    reason: ExitReason
    protection_key: str
    state: ExitIntentState
    intended_qty: DecimalStr
    filled_qty: DecimalStr
    trigger_price: DecimalStr | None
    degraded_since: datetime | None
    degraded_reason: str | None
    closed_reason: str | None
    created_at: datetime
    closed_at: datetime | None


class PositionOut(BaseModel):
    """One ``positions`` row, with the protections currently held on it."""

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
    protection_intents: list[ExitIntentOut]


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
    """One ``trades`` row — entry/exit, fees and PnL in both currencies, the
    feature snapshot at entry and exit, and the protections that were live on
    the position this trade closed."""

    id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    entry_price: DecimalStr
    exit_price: DecimalStr
    qty: DecimalStr
    fees: DecimalStr
    """In the wallet's operating currency (USDT)."""
    fees_brl: DecimalStr | None
    fees_brl_unavailable_reason: str | None
    pnl: DecimalStr
    """Realized PnL in USDT."""
    pnl_brl: DecimalStr | None
    pnl_brl_unavailable_reason: str | None
    pnl_pct: DecimalStr | None
    exit_reason: ExitReason | None
    entry_snapshot: dict[str, Any]
    exit_snapshot: dict[str, Any]
    protection_intents: list[ExitIntentOut]
    opened_at: datetime
    closed_at: datetime
