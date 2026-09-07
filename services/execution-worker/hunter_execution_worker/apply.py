"""Applying one **entry** report to the ledger — the whole effect, or none.

``hunter_core.execution`` computes and never writes a balance (notes-T3.4.md
§1); this is the other half. One report becomes, **in one transaction under the
wallet's lock**: the ``orders`` row, the ``fills`` row carrying the execution
key, the position's net quantity, the participation the fill really consumed,
the durable protection that must exist before the position does, the audit row
and the outbox event.

Idempotency is the schema's, not a flag: ``insert_order`` returns ``None`` when
``uq_orders_client_order_id`` already holds ``entry:{proposal_id}`` /
``exit:{attempt_id}``, and everything after it is skipped. A redelivered report
therefore writes nothing and moves no cash — which is the property V4 of
``spec-T3.9-verificacoes.md`` asks to be proved byte for byte.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.enums import ExitReason, OrderPurpose
from hunter_core.logging import get_logger
from hunter_execution_worker import events
from hunter_execution_worker.apply_exit import ExitApplication as ExitApplication  # re-export
from hunter_execution_worker.apply_exit import apply_exit as apply_exit  # re-export
from hunter_execution_worker.booking import book_fill
from hunter_execution_worker.intents_repo import insert_intent
from hunter_execution_worker.positions import open_position
from hunter_execution_worker.rows import (
    insert_fill,
    insert_order,
    record_execution_consumption,
    settle_order,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.adapter import ExecutionReport
    from hunter_core.execution.entries import MarketEntryOrder
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["EntryApplication", "ExitApplication", "apply_entry", "apply_exit"]
"""``ExitApplication``/``apply_exit`` are **re-exported**, not defined here: a
module split that breaks an import is a refactor that broke something."""

logger = get_logger(__name__)
_ZERO = Decimal(0)
STOP_PROTECTION_KEY = "stop"


@dataclass(frozen=True, slots=True)
class EntryApplication:
    """What applying one entry report did — or that it had already been done."""

    execution_key: str
    status: str
    replayed: bool
    filled_qty: Decimal
    order_id: uuid.UUID | None = None
    fill_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    intent_id: uuid.UUID | None = None


async def apply_entry(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    order: MarketEntryOrder,
    report: ExecutionReport,
    now: datetime,
    source: str,
) -> EntryApplication:
    """Book one entry attempt: order, fill, position, budget, protection, event."""
    booking = book_fill(report)
    order_id = await insert_order(
        session,
        wallet=wallet,
        market=market,
        report=report,
        purpose=OrderPurpose.ENTRY,
        now=now,
        proposal_id=order.proposal_id,
        booking=booking,
    )
    if order_id is None:
        logger.info("entry_report_replayed", execution_key=report.execution_key)
        return EntryApplication(report.execution_key, report.status, True, _ZERO)

    if report.filled_qty <= 0:
        await events.audit(
            session,
            wallet=wallet,
            action="execution.entry_refused",
            entity_type="order",
            entity_id=str(order_id),
            after={"execution_key": report.execution_key, "reason": report.reason},
            metadata={"proposal_id": str(order.proposal_id), "status": report.status},
            ts=now,
        )
        await events.publish_order_filled(
            session,
            wallet=wallet,
            market=market,
            report=report,
            order_id=order_id,
            fill_id=None,
            booked_price=booking.price,
            ts=now,
        )
        return EntryApplication(report.execution_key, report.status, False, _ZERO, order_id)

    net_qty = report.net_base_delta
    fees_quote = (
        report.fee.quote_equivalent or _ZERO
        if report.fee is not None and report.fee.asset == "base"
        else (report.fee.qty if report.fee is not None else _ZERO)
    )
    position_id = await open_position(
        session,
        wallet=wallet,
        market=market,
        qty=net_qty,
        entry_price=booking.price,
        stop_price=order.stop,
        fees_quote=fees_quote,
        now=now,
        proposal_id=order.proposal_id,
    )
    await settle_order(session, wallet=wallet, order_id=order_id, position_id=position_id)
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
    if fill_id is None:  # pragma: no cover - the order key already arbitrated this
        raise RuntimeError(
            f"order {report.client_order_id} was inserted but its execution key "
            f"{report.execution_key} already exists: the two identities disagree"
        )
    await record_execution_consumption(
        session,
        wallet=wallet,
        market=market,
        proposal_id=order.proposal_id,
        order_id=order_id,
        fill_id=fill_id,
        notional=booking.gross,
        occurred_at=report.executed_at or now,
    )
    # The protection is written **before** this transaction can commit: a
    # position that exists without a durable stop, even for one commit, is the
    # failure the intention/attempt split exists to prevent.
    intent = await insert_intent(
        session,
        wallet=wallet,
        market=market,
        position_id=position_id,
        protection_key=STOP_PROTECTION_KEY,
        reason=ExitReason.STOP,
        intended_qty=net_qty,
        trigger_price=order.stop,
        now=now,
    )
    await events.audit(
        session,
        wallet=wallet,
        action="execution.entry_filled",
        entity_type="position",
        entity_id=str(position_id),
        after={
            "execution_key": report.execution_key,
            "filled_qty": str(report.filled_qty),
            "net_qty": str(net_qty),
            "price": str(booking.price),
            "gross_quote": str(booking.gross),
            "booking_residual_quote": str(booking.residual),
            "fee_qty": str(report.fee.qty) if report.fee else "0",
            "stop_price": str(order.stop),
        },
        metadata={
            "proposal_id": str(order.proposal_id),
            "order_id": str(order_id),
            "fill_id": str(fill_id),
            "intent_id": str(intent.intent_id),
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
    await events.publish_position(
        session,
        wallet=wallet,
        market=market,
        position_id=position_id,
        event=events.POSITION_OPENED,
        qty=net_qty,
        avg_entry_price=booking.price,
        realized_pnl=None,
        execution_key=report.execution_key,
        ts=now,
    )
    return EntryApplication(
        execution_key=report.execution_key,
        status=report.status,
        replayed=False,
        filled_qty=report.filled_qty,
        order_id=order_id,
        fill_id=fill_id,
        position_id=position_id,
        intent_id=intent.intent_id,
    )
