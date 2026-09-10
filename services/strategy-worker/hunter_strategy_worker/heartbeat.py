"""``hb:strategy:shadow`` — the Lab's own heartbeat.

The runtime already writes the generic ``hb:{role}:{instance}``. This one is
scoped to the experiment and carries what an operator (and Sexta-feira's shift
report) actually needs to see: how many bars were evaluated and with which
outcome per state, how many trackings are open, and how far behind the outbox
is. Zero signals is a valid result — but only readable next to the number of
evaluations that produced it.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker.metrics import decision_lag_percentiles
from hunter_strategy_worker.shard import heartbeat_key
from hunter_strategy_worker.tracking_repo import load_open_trackings

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.consumer import ConsumerHealth
    from hunter_strategy_worker.outbox import OutboxHealth

logger = get_logger(__name__)
INTERVAL_S = 10
TTL_S = 60

__all__ = ["run_heartbeat", "write_heartbeat"]


async def write_heartbeat(
    runtime: WorkerRuntime,
    config: ShadowConfig,
    consumer: ConsumerHealth,
    outbox: OutboxHealth,
    *,
    open_trackings: int | None = None,
    shard_index: int = 0,
    shard_total: int = 1,
) -> None:
    """One ``HSET`` + ``EXPIRE`` of this shard's own heartbeat key.

    T3.74f: ``shard_total <= 1`` writes ``hb:strategy:shadow`` unchanged; a
    sharded deployment writes ``hb:strategy:shadow:{i}of{N}`` instead
    (:func:`hunter_strategy_worker.config.heartbeat_key`), mirroring
    ``hunter_market_worker.heartbeat.hb_key``'s convention closely enough
    that the API's generic ``/system/workers`` scan
    (``parse_heartbeat_key``, splits on the first ``:``) shows one row per
    shard with no change on that side -- the two extra fields below are what
    a reader needs to tell "N shards, this is one of them" from "one of N
    is missing", the same pair ``hb:market:*`` already carries.
    """
    lag_p50, lag_p95 = decision_lag_percentiles()
    key = heartbeat_key(shard_index, shard_total)
    payload = {
        "ts": utcnow().isoformat(),
        "instance": runtime.instance,
        "cohort": config.cohort,
        "shard_index": str(shard_index),
        "shard_total": str(shard_total),
        "evaluated_bars": str(consumer.evaluated_bars),
        "evaluations_by_state": orjson.dumps(consumer.states).decode(),
        "errors": str(consumer.errors),
        "outbox_pending": str(outbox.pending),
        "outbox_lag_s": f"{outbox.lag_s():.1f}",
        "open_trackings": "" if open_trackings is None else str(open_trackings),
        "last_iteration": (
            consumer.last_iteration_at.isoformat() if consumer.last_iteration_at else ""
        ),
        # T3.74c: the bar-close-to-persisted-decision latency this process has
        # actually seen, last 500 signals -- see metrics.py for why this is
        # not read out of the Prometheus histogram instead.
        "decision_lag_p50_s": "" if lag_p50 is None else f"{lag_p50:.1f}",
        "decision_lag_p95_s": "" if lag_p95 is None else f"{lag_p95:.1f}",
        # T3.82: the shadow universe policy. The threshold is always present
        # (part of this process's config, "0" means disabled); the counts are
        # "" until the first perpetual bar refreshes the cache, and forever
        # "" while disabled -- hunter_strategy_worker.universe module docstring.
        "universe_min_history_days": str(config.universe_min_history_days),
        "universe_size": "" if consumer.universe_size is None else str(consumer.universe_size),
        "universe_total": "" if consumer.universe_total is None else str(consumer.universe_total),
    }
    await cast("Any", runtime.redis).hset(key, mapping=payload)
    await runtime.redis.expire(key, TTL_S)


async def run_heartbeat(
    runtime: WorkerRuntime,
    config: ShadowConfig,
    consumer: ConsumerHealth,
    outbox: OutboxHealth,
    *,
    shard_index: int = 0,
    shard_total: int = 1,
) -> None:
    """Write the heartbeat forever; a failure is logged, never fatal.

    ``open_trackings`` is a cluster-wide count (every open tracking, not just
    this shard's own markets -- ``load_open_trackings`` is unpartitioned by
    design, T3.74f), so only shard 0 pays for it; every other shard reports
    an empty value for that one field, same as when the query itself fails.
    """
    factory = None
    while True:
        open_trackings: int | None = None
        if shard_index == 0:
            try:
                if factory is None:
                    from hunter_core.db.session import create_session_factory

                    factory = create_session_factory(runtime.engine)
                async with role_session(factory, db_role="hunter_worker") as session:
                    open_trackings = len(await load_open_trackings(session, limit=10_000))
            except Exception:
                logger.warning("shadow_heartbeat_count_failed")
        try:
            await write_heartbeat(
                runtime,
                config,
                consumer,
                outbox,
                open_trackings=open_trackings,
                shard_index=shard_index,
                shard_total=shard_total,
            )
        except Exception:
            logger.warning("shadow_heartbeat_write_failed")
        await asyncio.sleep(INTERVAL_S)
