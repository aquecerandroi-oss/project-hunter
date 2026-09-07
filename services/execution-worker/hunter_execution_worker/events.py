"""What an execution announces, and where it is written down.

Two rules, both from the M3 joint decision (item 4): the event is queued in the
**existing outbox** inside the transaction that made it true — never a third
queue and never a network call under the wallet's lock — and every meaningful
mutation is audited (CLAUDE.md).

**Stream names, declared.** ``docs/PIPELINE.md`` §10 (and
``hunter_core.events.streams.Streams``) publishes ``executions.completed`` and
``positions.updated``; the T3.5 brief names ``orders.filled`` and
``positions.opened``. Coining two new streams would mean editing
``packages/core`` — out of this task's file scope — and, more to the point, a
stream name is a contract with consumers that PIPELINE.md owns. So the two
events travel on the canonical streams with an explicit ``event`` field naming
which one they are, and a consumer filters on that. Registered as a deviation in
``.claude/state/notes-T3.5.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.events.outbox_event import event_id_for
from hunter_core.events.outbox_store import enqueue
from hunter_core.events.streams import Streams

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.adapter import ExecutionReport
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["PRODUCER", "audit", "publish_order_filled", "publish_position", "publish_kill_switch"]

PRODUCER = "execution-worker"

ORDER_FILLED = "orders.filled"
POSITION_OPENED = "positions.opened"
POSITION_REDUCED = "positions.reduced"
POSITION_CLOSED = "positions.closed"
KILL_SWITCH_CHANGED = "kill_switch.changed"


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


async def publish_order_filled(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    report: ExecutionReport,
    order_id: uuid.UUID,
    fill_id: uuid.UUID | None,
    booked_price: Decimal,
    ts: datetime,
) -> None:
    """``executions.completed`` — one event per attempt, identified by its key."""
    payload: dict[str, Any] = {
        "event": ORDER_FILLED,
        "organization_id": str(wallet.organization_id),
        "portfolio_id": str(wallet.portfolio_id),
        "market_id": str(market.market_id),
        "market": market.identity.model_dump(mode="json"),
        "order_id": str(order_id),
        "fill_id": str(fill_id) if fill_id else None,
        "execution_key": report.execution_key,
        "client_order_id": report.client_order_id,
        "kind": report.kind,
        "side": report.side.value,
        "status": report.status,
        "filled_qty": str(report.filled_qty),
        "price": _money(booked_price if report.filled_qty > 0 else None),
        "gross_quote": _money(report.gross_quote),
        "fee_qty": _money(report.fee.qty) if report.fee else None,
        "fee_asset": report.fee.asset if report.fee else None,
        "degraded": report.degraded,
        "alert": report.alert,
        "reason": report.reason,
        "slippage_vs_plan_bps": _money(report.slippage_vs_plan_bps),
        "ts": ts.isoformat(),
    }
    await enqueue(
        session,
        Streams.EXECUTIONS_COMPLETED,
        event_id_for(Streams.EXECUTIONS_COMPLETED, wallet.organization_id, report.execution_key),
        payload,
        producer=PRODUCER,
        key=str(wallet.portfolio_id),
        ts=ts,
    )


async def publish_position(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    position_id: uuid.UUID,
    event: str,
    qty: Decimal,
    avg_entry_price: Decimal,
    realized_pnl: Decimal | None,
    execution_key: str,
    ts: datetime,
) -> None:
    """``positions.updated`` — opened, reduced or closed, said by name."""
    payload: dict[str, Any] = {
        "event": event,
        "organization_id": str(wallet.organization_id),
        "portfolio_id": str(wallet.portfolio_id),
        "market_id": str(market.market_id),
        "position_id": str(position_id),
        "qty": str(qty),
        "avg_entry_price": str(avg_entry_price),
        "realized_pnl": _money(realized_pnl),
        "execution_key": execution_key,
        "ts": ts.isoformat(),
    }
    await enqueue(
        session,
        Streams.POSITIONS_UPDATED,
        event_id_for(Streams.POSITIONS_UPDATED, wallet.organization_id, event, execution_key),
        payload,
        producer=PRODUCER,
        key=str(wallet.portfolio_id),
        ts=ts,
    )


async def publish_kill_switch(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    previous: str,
    latched: str,
    effective: str,
    reason: str,
    ts: datetime,
) -> None:
    """``kill_switch.changed`` — the reaction the contract asks for in < 1 s.

    Published by the **worker**, which is the only role that may
    (``0007_paper_roles`` §19.6: the engine moves the latch and enqueues the
    event in one transaction; the API's resume still cannot, deliberately).
    """
    payload = {
        "event": KILL_SWITCH_CHANGED,
        "organization_id": str(wallet.organization_id),
        "portfolio_id": str(wallet.portfolio_id),
        "scope": "portfolio",
        "previous": previous,
        "state": latched,
        "effective": effective,
        "reason": reason,
        "ts": ts.isoformat(),
    }
    await enqueue(
        session,
        Streams.KILL_SWITCH_CHANGED,
        event_id_for(Streams.KILL_SWITCH_CHANGED, wallet.portfolio_id, latched, ts.isoformat()),
        payload,
        producer=PRODUCER,
        key=str(wallet.portfolio_id),
        ts=ts,
    )


async def audit(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    action: str,
    entity_type: str,
    entity_id: str,
    after: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    ts: datetime,
) -> None:
    """One append-only audit row, in the transaction that made the change true."""
    await SqlAuditSink(session).record(
        AuditEvent(
            actor_type="system",
            actor_id=PRODUCER,
            organization_id=wallet.organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            after=after,
            metadata=metadata or {},
            ts=ts,
        )
    )
