"""The SPOT collection subsystem: one venue, one extra connection (T3.0c).

D1 says the wallet executes on Binance spot while every signal stays on the
perpetual. That makes spot a **second data path in the same process**, not a
second mode of the first one, and this module is where the two are kept apart:

- its own adapter (``/api/v3``, its own 6000/min REST budget, its own socket);
- its own universe (a 50M floor, ``spot_universe.py``), refreshed on the same
  cadence as the perpetual one;
- its own persist queue and drain loop — ``load_market_ids`` answers
  ``{symbol: market_id}``, so one queue carrying both listings of ``BTCUSDT``
  could only resolve one of them (T3.0b §5.1);
- its own coverage record, heartbeat and recovery, keyed by ``market_type``.

**One shard only.** With ``MARKET_SHARD=i/N`` the spot collector runs on shard
0 and owns the whole spot universe: nineteen pairs times four channels is 76
streams against a 1024 limit and a handful of REST calls every fifteen minutes,
so splitting it would buy nothing and cost a leader election, four heartbeats
and a coverage merge. Every other shard idles this task instead of not creating
it, so the topology is visible in the task list rather than implied by absence.

**Shared with the perpetual, deliberately:** the tick coalescer (keyed by
``(exchange, symbol, market_type)`` since T3.0b, so one flush pipeline serves
both) and the outbox wake event. Nothing else.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from hunter_core.domain.enums import MarketType
from hunter_core.logging import get_logger
from hunter_market_worker.heartbeat import HeartbeatState, run_heartbeat
from hunter_market_worker.persist import PersistQueues, drain_loop
from hunter_market_worker.recovery import run_recovery
from hunter_market_worker.spot_universe import monitored_spot_symbols, run_spot_universe
from hunter_market_worker.streaming import SPOT_CHANNELS, run_ingest, run_watchdog
from hunter_market_worker.supervision import IngestionHealth, Watchdog, forever
from hunter_market_worker.universe import MonitoredUniverse

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_exchanges.base import ExchangeAdapter
    from hunter_market_worker.coalesce import TickCoalescer
    from hunter_market_worker.coverage import CoverageStampFn

logger = get_logger(__name__)

SPOT_SHARD = (0, 1)
"""The spot collector reports as solo (see the module docstring): it is one
process owning one whole universe, so ``hb:market:spot:{exchange}`` and the
coverage record have no ``{i}of{N}`` suffix and nothing waits for siblings."""

STATUS_CONNECTED = "connected"
STATUS_DEGRADED = "degraded"
STATUS_ABSENT = "absent"


class SpotStatus:
    """``/ready``'s ``spot`` **status detail** — never a readiness check.

    Three values, and the middle one is the reason this is not a check: the
    perpetual pipeline is what M2 delivered and what the scanner, the strategy
    worker and the whole Radar depend on. A spot socket that is reconnecting
    must be *visible* without turning a healthy collector red, exactly like
    ``rest_gate`` (T2.9). ``absent`` is the honest word for "this process does
    not collect spot at all" — a shard other than 0, or ``MARKET_SPOT_ENABLED``
    off — as opposed to "it should and it is not working".
    """

    def __init__(self) -> None:
        self.enabled = False
        self.health: IngestionHealth | None = None

    def __call__(self) -> str:
        if not self.enabled or self.health is None:
            return STATUS_ABSENT
        state = self.health.state
        if state == "connected":
            return STATUS_CONNECTED
        if state == "idle":
            # Subscribed to nothing because nothing cleared the floor. Not a
            # degradation of this process: it is doing exactly what the rule says.
            return STATUS_CONNECTED
        return STATUS_DEGRADED


def collects_spot(settings: Settings) -> bool:
    """Whether *this* process runs the spot path (T3.0f: ``MARKET_ROLE``-aware).

    ``"perpetual"`` never collects spot, whatever ``MARKET_SPOT_ENABLED`` says
    -- the whole point of the role is that the flag cannot reach a perpetual
    shard by accident. ``"spot"`` (the dedicated process,
    ``infra/docker/docker-compose.yml``'s ``market-worker-spot``) collects
    solely on the flag: it is never sharded (``Settings._validate_market_role``
    refuses a sharded ``MARKET_SHARD`` under this role), so there is no shard
    index to gate on. ``"both"`` keeps the pre-T3.0f rule -- shard 0 only --
    for the single-process local stack.
    """
    role = settings.market_role_effective
    if role == "perpetual":
        return False
    if role == "spot":
        return settings.market_spot_enabled
    return settings.market_spot_enabled and settings.shard_index == SPOT_SHARD[0]


async def run_spot(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: ExchangeAdapter,
    redis: redis_asyncio.Redis,
    settings: Settings,
    runtime: WorkerRuntime,
    coalescer: TickCoalescer,
    status: SpotStatus,
    *,
    outbox_wake: asyncio.Event | None = None,
    coverage_stamps: dict[MarketType, CoverageStampFn] | None = None,
) -> None:
    """Run the whole spot path until cancelled. Never returns on its own.

    ``coverage_stamps`` (T3.46g) is forwarded to ``run_ingest`` unchanged —
    this path's own stamp closure is registered under
    ``MarketType.SPOT``, next to whatever the perpetual path registered under
    ``MarketType.PERPETUAL`` in the same shared dict.

    A task on every shard, idle on all but shard 0 (module docstring). Idling
    with an ``Event`` that is never set rather than returning: ``forever()``
    treats a task that returns as fatal, and "this shard does not collect spot"
    is a topology fact, not a failure.
    """
    if not collects_spot(settings):
        logger.info(
            "market_spot_collector_idle",
            exchange=adapter.code,
            shard=settings.market_shard,
            enabled=settings.market_spot_enabled,
        )
        await asyncio.Event().wait()
        return

    universe, queues, state = MonitoredUniverse(), PersistQueues(), HeartbeatState()
    health = IngestionHealth()
    status.enabled, status.health = True, health
    producer = f"market-worker@{runtime.instance}"

    async def warning(message: str) -> None:
        # Spot silence is reported and retried; it never marks the *worker*
        # unhealthy, because the perpetual pipeline is untouched by it.
        logger.warning("market_spot_connection_watchdog", exchange=adapter.code, message=message)

    watchdog = Watchdog(adapter, warning)
    # The last committed universe, so a restart collects immediately instead of
    # waiting out a refresh interval with an empty subscription.
    restored = await monitored_spot_symbols(session_factory, adapter.code)
    if restored:
        universe.set(restored)
        logger.info("market_spot_universe_restored", exchange=adapter.code, total=len(restored))

    logger.info("market_spot_collector_starting", exchange=adapter.code)
    try:
        async with asyncio.TaskGroup() as group:
            tasks: dict[str, Any] = {
                "spot-universe": run_spot_universe(
                    session_factory, adapter, redis, settings, universe, runtime
                ),
                "spot-ingest": run_ingest(
                    adapter,
                    redis,
                    settings,
                    universe,
                    queues,
                    state,
                    runtime,
                    coalescer,
                    health,
                    watchdog,
                    market_type=MarketType.SPOT,
                    channels=SPOT_CHANNELS,
                    shard=SPOT_SHARD,
                    coverage_stamps=coverage_stamps,
                ),
                "spot-persist": drain_loop(
                    session_factory,
                    adapter.code,
                    queues,
                    runtime,
                    outbox_wake,
                    producer,
                    MarketType.SPOT,
                ),
                "spot-recovery": run_recovery(
                    session_factory, adapter, universe, state, runtime, MarketType.SPOT
                ),
                "spot-heartbeat": run_heartbeat(
                    runtime,
                    adapter,
                    universe,
                    state,
                    session_factory,
                    market_type=MarketType.SPOT,
                    shard=SPOT_SHARD,
                ),
                "spot-watchdog": run_watchdog(watchdog, universe),
            }
            for name, coro in tasks.items():
                group.create_task(forever(name, coro), name=f"market-{name}")
    finally:
        status.enabled, status.health = False, None
        await adapter.aclose()
