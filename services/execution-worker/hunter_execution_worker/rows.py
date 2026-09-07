"""The durable rows one execution writes: the order, the fill, the budget entry.

Every writer here runs **inside the caller's transaction**, under the wallet's
lock, and every one of them is idempotent by the key the schema already
arbitrates: ``uq_orders_client_order_id`` for the attempt,
``uq_fills_execution_key`` for the execution and ``uq_participation_executed``
for the budget entry. A redelivered report therefore inserts nothing and moves
no money — the guarantee is the unique index, not a check somebody can forget.

The number each of them is booked at is :mod:`hunter_execution_worker.booking`'s
question, not this module's.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.enums import (
    ExecutionMode,
    OrderPurpose,
    OrderSide,
    OrderStatus,
    ParticipationEntryKind,
)
from hunter_core.domain.types import uuid7
from hunter_execution_worker.booking import Booking, fill_metadata

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.adapter import ExecutionReport
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = [
    "insert_fill",
    "insert_order",
    "record_execution_consumption",
    "settle_order",
]

_ZERO = Decimal(0)


async def insert_order(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    report: ExecutionReport,
    purpose: OrderPurpose,
    now: datetime,
    proposal_id: uuid.UUID | None = None,
    position_id: uuid.UUID | None = None,
    exit_intent_id: uuid.UUID | None = None,
    booking: Booking,
) -> uuid.UUID | None:
    """The attempt. ``None`` when this ``client_order_id`` was already written.

    That ``None`` **is** the idempotency of the whole application: a redelivered
    report finds ``uq_orders_client_order_id`` taken and nothing after this point
    runs (RISK_ENGINE.md §10; ``entry:{proposal_id}`` and ``exit:{attempt_id}``
    are derived, never random).
    """
    order_id = uuid7()
    inserted = await session.scalar(
        text(
            "INSERT INTO orders (id, organization_id, portfolio_id, proposal_id, exit_intent_id, "
            "market_id, position_id, client_order_id, side, type, purpose, qty, stop_price, "
            "execution_mode, status, filled_qty, avg_fill_price, fees_paid, submitted_at, "
            "completed_at, reason, metadata) VALUES (:id, :org, :pf, :proposal, :intent, "
            ":market, :position, :client, :side, 'market', :purpose, :qty, :stop, 'paper', "
            ":status, :filled, :avg, :fees, :now, :now, :reason, CAST(:meta AS jsonb)) "
            "ON CONFLICT (portfolio_id, client_order_id) DO NOTHING RETURNING id"
        ),
        {
            "id": order_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "proposal": proposal_id,
            "intent": exit_intent_id,
            "market": market.market_id,
            "position": position_id,
            "client": report.client_order_id,
            "side": report.side.value,
            "purpose": purpose.value,
            "qty": _submitted_qty(report),
            "stop": report.planned_price,
            "status": _order_status(report).value,
            "filled": report.filled_qty,
            "avg": booking.price if report.filled_qty > 0 else None,
            "fees": _fee_in_quote(report),
            "now": now,
            "reason": report.reason or None,
            "meta": json.dumps({"execution_key": report.execution_key, "status": report.status}),
        },
    )
    return None if inserted is None else order_id


def _submitted_qty(report: ExecutionReport) -> Decimal:
    """What the attempt asked for — ``orders.qty``, which is always positive.

    ``requested_qty`` is **post-filter**: a leftover of 0,000482 under a step of
    0,001 rounds to zero, and writing that would violate ``ck_orders_qty_positive``
    and lose the fact that an attempt was made at all. ``submitted_qty`` is what
    the caller submitted before the filters touched it (T3.4b), which is the
    honest content of the column.
    """
    for candidate in (report.submitted_qty, report.requested_qty, report.filled_qty):
        if candidate is not None and candidate > _ZERO:
            return candidate
    raise ValueError(
        f"attempt {report.execution_key} carries no positive quantity at all; an order row would "
        "claim an attempt for nothing"
    )


def _order_status(report: ExecutionReport) -> OrderStatus:
    """The report's own status, in the vocabulary ``orders`` speaks.

    ``pending_degraded`` maps to ``submitted``: the attempt really was made and
    found nothing to fill against, and calling it ``rejected`` would read as a
    refusal by the venue (the intention stays open and degraded instead).
    """
    if report.status == "filled":
        return OrderStatus.FILLED
    if report.status == "partially_filled":
        return OrderStatus.PARTIALLY_FILLED
    if report.status == "rejected":
        return OrderStatus.REJECTED
    return OrderStatus.SUBMITTED


def _fee_in_quote(report: ExecutionReport) -> Decimal:
    """The fee expressed in the operating currency, for display only.

    A base-asset fee is already inside ``net_base_delta``; its
    ``quote_equivalent`` is informational and is **never** booked as cash
    (``adapter.py``: "booking it as well would charge the trade twice").
    """
    fee = report.fee
    if fee is None:
        return _ZERO
    if fee.asset == "quote":
        return fee.qty
    return fee.quote_equivalent or _ZERO


async def insert_fill(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    order_id: uuid.UUID,
    market: MarketReference,
    report: ExecutionReport,
    booking: Booking,
    now: datetime,
    source: str,
) -> uuid.UUID | None:
    """The execution. ``None`` when ``uq_fills_execution_key`` already has it."""
    fill_id = uuid7()
    fee = report.fee
    fee_asset = None
    if fee is not None and fee.qty > 0:
        fee_asset = (
            market.identity.quote_asset if fee.asset == "quote" else market.identity.base_asset
        )
    inserted = await session.scalar(
        text(
            "INSERT INTO fills (id, organization_id, portfolio_id, order_id, execution_key, ts, "
            "qty, price, fee, fee_asset, liquidity, slippage_bps, simulated, book_snapshot, "
            "metadata) VALUES (:id, :org, :pf, :order, :key, :ts, :qty, :price, :fee, :fee_asset, "
            "'taker', :slippage, true, CAST(:levels AS jsonb), CAST(:meta AS jsonb)) "
            "ON CONFLICT (organization_id, execution_key) DO NOTHING RETURNING id"
        ),
        {
            "id": fill_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "order": order_id,
            "key": report.execution_key,
            "ts": report.executed_at or now,
            "qty": report.filled_qty,
            "price": booking.price,
            "fee": fee.qty if fee is not None else _ZERO,
            "fee_asset": fee_asset,
            "slippage": report.slippage_vs_plan_bps,
            "levels": json.dumps(
                [{"price": str(level.price), "qty": str(level.qty)} for level in report.levels]
            ),
            "meta": json.dumps(fill_metadata(report, booking, source)),
        },
    )
    return None if inserted is None else fill_id


async def settle_order(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    order_id: uuid.UUID,
    position_id: uuid.UUID | None,
) -> None:
    """Point the attempt at the position it moved, once that position exists."""
    if position_id is None:
        return
    await session.execute(
        text(
            "UPDATE orders SET position_id = :position WHERE id = :id "
            "AND organization_id = :org AND portfolio_id = :pf"
        ),
        {
            "position": position_id,
            "id": order_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
        },
    )


async def record_execution_consumption(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    proposal_id: uuid.UUID,
    order_id: uuid.UUID,
    fill_id: uuid.UUID,
    notional: Decimal,
    occurred_at: datetime,
) -> None:
    """Charge the market's 60 s participation budget for what really executed.

    ``occurred_at`` is the **fill's** instant, never now: the rolling window is
    keyed on when the effect happened, so a retry cannot slide it forward
    (DATABASE.md §18.5). Unique per ``fill_id``, so a redelivery spends nothing.
    """
    if notional <= 0:
        return
    await session.execute(
        text(
            "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
            "market_id, proposal_id, order_id, fill_id, kind, notional, occurred_at) "
            "VALUES (:id, :org, :pf, :market, :proposal, :order, :fill, :kind, :notional, :at) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "id": uuid7(),
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "market": market.market_id,
            "proposal": proposal_id,
            "order": order_id,
            "fill": fill_id,
            "kind": ParticipationEntryKind.EXECUTED.value,
            "notional": notional,
            "at": occurred_at,
        },
    )


def entry_purpose(side: OrderSide) -> OrderPurpose:
    """Only spot longs exist in M3, so a buy is an entry and a sell is an exit."""
    return OrderPurpose.ENTRY if side is OrderSide.BUY else OrderPurpose.EXIT


def execution_mode() -> ExecutionMode:
    """Paper, always. ``LiveExecutionAdapter`` refuses to exist (T3.4 §9)."""
    return ExecutionMode.PAPER
