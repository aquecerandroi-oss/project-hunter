"""Applying one protection attempt to the ledger — the whole effect, or none.

The other half of :mod:`hunter_execution_worker.apply`, split from it because
the two are genuinely different acts: an entry *opens* a position and arms the
protection that must exist before it does; an exit *reduces* one, folds the
attempt into the durable intention, and settles the trade when nothing sellable
is left. The shared row writers live in :mod:`hunter_execution_worker.rows`.

Idempotency is the schema's, not a flag: ``insert_order`` returns ``None`` when
``uq_orders_client_order_id`` already holds ``exit:{attempt_id}``, and everything
after it is skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.enums import ExitReason, OrderPurpose
from hunter_core.execution.intents import ExitIntent, apply_attempt, void_intent
from hunter_core.execution.pricing import untradable_reason
from hunter_core.logging import get_logger
from hunter_execution_worker import events
from hunter_execution_worker.booking import book_fill
from hunter_execution_worker.intents_repo import live_intents, save_intent
from hunter_execution_worker.positions import OpenPositionRow, close_position, reduce_position
from hunter_execution_worker.rows import insert_fill, insert_order

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.adapter import ExecutionReport
    from hunter_core.execution.intents import ExitAttempt
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["ExitApplication", "apply_exit"]

logger = get_logger(__name__)
_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class ExitApplication:
    """What applying one protection attempt did."""

    execution_key: str
    status: str
    replayed: bool
    filled_qty: Decimal
    order_id: uuid.UUID | None = None
    fill_id: uuid.UUID | None = None
    position_closed: bool = False
    """The position holds nothing sellable any more — zero, or only dust."""
    intent: ExitIntent | None = None


async def apply_exit(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    attempt: ExitAttempt,
    report: ExecutionReport,
    position: OpenPositionRow,
    now: datetime,
    source: str,
) -> ExitApplication:
    """Book one protection attempt, and let the intention outlive it."""
    booking = book_fill(report)
    intent = attempt.intent
    order_id = await insert_order(
        session,
        wallet=wallet,
        market=market,
        report=report,
        purpose=_exit_purpose(intent.reason),
        now=now,
        position_id=position.position_id,
        exit_intent_id=intent.intent_id,
        booking=booking,
    )
    if order_id is None:
        logger.info("exit_report_replayed", execution_key=report.execution_key)
        return ExitApplication(report.execution_key, report.status, True, _ZERO)

    fill_id: uuid.UUID | None = None
    closed = False
    realized: Decimal | None = None
    if report.filled_qty > 0:
        fill_id = await insert_fill(
            session,
            wallet=wallet,
            order_id=order_id,
            market=market,
            report=report,
            booking=booking,
            now=now,
            source=source,
        )
        fee_quote = (
            report.fee.qty if report.fee is not None and report.fee.asset == "quote" else _ZERO
        )
        leftover = position.qty - report.filled_qty
        dust = leftover > _ZERO and (
            untradable_reason(leftover, market.filters, booking.price) is not None
        )
        reduction = await reduce_position(
            session,
            wallet=wallet,
            position=position,
            qty=report.filled_qty,
            exit_price=booking.price,
            fees_quote=fee_quote,
            now=now,
            dust=dust,
        )
        realized, closed = reduction.realized_pnl, reduction.settled
        if reduction.settled:
            await close_position(
                session,
                wallet=wallet,
                market=market,
                position=position,
                reduction=reduction,
                exit_reason=intent.reason,
                now=now,
            )
    updated = apply_attempt(
        intent,
        report,
        now=now,
        min_qty=market.filters.effective_min_qty,
        min_notional=market.filters.min_notional,
        valuation_price=booking.price if report.filled_qty > 0 else None,
    )
    await save_intent(session, wallet=wallet, intent=updated)
    if closed:
        await _void_the_other_protections(
            session, wallet=wallet, position=position, keep=intent.intent_id, now=now
        )
    await events.audit(
        session,
        wallet=wallet,
        action="execution.exit_filled" if report.filled_qty > 0 else "execution.exit_pending",
        entity_type="portfolio_exit_intent",
        entity_id=str(intent.intent_id),
        after={
            "execution_key": report.execution_key,
            "filled_qty": str(report.filled_qty),
            "price": str(booking.price) if report.filled_qty > 0 else None,
            "state": updated.state.value,
            "degraded": report.degraded,
            "reason": report.reason,
            "slippage_vs_plan_quote": (
                str(report.slippage_vs_plan_quote)
                if report.slippage_vs_plan_quote is not None
                else None
            ),
        },
        metadata={
            "attempt_id": str(attempt.attempt_id),
            "order_id": str(order_id),
            "fill_id": str(fill_id) if fill_id else None,
            "position_id": str(position.position_id),
            "position_closed": closed,
            "market_data_source": source,
        },
        ts=now,
    )
    await events.publish_order_filled(
        session,
        wallet=wallet,
        market=market,
        report=report,
        order_id=order_id,
        fill_id=fill_id,
        booked_price=booking.price,
        ts=now,
    )
    if report.filled_qty > 0:
        await events.publish_position(
            session,
            wallet=wallet,
            market=market,
            position_id=position.position_id,
            event=events.POSITION_CLOSED if closed else events.POSITION_REDUCED,
            qty=position.qty - report.filled_qty,
            avg_entry_price=position.avg_entry_price,
            realized_pnl=realized,
            execution_key=report.execution_key,
            ts=now,
        )
    return ExitApplication(
        execution_key=report.execution_key,
        status=report.status,
        replayed=False,
        filled_qty=report.filled_qty,
        order_id=order_id,
        fill_id=fill_id,
        position_closed=closed,
        intent=updated,
    )


def _exit_purpose(reason: ExitReason) -> OrderPurpose:
    if reason is ExitReason.STOP:
        return OrderPurpose.STOP
    if reason is ExitReason.TARGET:
        return OrderPurpose.TARGET
    return OrderPurpose.EXIT


async def _void_the_other_protections(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    position: OpenPositionRow,
    keep: uuid.UUID,
    now: datetime,
) -> None:
    """A protection whose quantity another one liquidated ends ``voided``.

    Never ``fulfilled`` with a fill that did not happen: the database's
    ``fulfilled = (filled_qty = intended_qty)`` biconditional exists precisely so
    that shortcut is unrepresentable (DATABASE.md §18.4).
    """
    for other in await live_intents(session, wallet=wallet, position_id=position.position_id):
        if other.intent_id == keep:
            continue
        await save_intent(
            session,
            wallet=wallet,
            intent=void_intent(
                other, now=now, reason="the position was closed by a competing protection"
            ),
        )
