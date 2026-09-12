"""``HUNTER_ROLE=meme`` — the pump.fun radar, one TaskGroup of loops.

The shape is the scanner-worker's: a thin entrypoint, a ``WorkerRuntime`` that owns
logging, Sentry, the heartbeat and ``/health``·``/ready``·``/metrics``, and the work
itself as supervised tasks (ARCHITECTURE.md §1.7, §11).

Streams and cadences, and one deliberate asymmetry between them: **discovery and
the four board streams react to frames; everything else wakes on its own clock**,
because the budgets they spend are per unit of *time*, not per event.

**Off by default** (``MEME_ENABLED``). The radar opens sockets to third parties
and polls undocumented endpoints; a default that starts doing that on the next
restart of an unrelated deploy is not a default (the ``market_spot_enabled``
argument, ``hunter_core.settings``). Disabled, the process still serves
``/health``, ``/ready`` and ``/metrics`` and says so in the readiness body — a
switched-off collector must be *visibly* switched off, not indistinguishable from
a broken one.

**Nothing here can become an order.** No import reaches ``packages/risk-core``,
``hunter_core.execution`` or the execution-worker, and the API role has ``SELECT``
and nothing else on the radar's tables (T4-MEME-RADAR.md §0).

**The Lab is a cadence in the same process** (T4.6, ``lab.py``): once a minute it
reads the closed minute the folder wrote and runs the paper engine over it.
**The second collector** (T4.2c, ``wiring.py``): the site's boards over
``/ws/trenches`` (holders, top-10, dev, snipers, exposure), the ``swap-api``
tape (buys, sells, creator sells) and the risk read — each behind its own switch,
each reported in ``hb:meme:radar`` and ``GET /meme/sources`` as connected or not,
with its lag, its errors and its budget.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory, role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys
from hunter_exchanges.pumpfun.rest import PumpFunRestClient
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.ws import PumpPortalWsClient
from hunter_exchanges.rate_limit import TokenBucketRateLimiter
from hunter_meme_worker.chain import chain_once
from hunter_meme_worker.collect import fold_once, forever, poll_once, prune_once, reconcile_once
from hunter_meme_worker.config import MemeConfig, load_config
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.discovery import run_discovery
from hunter_meme_worker.fast_lane import fast_once
from hunter_meme_worker.graduation import GlobalParamsStore
from hunter_meme_worker.lab import LabContext, LabState, lab_once, write_lab_heartbeat
from hunter_meme_worker.mayhem import mayhem_once
from hunter_meme_worker.metrics import meme_tracked_mints
from hunter_meme_worker.repo import load_tracked
from hunter_meme_worker.tracker import MintTracker
from hunter_meme_worker.wallets import build_wallets, wallets_once
from hunter_meme_worker.wiring import (
    build_boards,
    build_risk,
    build_sources,
    build_trades,
    heartbeat_once,
    risk_once,
    run_board,
    trades_once,
)

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime
    from hunter_exchanges.pumpfun.trenches import TrenchesWsClient

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
STALE_EVENT_AFTER_S = 600
"""No new token for ten minutes is *suspicious*, not fatal: pump.fun genuinely has
quiet stretches, and T4.1's acceptance criterion separates "the socket is alive"
from "there is activity". It shows up as a status detail, never as a red
``/ready`` (``hunter_core.runtime`` keeps the two apart)."""

SOL_PRICE_BUDGET_PER_MINUTE = 50
"""``/sol-price`` is its own upstream rate-limit group (50/60 s, ``docs/PUMPFUN.md``
§1.4), so the Lab's quote client gets its own bucket instead of spending the
curve poller's 60 — and the Lab reads it at most once a minute anyway."""


def build_context(
    runtime: WorkerRuntime, config: MemeConfig
) -> tuple[RadarContext, dict[str, TrenchesWsClient]]:
    """Wire the clients, the tracked set, the shared state and the T4.2c sources."""
    tracker = MintTracker(
        window_minutes=config.track_window_minutes,
        cap=config.tracked_max,
        young_minutes=config.young_minutes,
    )
    sources = build_sources(config)
    boards, board_clients = build_boards(config, tracker)
    curves = PumpFunRestClient()
    return RadarContext(
        config=config,
        session_factory=create_session_factory(runtime.engine),
        tracker=tracker,
        state=RadarState(),
        events=PumpPortalWsClient(),
        curves=curves,
        chain=SolanaRpcClient(),
        sources=sources,
        boards=boards,
        trades=build_trades(config, sources),
        risk=build_risk(config, sources),
        # The same client, the same 60/60 s bucket: a global-params read is a
        # curve read not made, once an hour (T4.2d).
        params=GlobalParamsStore(curves, refresh_s=config.global_params_refresh_s),
        wallets=build_wallets(config, sources),
    ), board_clients


def _heartbeat_writer(runtime: WorkerRuntime) -> Callable[[dict[str, str]], Awaitable[None]]:
    """Fields land on this worker's own ``hb:meme:radar`` hash; the runtime's
    heartbeat loop keeps the key alive, so a stopped loop shows as a stale
    field next to a fresh ``ts``."""
    key = keys.heartbeat(runtime.role, runtime.instance)

    async def write_fields(mapping: dict[str, str]) -> None:
        await runtime.redis.hset(key, mapping=mapping)  # type: ignore[reportUnknownMemberType]

    return write_fields


def build_lab_context(runtime: WorkerRuntime, config: MemeConfig) -> LabContext:
    """The Lab's own view: the same session factory, a quote client of its own,
    and a writer onto this worker's heartbeat hash."""
    return LabContext(
        config=config,
        session_factory=create_session_factory(runtime.engine),
        state=LabState(),
        quotes=PumpFunRestClient(
            rate_limiter=TokenBucketRateLimiter(
                "pumpfun_sol_price", capacity=SOL_PRICE_BUDGET_PER_MINUTE, refill_period_s=60.0
            )
        ),
        heartbeat=_heartbeat_writer(runtime),
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


def _register_health(
    runtime: WorkerRuntime, ctx: RadarContext, boards: dict[str, TrenchesWsClient]
) -> None:
    """Readiness answers "should traffic reach me"; the details answer "what is degraded"."""

    async def discovery_connected() -> bool:
        return ctx.events.state.ws_state == "connected"

    runtime.readiness_checks.append(discovery_connected)
    runtime.status_details["discovery_stream"] = lambda: ctx.events.state.ws_state
    runtime.status_details["tracked_mints"] = lambda: str(len(ctx.tracker))
    runtime.status_details["last_event_age_s"] = lambda: _last_event_age(ctx)
    runtime.status_details["ws_generation"] = lambda: str(ctx.state.ws_generation)
    runtime.status_details["trenches"] = lambda: (
        "disabled (MEME_TRENCHES_ENABLED=false)"
        if not boards
        else ", ".join(f"{b}:{c.state.ws_state}" for b, c in boards.items())
    )
    runtime.status_details["swap_api"] = lambda: (
        "disabled (MEME_SWAP_API_ENABLED=false)"
        if ctx.trades is None
        else f"{len(ctx.trades.coverage)} mints covered"
    )
    runtime.status_details["risk"] = lambda: (
        "disabled (MEME_RISK_ENABLED=false)"
        if ctx.risk is None
        else f"{len(ctx.risk.last_read)} mints read"
    )
    runtime.status_details["wallets"] = lambda: (
        "disabled (MEME_WATCH_WALLETS empty)"
        if ctx.wallets is None
        else ctx.wallets.describe(utcnow())
    )


def _register_lab_health(runtime: WorkerRuntime, lab: LabContext | None) -> None:
    """The Lab's liveness as a detail, never a verdict: a stopped loop must be
    visible next to a green collector, and a quiet gate must not turn ``/ready``
    red (contract §Semântica 5)."""
    if lab is None:
        runtime.status_details["lab"] = lambda: "disabled (MEME_LAB_ENABLED=false)"
        return

    def describe() -> str:
        last = lab.state.last_tick_at
        if last is None:
            return "starting"
        age = int((utcnow() - last).total_seconds())
        stalled = age > 3 * lab.config.lab_cycle_s
        return f"{age}s since last tick" + (" (stalled)" if stalled else "")

    runtime.status_details["lab"] = describe


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

    ctx, boards = build_context(runtime, config)
    _register_health(runtime, ctx, boards)
    lab = build_lab_context(runtime, config) if config.lab_enabled else None
    _register_lab_health(runtime, lab)
    write = _heartbeat_writer(runtime)
    if lab is None:
        logger.warning("meme_lab_disabled", reason="MEME_LAB_ENABLED is false")
        await write_lab_heartbeat(
            LabContext(config, ctx.session_factory, LabState(), None, write), enabled=False
        )
    warmed = await warm_tracked_set(ctx)
    logger.info(
        "meme_radar_starting",
        tracked=warmed,
        budget=config.rest_budget_per_minute,
        cap=config.tracked_max,
        retention_days=config.retention_days,
        lab=lab is not None,
        trenches=sorted(boards),
        swap_api=ctx.trades is not None,
        swap_api_budget_60s=config.swap_api_budget_60s,
        chain_curves=config.chain_curves_enabled,
        fast_lane=config.fast_lane_enabled and config.chain_curves_enabled,
        risk=ctx.risk is not None,
        wallets=len(config.watch_wallets),
    )

    async def _discovery(context: RadarContext) -> None:
        await run_discovery(context)
        runtime.mark_success()

    async def _heartbeat(context: RadarContext) -> None:
        await heartbeat_once(context, write)

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(_discovery(ctx), name="meme-discovery")
            group.create_task(
                forever("poll", config.poll_cycle_s, poll_once, ctx), name="meme-poll"
            )
            if config.chain_curves_enabled:
                # T4.2f: every tracked curve from the chain, once a minute; the
                # top-K reconciliation is a subset of it and does not run.
                group.create_task(
                    forever("chain", config.chain_cycle_s, chain_once, ctx), name="meme-chain"
                )
                if config.fast_lane_enabled:
                    # T4.16: the mints younger than five minutes, every 15 s.
                    group.create_task(
                        forever("fast", config.fast_lane_cycle_s, fast_once, ctx),
                        name="meme-fast",
                    )
            else:
                group.create_task(
                    forever("reconcile", config.reconcile_cycle_s, reconcile_once, ctx),
                    name="meme-reconcile",
                )
            group.create_task(
                forever("mayhem", config.mayhem_cycle_s, mayhem_once, ctx), name="meme-mayhem"
            )
            group.create_task(
                forever("fold", config.features_cycle_s, fold_once, ctx), name="meme-fold"
            )
            group.create_task(
                forever("retention", config.retention_cycle_s, prune_once, ctx),
                name="meme-retention",
            )
            group.create_task(
                forever("heartbeat", config.heartbeat_cycle_s, _heartbeat, ctx),
                name="meme-heartbeat",
            )
            for board, client in boards.items():
                group.create_task(run_board(ctx, client), name=f"meme-board-{board}")
            if ctx.trades is not None:
                group.create_task(
                    forever("trades", config.trades_cycle_s, trades_once, ctx), name="meme-trades"
                )
            if ctx.risk is not None:
                group.create_task(
                    forever("risk", config.risk_cycle_s, risk_once, ctx), name="meme-risk"
                )
            if ctx.wallets is not None:
                # T4.12: the observed wallets' real fills, every 30 s, own RPC bucket.
                group.create_task(
                    forever("wallets", config.wallets_cycle_s, wallets_once, ctx),
                    name="meme-wallets",
                )
            if lab is not None:
                group.create_task(
                    forever("lab", config.lab_cycle_s, lab_once, lab), name="meme-lab"
                )
    finally:
        await _close(ctx, boards)
        if lab is not None and isinstance(lab.quotes, PumpFunRestClient):
            await lab.quotes.aclose()


async def _close(ctx: RadarContext, boards: dict[str, TrenchesWsClient]) -> None:
    """Close whatever the clients own. Best effort: shutdown must not raise."""
    clients: list[object] = [ctx.events, ctx.curves, ctx.chain, ctx.wallets, *boards.values()]
    for client in clients:
        closer = getattr(client, "aclose", None)
        if closer is None:
            continue
        try:
            await closer()
        except Exception:  # a socket that will not close is not a shutdown failure
            logger.warning("meme_client_close_failed", client=type(client).__name__)
