"""One pass over the dirty markets: evaluate, publish, add to the batch.

Moved out of ``runners.evaluation_loop`` (350-line budget) without changing what it
does; the loop now owns only the lock, the flush cadence and the failure policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_scanner_worker import publish as projections
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.metrics import scanner_tick_to_opportunity_seconds

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio

    from hunter_scanner_worker.persist import WriteBatch
    from hunter_scanner_worker.scanner import Scanner

__all__ = ["evaluate_due_markets"]


async def evaluate_due_markets(
    scanner: Scanner, redis: redis_asyncio.Redis, batch: WriteBatch, *, now: datetime
) -> int:
    """Evaluate every due market into ``batch``; returns how many were evaluated."""
    config = scanner.config
    scanner.coverage = await read_coverage(redis, config.exchange, now=now)
    due = scanner.state.due(now, config.feature_throttle_s)
    evaluated = 0
    for market in due[: config.max_markets]:
        # Captured before the advance clears the dirt: the measurement
        # starts at the market's own timestamp, not at ours.
        waiting_since = market.last_input_ts
        evaluation = await scanner.advance(redis, market, batch, now=now)
        if evaluation is None:
            continue
        evaluated += 1
        await projections.publish_features(redis, scanner.producer, market.ref, evaluation)
        radar = projections.RADAR_NOTHING
        if evaluation.score is not None:
            radar = await projections.publish_radar(redis, market.ref, evaluation)
        delivered = radar != projections.RADAR_FAILED
        if evaluation.scored and delivered and waiting_since is not None:
            # After the publish, never before it: the budget is "tick to
            # opportunity", and an observation taken inside ``advance``
            # would leave the two projections outside the number that is
            # supposed to bound them (Astra, T2.5c design review).
            #
            # ``delivered`` is the second half of that: an observation whose
            # Radar row was refused by Redis was *not* delivered, and
            # counting it would report a latency for something nobody
            # can see (Astra, diff review, must-fix 2). An observation
            # with no usable score published nothing on purpose and is
            # still a finished cycle, which is what the histogram's help
            # text now says it measures.
            scanner_tick_to_opportunity_seconds.observe(
                max(0.0, (utcnow() - waiting_since).total_seconds())
            )
    return evaluated
