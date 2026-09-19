"""T4.63 — event-driven exits: the position's curve, judged on every update.

CITIZEN (18/09/2026, 19:06:43 → 19:11:29 BRT) was bought at 0,0716 SOL, peaked
at 0,1303 (+82 %) and was sold by the trailing stop at 0,0142 (−0,80 R): the
curve was drained in seconds **between two ticks** of ``exits.py``. This
runtime removes the wait: while a real position is open the executor owns one
Solana RPC WebSocket (``rpc_ws.SolanaWsClient``, the same client the radar's
event gate uses) and subscribes to the mint's bonding-curve PDA —
``accountSubscribe`` (the reserves after every trade) and ``logsSubscribe``
(the ``TradeEvent`` of every trade, so the creator's own sell is seen the
instant it lands, not on the radar's 15 s watch). Each notification is folded
into the position's running peak and evaluated by the **same**
``hunter_risk_meme.decide_exit`` with the **same** ``ExitParams`` the tick
uses; when it fires, the sell goes through ``exits.sell_on_event`` — the same
lock, the same fresh ``CurveRead``, the same build/simulate/send/resend path
as ``exits.manage_position``. The 10-second tick stays as fallback and
reconciliation; a position the tick just closed is found closed under the
lock and nothing is sent twice.

Shape (mirrors ``hunter_meme_worker.event_gate``): three loops in one
``TaskGroup`` — :func:`_sync_loop` keeps the subscriptions equal to
``open_positions`` (every 2 s, and the instant the entries loop opens one,
``ExecutorContext.event_exits_wake``; bounded at ``max_open_positions``
positions = ``× 2`` subscriptions); :func:`_read_loop` drains
``ws.listen()`` (which never raises — reconnects with backoff forever) into
a bounded queue, dropping and counting when full; :func:`_handle_loop`
evaluates each frame under a per-frame ``try``/``except`` (a bad frame is
counted, never a crash). :func:`run_event_exits_forever` restarts the whole
runtime 5 s after any exception (T4.62's discipline), so ``main.py``'s own
``TaskGroup`` — entries, the tick, the kill switch — never sees it. A WS
outage therefore means "tick only", never a stopped executor.

Behind ``MEME_EVENT_EXITS`` (``off`` by default, ``event_exits_config.py``).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger, redact_url
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_meme_executor.event_exits_config import EventExitsConfig
from hunter_meme_executor.event_exits_eval import handle_notification
from hunter_meme_executor.event_exits_runtime import EventExitsRuntime, SolanaWs, Watched
from hunter_meme_executor.event_exits_watch import sync_watch

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification

__all__ = [
    "EventExitsRuntime",
    "SolanaWs",
    "Watched",
    "event_exits_client",
    "handle_notification",
    "run_event_exits",
    "run_event_exits_forever",
    "sync_watch",
]

logger = get_logger(__name__)


def event_exits_client(config: EventExitsConfig) -> SolanaWsClient | None:
    """The one WebSocket this runtime owns — ``None`` with the flag off: no
    connection is opened, nothing subscribes, the tick is the only exit path."""
    return SolanaWsClient(url=config.ws_url) if config.enabled else None


async def _sync_loop(rt: EventExitsRuntime) -> None:
    wake = rt.ctx.event_exits_wake
    while True:
        try:
            await sync_watch(rt, now=utcnow())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a failed sync is the next sync's problem, not a crash
            logger.warning(
                "meme_event_exits_sync_failed",
                error_type=type(exc).__name__,
                error=redact_url(str(exc)),
            )
        try:
            await asyncio.wait_for(wake.wait(), timeout=rt.config.sync_s)
        except TimeoutError:
            pass
        wake.clear()


async def _read_loop(rt: EventExitsRuntime, queue: asyncio.Queue[Notification]) -> None:
    async for notif in rt.ws.listen():
        if rt.ws.state.reconnects != rt.seen_reconnects:
            rt.seen_reconnects = rt.ws.state.reconnects
            rt.stats.record_reconnect()
            logger.warning("meme_event_exits_ws_reconnected", reconnects=rt.seen_reconnects)
        rt.stats.ws_state = rt.ws.state.ws_state
        try:
            queue.put_nowait(notif)
        except asyncio.QueueFull:
            rt.stats.record_dropped()


async def _handle_loop(rt: EventExitsRuntime, queue: asyncio.Queue[Notification]) -> None:
    while True:
        notif = await queue.get()
        try:
            await handle_notification(rt, notif, now=utcnow())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # one bad frame is counted, never the runtime's end
            rt.stats.record_bad_frame()
            logger.warning(
                "meme_event_exits_bad_frame",
                error_type=type(exc).__name__,
                error=redact_url(str(exc)),
            )


async def run_event_exits(rt: EventExitsRuntime) -> None:
    queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=rt.config.queue_size)
    async with asyncio.TaskGroup() as group:
        group.create_task(_sync_loop(rt), name="meme-event-exits-sync")
        group.create_task(_read_loop(rt, queue), name="meme-event-exits-read")
        group.create_task(_handle_loop(rt, queue), name="meme-event-exits-handle")


async def run_event_exits_forever(rt: EventExitsRuntime) -> None:
    """What ``main.py`` runs: any exception out of :func:`run_event_exits` is
    counted, logged and the runtime restarts after ``restart_delay_s`` —
    forever. The tick keeps every position covered in between."""
    while True:
        try:
            await run_event_exits(rt)
            return  # ``rt.ws`` closed deliberately (``aclose``) — not a crash
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            rt.stats.record_restart()
            rt.stats.ws_state = "restarting"
            logger.warning(
                "meme_event_exits_crashed_restarting",
                delay_s=rt.config.restart_delay_s,
                error_type=type(exc).__name__,
                error=redact_url(str(exc)),
                exc_info=True,
            )
            await asyncio.sleep(rt.config.restart_delay_s)
