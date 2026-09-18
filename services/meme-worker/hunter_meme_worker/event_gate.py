"""The event gate itself (T4.52b-3, plan-T4.52b.md §2/§4): a chain event
(``logsSubscribe``/``accountSubscribe`` of a young mint's bonding-curve PDA)
folded straight into a judged row and, behind ``MEME_EVENT_GATE``, a proposal
— without ever waiting for the next 15-second tick.

**Reuse, not reimplementation.** The row is ``event_gate_rows.build_event_row``
(the last 15-second base row, overridden with the in-memory series); the
judgement is the same ``proposals.evaluate_gate``, the same
``lab_repo.insert_proposals`` (its own ``ON CONFLICT`` is still the last
guard), the same ``LabContext.wake`` and the same per-mint refusal trail
(``lab_fast._trail_row`` + ``lab_trail.write_refusal_trail``) the 15-second
lane already writes through (``event_gate_eval.py``). Nothing here opens a
session to *read*: every input is ``LabContext.caches``, filled by the Lab's
own tick (``lab_fast.fast_gate_step``).

**Shape.** Four concurrent loops share one
``event_gate_runtime.EventGateRuntime``: (1) :func:`_sync_loop` keeps the WS
subscriptions equal to ``fast_lane.young_mints`` every
``subscription_sync_s`` (``event_gate_subscriptions.py``); (2)
:func:`_read_loop` drains ``SolanaWs.listen()`` into a bounded queue,
dropping and marking a coverage gap when it is full (plan §4
"Backpressure") rather than ever blocking the socket reader, and detects a
reconnect; (3) :func:`_evaluate_loop` folds each notification into the
mint's state and evaluates it, debounced per mint (plan's 100 ms); a dirty
mint that arrived less than the debounce window ago is picked up by
:func:`_flush_loop` instead of being dropped. (4) :func:`_heartbeat_loop`
writes ``event_gate_*`` fields onto the same heartbeat hash the Lab uses.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.event_gate_eval import apply_notification, evaluate_mint, handle_reconnect
from hunter_meme_worker.event_gate_runtime import EventGateRuntime
from hunter_meme_worker.event_gate_stats import heartbeat_fields as event_gate_heartbeat_fields
from hunter_meme_worker.event_gate_subscriptions import sync_subscriptions

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification

logger = get_logger(__name__)

HEARTBEAT_CYCLE_S = 5

__all__ = ["EventGateRuntime", "run_event_gate"]


async def _sync_loop(rt: EventGateRuntime) -> None:
    while True:
        try:
            await sync_subscriptions(rt)
        except Exception:  # a sync failure is not a reason to stop the gate
            logger.warning("meme_event_gate_sync_failed")
        await asyncio.sleep(rt.config.subscription_sync_s)


async def _read_loop(rt: EventGateRuntime, queue: asyncio.Queue[Notification]) -> None:
    async for notif in rt.ws.listen():
        now = utcnow()
        if rt.ws.state.reconnects != rt.seen_reconnects:
            await handle_reconnect(rt, now)
        rt.stats.ws_state = rt.ws.state.ws_state
        try:
            queue.put_nowait(notif)
        except asyncio.QueueFull:
            rt.stats.record_dropped(now)
            mint = rt.subs_by_logical.get(notif.subscription_id)
            state = rt.book.get(mint) if mint is not None else None
            if state is not None:
                state.mark_gap(now)


async def _evaluate_loop(rt: EventGateRuntime, queue: asyncio.Queue[Notification]) -> None:
    while True:
        notif = await queue.get()
        now = utcnow()
        mint = apply_notification(rt, notif)
        if mint is None:
            continue
        rt.stats.record_event(now)
        if rt.debouncer.poll(mint, time.monotonic()):
            await evaluate_mint(rt, mint, now)


async def _flush_loop(rt: EventGateRuntime) -> None:
    interval = rt.config.debounce_ms / 1000
    while True:
        await asyncio.sleep(interval)
        for mint in rt.debouncer.drain_ready(time.monotonic()):
            await evaluate_mint(rt, mint, utcnow())


async def _heartbeat_loop(rt: EventGateRuntime) -> None:
    if rt.heartbeat is None:
        return
    while True:
        await asyncio.sleep(HEARTBEAT_CYCLE_S)
        rt.stats.ws_state = rt.ws.state.ws_state
        try:
            await rt.heartbeat(event_gate_heartbeat_fields(rt.stats, now=utcnow(), enabled=True))
        except Exception:  # a heartbeat that cannot be written must not stop the gate
            logger.warning("meme_event_gate_heartbeat_write_failed")


async def run_event_gate(rt: EventGateRuntime) -> None:
    """Restart-safe (plan §4 (iv)): waits for the Lab's own first tick to warm
    ``LabContext.caches`` before a single subscription opens."""
    while rt.lab.caches is None or not rt.lab.caches.specs:  # noqa: ASYNC110 — polling a plain field, not an Event
        await asyncio.sleep(1)
    queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=rt.config.queue_size)
    async with asyncio.TaskGroup() as group:
        group.create_task(_sync_loop(rt), name="meme-event-gate-sync")
        group.create_task(_read_loop(rt, queue), name="meme-event-gate-read")
        group.create_task(_evaluate_loop(rt, queue), name="meme-event-gate-evaluate")
        group.create_task(_flush_loop(rt), name="meme-event-gate-flush")
        group.create_task(_heartbeat_loop(rt), name="meme-event-gate-heartbeat")
