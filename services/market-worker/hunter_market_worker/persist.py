"""Bounded batch persistence, retrying failures without silently clearing the batch.

T2.9: the flush no longer publishes anything itself. Every durable event is
queued inside the flush transaction (``persist_rows``/``durable``); when that
transaction commits, the loop only *wakes* the outbox dispatcher. The
publication therefore never runs on the drain's hot path, so a stalled Redis
can no longer delay the next flush and age the queue out — it just leaves the
backlog visible in ``outbox_events`` (Astra, T2.9 round 1).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from typing import Any

from sqlalchemy import select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, RiskEventSeverity
from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_market_worker.latency import observe_flush_lag
from hunter_market_worker.persist_rows import (
    flush_batch,
    load_market_ids,
    upsert_candles,
    upsert_funding,
    upsert_liquidations,
)
from hunter_market_worker.queues import PersistItem, PersistQueues, item_bytes
from hunter_market_worker.recovery_queries import try_lock_gap_planning
from hunter_market_worker.sampling import oi_poll_loop, snapshot_loop, write_snapshots

__all__ = [
    "PersistQueues",
    "load_market_ids",
    "upsert_candles",
    "flush_batch",
    "upsert_funding",
    "upsert_liquidations",
    "oi_poll_loop",
    "snapshot_loop",
    "write_snapshots",
]
logger = get_logger(__name__)


def _flush_interval_s() -> float:
    """T3.81: how long a batch may sit before it is written, in seconds.

    Was a hardcoded 1.0s. Measured on the VPS (``notes-T3.81.md`` §1): almost
    every final candle of a minute lands within ~0-2s of the bar close (a mix
    of Binance's own emission jitter and our WS parse time), and the old fixed
    1.0s wait did two things wrong at once — it forced the *common* case (a
    candle that was ready to flush within a couple hundred ms) to sit idle for
    the rest of a full second, **and** it forced any straggler that missed
    that first batch's cutoff to wait a second *full* second of its own before
    its own batch flushed, compounding the exchange's own jitter instead of
    absorbing it. ``MARKET_CANDLE_FLUSH_MS`` (default 200ms, the same cadence
    ``tick_coalesce_ms`` already uses for the ephemeral path) still batches
    everything that lands within one short window into a single write, but
    stops padding every candle's latency with up to a second of dead time.
    Read once at import (into the ``FLUSH_INTERVAL_S`` module constant below),
    exactly like the old hardcoded value — a test that needs a different
    number monkeypatches ``persist.FLUSH_INTERVAL_S`` directly, same as every
    existing test in this suite already does, rather than the environment.
    """
    return float(os.environ.get("MARKET_CANDLE_FLUSH_MS", "200")) / 1000


FLUSH_INTERVAL_S = _flush_interval_s()
FLUSH_MAX_ROWS = 500
FLUSH_MAX_BYTES = 1024 * 1024
LAG_WARNING_S = 10.0


GapKey = tuple[Any, Any, Any]  # (market_id, timeframe, open_time)


async def _uncovered_gap_keys(session: Any, keys: set[GapKey]) -> set[GapKey]:
    """Which of ``keys`` still need an ``ingestion_gaps`` row (MEDIUM-8):
    neither already persisted as a candle nor already covered by an existing
    open/failed gap. Exactly one query per check, regardless of batch size."""
    market_ids = {key[0] for key in keys}
    timeframes = {key[1] for key in keys}
    persisted = await session.execute(
        select(Candle.market_id, Candle.timeframe, Candle.open_time).where(
            Candle.market_id.in_(market_ids),
            Candle.timeframe.in_(timeframes),
            Candle.open_time.in_({key[2] for key in keys}),
        )
    )
    persisted_keys = {(row.market_id, row.timeframe, row.open_time) for row in persisted}
    existing_gaps = await session.execute(
        select(
            IngestionGap.market_id,
            IngestionGap.timeframe,
            IngestionGap.gap_start,
            IngestionGap.gap_end,
        ).where(
            IngestionGap.market_id.in_(market_ids),
            IngestionGap.timeframe.in_(timeframes),
            IngestionGap.status.in_(("open", "failed")),
        )
    )
    gap_ranges: dict[tuple[Any, Any], list[tuple[Any, Any]]] = defaultdict(list)
    for row in existing_gaps:
        gap_ranges[(row.market_id, row.timeframe)].append((row.gap_start, row.gap_end))

    def covered(key: GapKey) -> bool:
        market_id, timeframe, open_time = key
        return key in persisted_keys or any(
            start <= open_time <= end for start, end in gap_ranges.get((market_id, timeframe), [])
        )

    return {key for key in keys if not covered(key)}


async def report_losses(
    factory: Any,
    exchange: str,
    queues: PersistQueues,
    market_type: MarketType = MarketType.PERPETUAL,
) -> None:
    """Best-effort: a failure here must never propagate (H1) — the loss is
    already recorded in ``losses_total``; failing to also write the
    ``system_events``/``ingestion_gaps`` rows for it is degraded, not fatal.
    ``queues.losses`` is only drained after everything below committed, and
    the drain removes exactly the reported entries by identity (D2) — a plain
    ``popleft() * len(reported)`` would, under concurrent eviction from the
    bounded (``maxlen``) deque, remove brand-new never-reported losses instead
    of (already-evicted) reported ones.
    """
    losses = list(queues.losses)
    if not losses:
        return
    async with role_session(factory, db_role="hunter_worker") as session:
        # The third writer of ``ingestion_gaps``, and it runs the same
        # read-then-insert protocol as the periodic detection and the backfill
        # consumer: it must take the same transaction-scoped advisory lock
        # before reading coverage, or a dropped candle and a backfill request
        # both read "missing, no gap" and both insert (Astra, T2.5-backfill
        # diff review, must-fix 3).
        if not await try_lock_gap_planning(session, exchange):
            # Never wait here: this runs once per drain iteration and a
            # detection cycle holds the lock for as long as it reads 200
            # markets. The losses stay queued for the next iteration.
            logger.debug(
                "market_loss_report_deferred", exchange=exchange, market_type=market_type.value
            )
            return
        ids = await load_market_ids(
            session, exchange, {loss.item.symbol for loss in losses}, market_type
        )
        final_candle_keys: set[GapKey] = set()
        for loss in losses:
            item = loss.item
            session.add(
                SystemEvent(
                    level=RiskEventSeverity.WARNING,
                    component="market-worker",
                    event="persistence_drop",
                    message=f"{item.kind} {item.symbol}: {loss.reason}",
                )
            )
            if isinstance(item, NormalizedCandle) and item.is_final and item.symbol in ids:
                # a set, not a list: the same final candle dropped twice in one
                # report must open exactly one gap (MEDIUM-8).
                final_candle_keys.add((ids[item.symbol], item.timeframe, item.open_time))
        if final_candle_keys:
            to_open = await _uncovered_gap_keys(session, final_candle_keys)
            for market_id, timeframe, open_time in to_open:
                session.add(
                    IngestionGap(
                        market_id=market_id,
                        timeframe=timeframe,
                        gap_start=open_time,
                        gap_end=open_time,
                        status="open",
                        attempts=0,
                    )
                )
    reported_ids = {id(loss) for loss in losses}
    queues.losses = deque(
        (loss for loss in queues.losses if id(loss) not in reported_ids),
        maxlen=queues.losses.maxlen,
    )


async def drain_loop(
    factory: Any,
    exchange_code: str,
    queues: PersistQueues,
    runtime: Any,
    outbox_wake: asyncio.Event | None = None,
    producer: str | None = None,
    market_type: MarketType = MarketType.PERPETUAL,
) -> None:
    """``market_type`` (T3.0c): one drain loop per product, each over its own
    queue. See :func:`flush_batch` for why a mixed batch cannot be resolved."""
    producer = producer or f"market-worker@{getattr(runtime, 'instance', 'unknown')}"
    batch: list[PersistItem] = []
    batch_bytes = 0
    oldest = time.monotonic()
    warned = False
    while True:
        try:
            await report_losses(factory, exchange_code, queues, market_type)
        except Exception:
            runtime.mark_error()
            logger.exception("market_persist_report_losses_failed", market_type=market_type.value)
        if not batch:
            try:
                item = await asyncio.wait_for(queues.events.get(), FLUSH_INTERVAL_S)
            except TimeoutError:
                continue
            batch = [item]
            batch_bytes = item_bytes(item)
            oldest = queues.events.last_taken_at
            if time.monotonic() - oldest >= queues.max_age:
                queues.drop(item, "age")
                batch = []
                continue
            queues.in_flight = True
        while (
            not queues.events.empty()
            and len(batch) < FLUSH_MAX_ROWS
            and batch_bytes < FLUSH_MAX_BYTES
        ):
            item = queues.events.get_nowait()
            batch.append(item)
            batch_bytes += item_bytes(item)
        age = time.monotonic() - oldest
        if age < FLUSH_INTERVAL_S and len(batch) < FLUSH_MAX_ROWS and batch_bytes < FLUSH_MAX_BYTES:
            await asyncio.sleep(min(0.05, FLUSH_INTERVAL_S - age))
            continue
        if age > LAG_WARNING_S and not warned:
            from hunter_market_worker.heartbeat import record_system_event

            logger.warning("market_persist_lag", lag_s=age, market_type=market_type.value)
            try:
                await record_system_event(
                    factory, "persistence_lag", f"lag={age:.1f}s", RiskEventSeverity.WARNING
                )
            except Exception:
                runtime.mark_error()
                logger.exception("market_persist_lag_report_failed", market_type=market_type.value)
            warned = True
        try:
            await asyncio.wait_for(
                flush_batch(
                    factory, exchange_code, batch, producer=producer, market_type=market_type
                ),
                timeout=10,
            )
        except Exception:
            runtime.mark_error()
            logger.exception(
                "market_persist_flush_failed", batch_size=len(batch), market_type=market_type.value
            )
            if time.monotonic() - oldest >= queues.max_age:
                for item in batch:
                    queues.drop(item, "age")
                batch = []
                queues.in_flight = False
            await asyncio.sleep(FLUSH_INTERVAL_S)
            continue
        queues.last_flush = queues.clock()
        queues.in_flight = False
        runtime.mark_success()
        # T3.79: bar close -> "durably queued for the outbox" (the dispatcher's
        # own wake-triggered publish, below, adds only its own publication on
        # top). Every final candle *attempted* in this batch, not only the ones
        # ``ON CONFLICT DO NOTHING`` actually inserted -- a redelivered minute
        # is measured again, a known simplification for a diagnostic gauge
        # (hunter_market_worker.latency module docstring).
        observe_flush_lag(
            (item for item in batch if isinstance(item, NormalizedCandle)), now=utcnow()
        )
        # The events for everything this flush inserted are already committed
        # alongside their rows; all that is left is to let the dispatcher know
        # there is work, so a closed candle does not wait out its poll interval.
        if outbox_wake is not None:
            outbox_wake.set()
        batch, batch_bytes, warned = [], 0, False
