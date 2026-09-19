"""The launch lane itself (T4.67a, EXP-M18): a pump.fun ``create`` folded
straight into a proposal for ``launch_v0/1`` — no 15-second base row, no
holders, no tape, no pedigree; the criterion is only what the create frame
itself and the lane's own memory can answer (``launch_lane_entry.py``).

**Chosen trigger: the PumpPortal create stream, already flowing through
``discovery.py``**, not a new program-wide ``logsSubscribe`` on the pump
program. ``plan-T4.52b.md``'s own inventory (§1, item 1 vs item 8) measured
PumpPortal's ``subscribeNewToken`` at ~100 ms and never chose the
program-wide log firehose for *any* lane — item 8 was chosen there only for a
**per-mint**, already-known PDA (T4.52b-1's own probe measured that path,
never a program-wide one). Building and decoding a brand-new ``CreateEvent``
off an unfiltered, unmeasured, high-volume subscription — with no recorded
fixture and no live measurement of its own — would spend this task's whole
budget on a transport most likely no faster than the one already wired,
tested and running in production. ``launch_lane_eval.on_create`` is called
by ``discovery.py`` the instant a ``created`` frame is durable, before its
own session even opens — well inside the 200 ms budget the brief sets.

**Paper accounting priced by events, not the Lab's 15-second filler**: once a
create passes the gate, the lane opens its own short-lived
``SolanaWsClient`` subscription (:mod:`hunter_exchanges.pumpfun.rpc_ws`, the
T4.52b-1 adapter) on the mint's own bonding-curve PDA and folds every
notification into a fresh :class:`~hunter_meme_worker.event_state.MintEventState`
— the same series the event gate uses (``launch_lane_pricing.py``). The
first point at or after +1 s opens a ``meme_paper_bets`` row
(``launch_lane_bets.py``); the first of the three pre-registered exits closes
it (``launch_lane_eval.py``, split out for the 350-line budget — the same cut
``event_gate.py``/``event_gate_eval.py`` took).

**Never crashes the worker.** Every per-frame, per-create and per-watch step
is wrapped in ``launch_lane_eval.py``; a bad frame or a bad row is logged,
never raised into this module's own ``TaskGroup``.
:func:`run_launch_lane_forever` restarts the whole lane after a crash —
``event_gate.py``'s own F2 discipline.
"""

from __future__ import annotations

import asyncio

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.launch_lane_eval import apply_notification, on_create, progress_mint
from hunter_meme_worker.launch_lane_repo import load_launch_specs
from hunter_meme_worker.launch_lane_runtime import LaunchLaneRuntime
from hunter_meme_worker.launch_lane_stats import heartbeat_fields as launch_lane_heartbeat_fields

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"

SPEC_REFRESH_S = 30
HEARTBEAT_CYCLE_S = 5
SWEEP_CYCLE_S = 1
RESTART_DELAY_S = 5

__all__ = ["LaunchLaneRuntime", "on_create", "run_launch_lane", "run_launch_lane_forever"]


async def _read_loop(rt: LaunchLaneRuntime) -> None:
    async for notif in rt.ws.listen():
        try:
            await apply_notification(rt, notif, utcnow())
        except Exception as exc:  # a bad frame is dropped, not a crash
            logger.warning(
                "meme_launch_lane_bad_frame", error_type=type(exc).__name__, error=str(exc)
            )


async def _sweep_loop(rt: LaunchLaneRuntime) -> None:
    """The periodic half of exit detection: a ``time_stop`` (or a watch that
    never got a single point) fires even when no new notification arrives."""
    while True:
        await asyncio.sleep(SWEEP_CYCLE_S)
        now = utcnow()
        for mint in list(rt.watches):
            try:
                await progress_mint(rt, mint, now, None)
            except Exception as exc:
                logger.warning(
                    "meme_launch_lane_sweep_failed",
                    mint=mint,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )


async def _spec_refresh_loop(rt: LaunchLaneRuntime) -> None:
    while True:
        try:
            async with role_session(rt.session_factory, db_role=WORKER_ROLE) as session:
                rt.specs = tuple(await load_launch_specs(session))
        except Exception:  # a refresh failure keeps the last known specs
            logger.warning("meme_launch_lane_spec_refresh_failed")
        await asyncio.sleep(SPEC_REFRESH_S)


async def _heartbeat_loop(rt: LaunchLaneRuntime) -> None:
    if rt.heartbeat is None:
        return
    while True:
        await asyncio.sleep(HEARTBEAT_CYCLE_S)
        try:
            await rt.heartbeat(
                launch_lane_heartbeat_fields(rt.stats, now=utcnow(), mode=rt.config.mode)
            )
        except Exception:  # a heartbeat that cannot be written must not stop the lane
            logger.warning("meme_launch_lane_heartbeat_write_failed")


async def run_launch_lane(rt: LaunchLaneRuntime) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(_read_loop(rt), name="meme-launch-lane-read")
        group.create_task(_sweep_loop(rt), name="meme-launch-lane-sweep")
        group.create_task(_spec_refresh_loop(rt), name="meme-launch-lane-specs")
        group.create_task(_heartbeat_loop(rt), name="meme-launch-lane-heartbeat")


async def run_launch_lane_forever(rt: LaunchLaneRuntime) -> None:
    """``event_gate.py``'s own F2 discipline: any exception restarts the whole
    lane after :data:`RESTART_DELAY_S` instead of taking ``main.py``'s own
    ``TaskGroup`` — and discovery with it — down."""
    while True:
        try:
            await run_launch_lane(rt)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "meme_launch_lane_crashed_restarting",
                delay_s=RESTART_DELAY_S,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            await asyncio.sleep(RESTART_DELAY_S)
