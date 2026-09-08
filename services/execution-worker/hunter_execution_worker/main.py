"""``HUNTER_ROLE=execution`` — the paper wallet's engine.

One TaskGroup owns six long-lived loops (admission, entries, protection, expiry,
kill switch, mark-to-market) plus the heartbeat; :func:`forever` makes any of
them *returning* fatal, because a loop that quietly stopped is worse than a
process that restarts — a stopped protection loop is a position without a stop.

Two refusals happen before any loop starts:

- **``ENABLE_LIVE_TRADING=true``** (``config.load_config``). This process is the
  paper worker and there is no live adapter; coming up anyway would be coming up
  as something an operator believes is trading real money;
- **the paper schema is missing.** Without ``0006``/``0007`` there is no wallet
  lock to take and no column to write the curve's quality into, and a worker that
  "runs" while every cycle raises reports itself healthy while doing nothing.

**Recovery is not a step here, and that is the design.** There is no state to
rebuild: every loop re-reads the positions, the intentions and the reservations
from Postgres on every pass, so the worker that comes back after ``kill -9`` is
the worker that went down, minus whatever the last transaction did not commit.
The only in-memory thing is the trigger watermark, and losing it can cause a
re-evaluation, never a second sale (``protection.TriggerWatermarks``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from functools import partial
from typing import TYPE_CHECKING, Any, cast

from hunter_core.db.session import create_session_factory
from hunter_core.logging import get_logger
from hunter_execution_worker.avg_price import ExchangeAvgPrice
from hunter_execution_worker.bridge_consumer import autonomy_status, bridge_tasks
from hunter_execution_worker.config import load_config
from hunter_execution_worker.cycles import Cycles, every
from hunter_execution_worker.health import migration_present, readiness_checks
from hunter_execution_worker.heartbeat import run_heartbeat
from hunter_execution_worker.market_data import RedisSpotMarketData
from hunter_execution_worker.schedule import next_mtm_tick
from hunter_execution_worker.state import CycleHealth

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime

logger = get_logger(__name__)

__all__ = ["forever", "run_execution"]


def _avg_price_reader(runtime: WorkerRuntime) -> ExchangeAvgPrice:
    """The ``NOTIONAL`` reference reader, on the **shared** spot weight budget.

    Redis is passed explicitly, never the client's own default: without it the
    limiter falls back to a per-process bucket, and every process with a local
    budget adds up to N quotas against one shared exchange quota, whose price for
    getting it wrong is an IP ban (the same reasoning as
    ``hunter_market_worker.config``). ``GET /api/v3/avgPrice`` is weight 2 and
    this reader asks at most once per market per
    ``avg_price.AVG_PRICE_REFRESH_S``.
    """
    from hunter_exchanges.binance_spot import BinanceSpotAdapter
    from hunter_exchanges.binance_spot.http import (
        REQUEST_WEIGHT_CAPACITY,
        REQUEST_WEIGHT_PERIOD_S,
    )
    from hunter_exchanges.binance_spot.rest import BinanceSpotRestClient
    from hunter_exchanges.rate_limit import TokenBucketRateLimiter

    limiter = TokenBucketRateLimiter(
        "binance",
        redis=cast("Any", runtime.redis),
        capacity=REQUEST_WEIGHT_CAPACITY,
        refill_period_s=REQUEST_WEIGHT_PERIOD_S,
    )
    return ExchangeAvgPrice(BinanceSpotAdapter(rest=BinanceSpotRestClient(rate_limiter=limiter)))


async def forever(name: str, coro: Awaitable[None]) -> None:
    """A long-lived loop must never return; if it does, that is fatal."""
    await coro
    raise RuntimeError(f"task {name} exited unexpectedly")


async def run_execution(runtime: WorkerRuntime) -> None:
    """Entry point registered for ``HUNTER_ROLE=execution``."""
    config = load_config()
    factory = create_session_factory(runtime.engine)
    health = CycleHealth()
    checks = readiness_checks(factory, config, health)
    runtime.readiness_checks.extend(checks)
    # A status detail, never a verdict: autonomy being off is the normal, correct
    # state of this worker, and it must not turn ``/ready`` red. What it must do
    # is *say so* — "the wallet entered nothing" has two very different causes.
    runtime.status_details["autonomy"] = lambda: autonomy_status(config)
    logger.info(
        "execution_worker_starting",
        paper_autonomy=config.enable_paper_autonomy,
        mtm_poll_s=config.mtm_poll_s,
    )
    try:
        if not await migration_present(factory):
            raise RuntimeError(
                "0006_paper_wallet/0007_paper_roles are not applied; refusing to run. There is no "
                "wallet lock to take and nowhere to record why a curve point has no BRL"
            )
        data = RedisSpotMarketData(runtime.redis, avg_price=_avg_price_reader(runtime))
        cycles = Cycles(factory, data, config, health)
        async with asyncio.TaskGroup() as group:
            loops = {
                "admission": (config.admission_poll_s, cycles.admission),
                "entries": (config.admission_poll_s, cycles.entries),
                "protection": (config.protection_poll_s, cycles.protection),
                "expiry": (config.expiry_poll_s, cycles.expiry),
                "kill_switch": (config.kill_switch_poll_s, cycles.kill_switch),
                "mtm": (config.mtm_poll_s, cycles.mark_to_market),
            }
            if config.enable_paper_autonomy:
                loops["bridge"] = (config.admission_poll_s, cycles.bridge)
            # The MTM is the one loop whose period decides whether the trading
            # day has a reference at all: aligned to the minute grid, plus one
            # point just before the Sao Paulo turn (``schedule``).
            mtm_plan = partial(next_mtm_tick, period_s=config.mtm_poll_s)
            for name, (cadence, run) in loops.items():
                group.create_task(
                    forever(
                        name,
                        every(
                            cadence,
                            run,
                            name=name,
                            health=health,
                            plan=mtm_plan if name == "mtm" else None,
                        ),
                    ),
                    name=f"execution-{name}",
                )
            group.create_task(
                forever("heartbeat", run_heartbeat(runtime, health, config)),
                name="execution-heartbeat",
            )
            for name, coro in bridge_tasks(
                config,
                redis=runtime.redis,
                factory=factory,
                data=data,
                health=health,
                consumer=runtime.instance,
            ):
                group.create_task(forever(name, coro), name=f"execution-{name}")
    finally:
        for check in checks:
            if check in runtime.readiness_checks:
                runtime.readiness_checks.remove(check)
        runtime.status_details.pop("autonomy", None)
