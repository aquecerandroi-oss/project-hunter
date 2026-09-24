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

**Shape.** Eight concurrent loops share one
``event_gate_runtime.EventGateRuntime``: (1) :func:`_sync_loop` keeps the WS
subscriptions equal to ``fast_lane.young_mints`` every
``subscription_sync_s`` (``event_gate_subscriptions.py``), which also prunes
the caches and the debouncer (F1); (2) :func:`_read_loop` drains
``SolanaWs.listen()`` into a bounded queue, dropping and marking a coverage
gap when it is full (plan §4 "Backpressure") rather than ever blocking the
socket reader, and detects a reconnect — ``listen()`` itself never raises
(``rpc_ws.py``'s own F2 fix: unlimited backoff, never a crash); (3)
:func:`_evaluate_loop` folds each notification into the mint's state and
evaluates it, debounced per mint (plan's 100 ms); a dirty mint that arrived
less than the debounce window ago is picked up by :func:`_flush_loop`
instead of being dropped. (4) :func:`_heartbeat_loop` writes ``event_gate_*``
fields (including cache sizes, F1) onto the same heartbeat hash the Lab
uses. (5) :func:`_slot_subscribe_loop` subscribes once to ``slotSubscribe``
so ``rt.slot`` is set (``event_to_proposal_s``, metrics §5) and the
connection is never idle with zero subscriptions (F2). (6)
:func:`_trail_flush_loop` writes the per-mint refusal trail queued by
``event_gate_eval.py`` at most once a minute per mint (F6/F7). (7) since
T4.89, :func:`_tape_flush_loop` writes the decision tapes the evaluations
offered (``decision_tape_writer.py``) and prunes them once a UTC day. (8)
since T4.91, :func:`_pullback_loop` expires the mints armed for their
pullback and writes their outcome rows (``event_gate_pullback.py``); the
trigger itself fires in :func:`_evaluate_loop`, before the debounce.

:func:`run_event_gate_forever` (F2) is what ``main.py`` actually runs: any
exception out of :func:`run_event_gate` — including one that killed its own
``TaskGroup`` — is logged and the whole gate restarts after 5 s, so the
15-second lane's own ``TaskGroup`` in ``main.py`` never sees it.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.event_gate_eval import (
    apply_notification,
    evaluate_mint,
    flush_pending_trail,
    handle_reconnect,
)
from hunter_meme_worker.event_gate_pullback import (
    expire_pullbacks,
    fire_pullbacks,
    flush_pullback_trail,
)
from hunter_meme_worker.event_gate_runtime import EventGateRuntime
from hunter_meme_worker.event_gate_stats import heartbeat_fields as event_gate_heartbeat_fields
from hunter_meme_worker.event_gate_subscriptions import sync_subscriptions

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification

logger = get_logger(__name__)

HEARTBEAT_CYCLE_S = 5
TRAIL_FLUSH_CYCLE_S = 15
TAPE_FLUSH_CYCLE_S = 2
PULLBACK_CYCLE_S = 1
RESTART_DELAY_S = 5

__all__ = ["EventGateRuntime", "run_event_gate", "run_event_gate_forever"]


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


def _log_bad_frame(rt: EventGateRuntime, event: str, exc: Exception, *, mint: str | None) -> None:
    """S-T4.62 MEDIUM: a single bad notification/evaluation must never kill
    the gate's own ``TaskGroup`` — counted and logged, the loop continues."""
    rt.stats.record_bad_frame()
    logger.warning(event, mint=mint, error_type=type(exc).__name__, error=str(exc))


async def _evaluate_loop(rt: EventGateRuntime, queue: asyncio.Queue[Notification]) -> None:
    while True:
        notif = await queue.get()
        now = utcnow()
        try:
            mint = apply_notification(rt, notif)
        except Exception as exc:  # a malformed frame is dropped, not a crash
            _log_bad_frame(rt, "meme_event_gate_bad_frame", exc, mint=None)
            continue
        rt.pullback.mark_processed(notif.received_at)  # T4.91: the FIFO proof of an expiry
        if mint is None:
            continue
        rt.stats.record_event(now)
        if rt.pullback.is_armed(mint):  # T4.91: the trade is the trigger - never debounced
            try:  # decided here, inserted by ``rt.pullback_inserts`` - this loop never waits
                fire_pullbacks(rt, mint, max(utcnow(), now + timedelta(microseconds=1)))
            except Exception as exc:
                _log_bad_frame(rt, "meme_event_gate_pullback_failed", exc, mint=mint)
        if rt.debouncer.poll(mint, time.monotonic()):
            try:
                await evaluate_mint(rt, mint, now)
            except Exception as exc:  # a bad row/spec must not stop the gate
                _log_bad_frame(rt, "meme_event_gate_evaluate_failed", exc, mint=mint)


async def _flush_loop(rt: EventGateRuntime) -> None:
    interval = rt.config.debounce_ms / 1000
    while True:
        await asyncio.sleep(interval)
        for mint in rt.debouncer.drain_ready(time.monotonic()):
            try:
                await evaluate_mint(rt, mint, utcnow())
            except Exception as exc:  # a bad row/spec must not stop the gate
                _log_bad_frame(rt, "meme_event_gate_evaluate_failed", exc, mint=mint)


async def _trail_flush_loop(rt: EventGateRuntime) -> None:
    """F6/F7: the periodic half of the refusal-trail batching — a mint whose
    evaluation queued a candidate but never opened a session (no insert) is
    still written, at most once a minute, here rather than never."""
    while True:
        await asyncio.sleep(TRAIL_FLUSH_CYCLE_S)
        try:
            await flush_pending_trail(rt, utcnow())
        except Exception:  # a flush failure is not a reason to stop the gate
            logger.warning("meme_event_gate_trail_flush_failed")


async def _tape_flush_loop(rt: EventGateRuntime) -> None:
    """T4.89: the background half of the decision tapes — the writer never
    raises (a failed batch is counted), so this loop never stops the gate."""
    while True:
        await asyncio.sleep(TAPE_FLUSH_CYCLE_S)
        await rt.tapes.flush(rt.lab.session_factory)
        await rt.tapes.maybe_prune(rt.lab.session_factory, utcnow())


async def _pullback_loop(rt: EventGateRuntime) -> None:
    """T4.91: expire the armed mints whose window is over, write the outcome
    rows — a failure is logged, never a reason to stop the gate."""
    while True:
        await asyncio.sleep(PULLBACK_CYCLE_S)
        try:
            expire_pullbacks(rt, utcnow())
            await flush_pullback_trail(rt)
        except Exception as exc:
            logger.warning("meme_event_gate_pullback_loop_failed", error=str(exc))


async def _slot_subscribe_loop(rt: EventGateRuntime) -> None:
    """Metrics §5: ``slotSubscribe`` once, retried until it sticks — sets
    ``rt.slot`` (``event_to_proposal_s``) and keeps at least one subscription
    alive at all times so the WS is never idle with zero of them (F2,
    ``rpc_ws.py``'s own idle-timeout skip is the other half)."""
    while True:
        try:
            await rt.ws.subscribe_slot()
            return
        except Exception:
            logger.warning("meme_event_gate_slot_subscribe_failed")
            await asyncio.sleep(5)


async def _heartbeat_loop(rt: EventGateRuntime) -> None:
    if rt.heartbeat is None:
        return
    while True:
        await asyncio.sleep(HEARTBEAT_CYCLE_S)
        rt.stats.ws_state = rt.ws.state.ws_state
        caches = rt.lab.caches
        sizes = {
            "base_rows": len(caches.base_rows) if caches is not None else 0,
            "pedigree": len(caches.pedigree) if caches is not None else 0,
            "e2b": len(caches.e2b) if caches is not None else 0,
            "debounce": rt.debouncer.size,
        }
        fields = event_gate_heartbeat_fields(
            rt.stats, now=utcnow(), enabled=True, cache_sizes=sizes
        )
        fields.update(rt.tapes.heartbeat_fields())
        fields.update(rt.pullback.heartbeat_fields())
        fields.update(rt.pullback_inserts.heartbeat_fields("event_gate_pullback_insert_"))
        try:
            await rt.heartbeat(fields)
        except Exception:  # a heartbeat that cannot be written must not stop the gate
            logger.warning("meme_event_gate_heartbeat_write_failed")


async def run_event_gate(rt: EventGateRuntime) -> None:
    """Restart-safe (plan §4 (iv)): waits for the Lab's own first tick to warm
    ``LabContext.caches`` before a single subscription opens."""
    while rt.lab.caches is None or not rt.lab.caches.specs:  # noqa: ASYNC110 — polling a plain field, not an Event
        await asyncio.sleep(1)
    queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=rt.config.queue_size)
    try:
        await _run_loops(rt, queue)
    except asyncio.CancelledError:
        await rt.pullback_inserts.aclose()  # T4.91: no insert outlives the gate's shutdown
        raise


async def _run_loops(rt: EventGateRuntime, queue: asyncio.Queue[Notification]) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(_slot_subscribe_loop(rt), name="meme-event-gate-slot")
        group.create_task(_sync_loop(rt), name="meme-event-gate-sync")
        group.create_task(_read_loop(rt, queue), name="meme-event-gate-read")
        group.create_task(_evaluate_loop(rt, queue), name="meme-event-gate-evaluate")
        group.create_task(_flush_loop(rt), name="meme-event-gate-flush")
        group.create_task(_trail_flush_loop(rt), name="meme-event-gate-trail-flush")
        group.create_task(_tape_flush_loop(rt), name="meme-event-gate-tape-flush")
        group.create_task(_pullback_loop(rt), name="meme-event-gate-pullback")
        group.create_task(_heartbeat_loop(rt), name="meme-event-gate-heartbeat")


async def run_event_gate_forever(rt: EventGateRuntime) -> None:
    """F2 (review-T4.52b.md §4): ``main.py`` runs this, never
    :func:`run_event_gate` directly — any exception (a WS error the read loop
    somehow let through, a DB error mid-evaluation, the ``TaskGroup``'s own
    ``ExceptionGroup``) is logged and the gate restarts after
    :data:`RESTART_DELAY_S`, forever, instead of propagating into ``main.py``'s
    own ``TaskGroup`` and killing discovery/the fast lane/the Lab with it."""
    while True:
        try:
            await run_event_gate(rt)
            return  # ``rt.ws`` closed deliberately (``aclose``) — not a crash
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            rt.stats.record_restart()
            logger.warning(
                "meme_event_gate_crashed_restarting",
                delay_s=RESTART_DELAY_S,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            await asyncio.sleep(RESTART_DELAY_S)
