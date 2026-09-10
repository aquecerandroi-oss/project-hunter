"""Advancing open shadow trackings — the sweep, not the decision.

Split out of ``consumer.py`` (T3.74c, when the bar-dispatch work needed to grow
the consumer's own line budget): a genuinely separate responsibility from
consuming the candle stream — this runs on its own timer
(``ShadowConfig.outcome_poll_s``) and advances trackings that are already
*open*, independent of whatever bar the decision consumer is handling right
now.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_strategy_worker import slots
from hunter_strategy_worker.metrics import shadow_trackings_open, shadow_trackings_unswept
from hunter_strategy_worker.outcomes import advance_tracking
from hunter_strategy_worker.tracking_repo import (
    count_open_trackings,
    load_open_trackings,
    load_tracking,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_strategy_worker.config import ShadowConfig

logger = get_logger(__name__)

__all__ = ["run_outcomes", "sweep_outcomes"]


async def sweep_outcomes(
    factory: async_sessionmaker[AsyncSession],
    config: ShadowConfig,
    *,
    blocked: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> int:
    """Advance up to ``SWEEP_LIMIT`` open trackings once.

    Returns how many of the ones it *visited* are still open. The pass is
    bounded (``tracking_repo.SWEEP_LIMIT``), and the rows past the bound would
    otherwise be indistinguishable from a quiet market, so the backlog is
    published as ``hunter_shadow_trackings_unswept`` rather than left invisible.
    """
    async with role_session(factory, db_role="hunter_worker") as session:
        pending = await load_open_trackings(session)
        total_open = await count_open_trackings(session)
    unswept = max(0, total_open - len(pending))
    shadow_trackings_unswept.set(unswept)
    if unswept:
        logger.warning("shadow_sweep_incomplete", visited=len(pending), unswept=unswept)
    still_open = 0
    for tracking in pending:
        async with role_session(factory, db_role="hunter_worker") as session:
            await slots.lock_slot(
                session,
                strategy_version_id=tracking.strategy_version_id,
                market_id=tracking.market_id,
                cohort=str(tracking.meta.get("cohort") or config.cohort),
            )
            fresh = await load_tracking(session, tracking.signal_id)
            if fresh is None:
                continue
            result = await advance_tracking(session, fresh, config=config, blocked=blocked, now=now)
            if not result.finished:
                still_open += 1
    shadow_trackings_open.set(still_open)
    return still_open


async def run_outcomes(
    factory: async_sessionmaker[AsyncSession],
    runtime: WorkerRuntime,
    config: ShadowConfig,
    settings: Settings,
    *,
    shard_index: int = 0,
) -> None:
    """The outcome sweep loop. Postgres down is a backoff, never a death.

    **Leader-only under sharding (T3.74f).** ``sweep_outcomes`` is
    unpartitioned by design -- it advances whatever tracking is open,
    regardless of which shard's decision opened it, because a tracking
    outlives the bar that created it. Running it on every shard of a
    ``STRATEGY_SHARDS > 1`` topology would multiply Postgres load (the exact
    thing this task exists to relieve) for no benefit: N processes competing
    over ``slots.lock_slot`` for the same rows. Only ``shard_index == 0``
    runs the real sweep; every other shard idles on the same cadence, the
    same convention ``hunter_market_worker``'s ``fx``/``spot`` tasks already
    use for a once-per-cluster loop ("idles on every shard but shard 0").
    """
    blocked = frozenset(s.upper() for s in settings.market_universe_blocklist)
    if shard_index != 0:
        # Idling on an ``Event`` that is never set rather than returning:
        # ``forever()`` treats a task that returns as fatal, and "this shard
        # is not the sweep leader" is a topology fact, not a failure --
        # exactly the idiom ``hunter_market_worker.spot.run_spot`` already
        # uses for a once-per-cluster task idle on every non-leader shard.
        logger.info("shadow_outcome_sweep_idle_non_leader_shard", shard_index=shard_index)
        await asyncio.Event().wait()
        return
    while True:
        try:
            await sweep_outcomes(factory, config, blocked=blocked)
            runtime.mark_success()
        except Exception:
            runtime.mark_error()
            logger.exception("shadow_outcome_sweep_failed")
            await asyncio.sleep(min(60.0, config.outcome_poll_s * 6))
            continue
        await asyncio.sleep(config.outcome_poll_s)
