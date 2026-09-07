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

**``kill_switch.changed`` has exactly one shape, the core's.**
``hunter_core.risk.transitions.record_transition`` already enqueues this event
— same transaction as the latch, ``event_id = transition_id`` — whenever a
caller passes ``publish=True``. This module used to publish a *second* event in
its own shape whenever the worker's own MTM cycle moved the latch (T3.5d review
finding 1); that call is gone, and :func:`publish_resumed_transitions` is the
other side of finding 2 — the worker enqueues, in the same shape, the
transitions the API authorised but could not publish itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.events.outbox_event import event_id_for
from hunter_core.events.outbox_store import enqueue
from hunter_core.events.streams import Streams

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.adapter import ExecutionReport
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = [
    "PRODUCER",
    "audit",
    "publish_order_filled",
    "publish_position",
    "publish_resumed_transitions",
]

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


_RESUME_LOOKBACK = timedelta(hours=24)
"""How far back :func:`publish_resumed_transitions` scans. A resume is expected
to reach the outbox within one kill-switch cycle (10 s); a day is headroom for
a worker that was briefly down, kept an index range over
``ix_kill_switch_transitions_scope_created`` rather than a full-table scan."""

_UNPUBLISHED_USER_RESUMES = (
    "SELECT id, organization_id, from_state::text AS from_state, to_state::text AS to_state, "
    "reason, actor_type, evidence, created_at FROM kill_switch_transitions kt "
    "WHERE scope = 'portfolio' AND scope_id = :pf AND actor_type = 'user' "
    "AND created_at >= :cutoff "
    "AND NOT EXISTS (SELECT 1 FROM outbox_events oe WHERE oe.event_id = kt.id) "
    "ORDER BY created_at"
)


async def publish_resumed_transitions(
    session: AsyncSession, *, wallet: WalletRef, now: datetime
) -> int:
    """Enqueue ``kill_switch.changed`` for every user resume the API could not publish.

    ``0007_paper_roles`` denies ``hunter_app`` ``INSERT`` on ``outbox_events``
    by design (SECURITY.md: the API never talks to the transport directly), so
    ``apps/api/hunter_api/routers/risk.py`` calls
    ``hunter_core.risk.resume.resume(..., publish=False)`` — the transition is
    written, audited and the latch moves, but nothing is queued (T3.5d review
    finding 2). This is the other side, run every 10 s
    (:meth:`hunter_execution_worker.cycles.Cycles.kill_switch`): the worker
    looks at this wallet's own ``actor_type='user'`` transitions and enqueues
    the ones with no matching outbox row yet, in **the same shape**
    ``hunter_core.risk.transitions.record_transition`` already uses for an
    automatic move (T3.5d finding 1) — one format, whichever side moved the
    latch.

    Idempotent by construction, not by a cursor kept in memory:
    ``event_id = transition_id``, so ``enqueue``'s own
    ``ON CONFLICT (event_id) DO NOTHING`` makes re-reading an already-queued
    row a no-op, and a process killed between this read and the ``enqueue``
    below simply re-reads and re-queues the same row next cycle — never a
    second transition, never two different shapes.

    **Caveat, documented rather than fixed** (the brief's own words: "decidir e
    documentar"): "not yet published" is tested with ``NOT EXISTS`` against
    ``outbox_events``, durable only until that row is pruned
    (``outbox_store.prune_dispatched`` — 7 days after *dispatch*, DATABASE.md
    §1.3, a job the M3 stack does not yet run anywhere). Only a worker that
    missed every 10 s cycle for that whole week would re-enqueue an
    already-delivered resume under the same ``event_id`` — a redundant, harmless
    redelivery to a consumer that is required to be idempotent by
    ``event_id`` (CLAUDE.md), not a second move of the latch.
    """
    rows = await session.execute(
        text(_UNPUBLISHED_USER_RESUMES),
        {"pf": wallet.portfolio_id, "cutoff": now - _RESUME_LOOKBACK},
    )
    count = 0
    for row in rows:
        await enqueue(
            session,
            Streams.KILL_SWITCH_CHANGED,
            row.id,
            {
                "scope": "portfolio",
                "scope_id": str(wallet.portfolio_id),
                "organization_id": str(row.organization_id),
                "from_state": row.from_state,
                "to_state": row.to_state,
                "reason": row.reason,
                "actor_type": row.actor_type,
                "evidence": row.evidence,
            },
            producer=PRODUCER,
            key=str(wallet.portfolio_id),
            ts=row.created_at,
        )
        count += 1
    return count


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
