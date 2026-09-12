"""``HUNTER_ROLE=meme`` — the pump.fun radar, four loops under one TaskGroup.

The shape is the scanner-worker's: a thin entrypoint, a ``WorkerRuntime`` that owns
logging, Sentry, the heartbeat and ``/health``·``/ready``·``/metrics``, and the work
itself as supervised tasks (ARCHITECTURE.md §1.7, §11).

Four tasks, and one deliberate asymmetry between them: **discovery is a stream and
the other three are cadences.** Discovery consumes the PumpPortal socket and reacts
to a frame; the poller, the reconciler and the folder wake on their own clock,
because the budgets they spend are per unit of *time*, not per event.

**Off by default** (``MEME_ENABLED``). The radar opens a WebSocket to a third party
and polls an undocumented endpoint; a default that starts doing that on the next
restart of an unrelated deploy is not a default (the ``market_spot_enabled``
argument, ``hunter_core.settings``). Disabled, the process still serves
``/health``, ``/ready`` and ``/metrics`` and says so in the readiness body — a
switched-off collector must be *visibly* switched off, not indistinguishable from
a broken one.

**Nothing here can become an order.** No import reaches ``packages/risk-core``,
``hunter_core.execution`` or the execution-worker, and the API role has ``SELECT``
and nothing else on all five tables (T4-MEME-RADAR.md §0).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory, role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.rest import PumpFunRestClient
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.ws import PumpPortalWsClient
from hunter_meme_worker.collect import fold_once, forever, poll_once, prune_once, reconcile_once
from hunter_meme_worker.config import MemeConfig, load_config
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.discovery import run_discovery
from hunter_meme_worker.metrics import meme_tracked_mints
from hunter_meme_worker.repo import load_tracked
from hunter_meme_worker.tracker import MintTracker

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
STALE_EVENT_AFTER_S = 600
"""No new token for ten minutes is *suspicious*, not fatal: pump.fun genuinely has
quiet stretches, and T4.1's acceptance criterion separates "the socket is alive"
from "there is activity". It shows up as a status detail, never as a red
``/ready`` (``hunter_core.runtime`` keeps the two apart)."""


def build_context(runtime: WorkerRuntime, config: MemeConfig) -> RadarContext:
    """Wire the three clients, the tracked set and the shared state."""
    return RadarContext(
        config=config,
        session_factory=create_session_factory(runtime.engine),
        tracker=MintTracker(
            window_minutes=config.track_window_minutes,
            cap=config.tracked_max,
            young_minutes=config.young_minutes,
        ),
        state=RadarState(),
        events=PumpPortalWsClient(),
        curves=PumpFunRestClient(),
        chain=SolanaRpcClient(),
    )


async def warm_tracked_set(ctx: RadarContext) -> int:
    """Rebuild the tracked set from the database before any loop starts.

    A restart is not a reset: without this the radar would watch only what the
    socket happens to push next, and every mint discovered before the restart
    would silently stop being polled while its rows kept implying it was watched.
    This is the durable checkpoint half of Astra's MUST-FIX 3.
    """
    cutoff = utcnow() - timedelta(minutes=ctx.config.track_window_minutes)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        tracked = await load_tracked(session, cutoff=cutoff, cap=ctx.config.tracked_max)
    for mint in tracked:
        ctx.tracker.observe(mint)
    meme_tracked_mints.set(len(ctx.tracker))
    return len(tracked)


def _register_health(runtime: WorkerRuntime, ctx: RadarContext) -> None:
    """Readiness answers "should traffic reach me"; the details answer "what is degraded"."""

    async def discovery_connected() -> bool:
        return ctx.events.state.ws_state == "connected"

    runtime.readiness_checks.append(discovery_connected)
    runtime.status_details["discovery_stream"] = lambda: ctx.events.state.ws_state
    runtime.status_details["tracked_mints"] = lambda: str(len(ctx.tracker))
    runtime.status_details["last_event_age_s"] = lambda: _last_event_age(ctx)
    runtime.status_details["ws_generation"] = lambda: str(ctx.state.ws_generation)


def _last_event_age(ctx: RadarContext) -> str:
    last = ctx.state.last_event_at
    if last is None:
        return "never"
    age = int((utcnow() - last).total_seconds())
    return f"{age}s{' (stale)' if age > STALE_EVENT_AFTER_S else ''}"


async def run_meme(runtime: WorkerRuntime) -> None:
    """The entrypoint ``RoleRegistry['meme']`` points at."""
    config = load_config(runtime.settings)
    if not config.enabled:
        runtime.status_details["radar"] = lambda: "disabled (MEME_ENABLED=false)"
        logger.warning("meme_radar_disabled", reason="MEME_ENABLED is false")
        # Health, readiness and metrics stay served; nothing is collected. An
        # Event that is never set parks the task without a polling loop, and the
        # runtime cancels it on SIGTERM like any other.
        await asyncio.Event().wait()
        return

    ctx = build_context(runtime, config)
    _register_health(runtime, ctx)
    warmed = await warm_tracked_set(ctx)
    logger.info(
        "meme_radar_starting",
        tracked=warmed,
        budget=config.rest_budget_per_minute,
        cap=config.tracked_max,
        retention_days=config.retention_days,
    )

    async def _discovery(context: RadarContext) -> None:
        await run_discovery(context)
        runtime.mark_success()

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(_discovery(ctx), name="meme-discovery")
            group.create_task(forever("poll", config.poll_cycle_s, _poll, ctx), name="meme-poll")
            group.create_task(
                forever("reconcile", config.reconcile_cycle_s, _reconcile, ctx),
                name="meme-reconcile",
            )
            group.create_task(
                forever("fold", config.features_cycle_s, _fold, ctx), name="meme-fold"
            )
            group.create_task(
                forever("retention", config.retention_cycle_s, prune_once, ctx),
                name="meme-retention",
            )
    finally:
        await _close(ctx)


async def _poll(ctx: RadarContext) -> None:
    await poll_once(ctx)


async def _reconcile(ctx: RadarContext) -> None:
    await reconcile_once(ctx)


async def _fold(ctx: RadarContext) -> None:
    await fold_once(ctx)


async def _close(ctx: RadarContext) -> None:
    """Close whatever the clients own. Best effort: shutdown must not raise."""
    for client in (ctx.events, ctx.curves, ctx.chain):
        closer = getattr(client, "aclose", None)
        if closer is None:
            continue
        try:
            await closer()
        except Exception:  # a socket that will not close is not a shutdown failure
            logger.warning("meme_client_close_failed", client=type(client).__name__)
