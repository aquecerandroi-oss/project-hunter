"""``HUNTER_ROLE=strategy`` — the Shadow Lab worker.

One TaskGroup owns the four long-lived tasks (decisions, outcomes, outbox,
heartbeat); ``forever`` makes any of them returning fatal, because a task that
quietly stopped is worse than a process that restarts. Nothing here places an
order, sizes a position or touches a portfolio: the only writes are
``agent_signals``, ``signal_outcomes``, ``shadow_episodes`` and
``shadow_outbox``, and every signal carries ``purpose = research_only``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory
from hunter_core.logging import get_logger
from hunter_strategy_worker.config import load_config
from hunter_strategy_worker.consumer import ConsumerHealth, run_consumer
from hunter_strategy_worker.health import migration_present, readiness_checks
from hunter_strategy_worker.heartbeat import run_heartbeat
from hunter_strategy_worker.outbox import OutboxHealth, run_outbox
from hunter_strategy_worker.outcome_sweep import run_outcomes

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime

logger = get_logger(__name__)

__all__ = ["forever", "run_strategy"]


async def forever(name: str, coro: Awaitable[None]) -> None:
    """A long-lived task must never return; if it does, that is fatal."""
    await coro
    raise RuntimeError(f"task {name} exited unexpectedly")


async def run_strategy(runtime: WorkerRuntime) -> None:
    """Entry point registered for ``HUNTER_ROLE=strategy``."""
    config = load_config()
    settings = runtime.settings
    shard_index, shard_total = settings.strategy_shard_index, settings.strategy_shard_total
    factory = create_session_factory(runtime.engine)
    consumer_health, outbox_health = ConsumerHealth(), OutboxHealth()
    checks = readiness_checks(factory, config, consumer_health, outbox_health, runtime.redis)
    runtime.readiness_checks.extend(checks)
    logger.info(
        "shadow_worker_starting",
        cohort=config.cohort,
        strategy_shard=settings.strategy_shard,
    )
    try:
        if not await migration_present(factory):
            # Fatal on purpose: with 0002_shadow_lab missing there is nowhere to
            # write a decision, and a worker that "runs" while dropping every
            # signal is the worst possible failure mode for a research log. Since
            # T3.52 the same check covers 0017_eligibility_policy, which the
            # catalogue selects on every roster load.
            raise RuntimeError(
                "0002_shadow_lab / 0017_eligibility_policy are not applied; refusing to run"
            )
        async with asyncio.TaskGroup() as group:
            tasks = {
                "decisions": run_consumer(
                    factory,
                    runtime.redis,
                    runtime,
                    config,
                    consumer_health,
                    shard_index=shard_index,
                    shard_total=shard_total,
                ),
                # T3.74f: unpartitioned by design -- only shard 0 runs it
                # (outcome_sweep.run_outcomes docstring).
                "outcomes": run_outcomes(
                    factory, runtime, config, settings, shard_index=shard_index
                ),
                "outbox": run_outbox(factory, runtime.redis, runtime, config, outbox_health),
                "heartbeat": run_heartbeat(
                    runtime,
                    config,
                    consumer_health,
                    outbox_health,
                    shard_index=shard_index,
                    shard_total=shard_total,
                ),
            }
            for name, coro in tasks.items():
                group.create_task(forever(name, coro), name=f"shadow-{name}")
    finally:
        for check in checks:
            if check in runtime.readiness_checks:
                runtime.readiness_checks.remove(check)
