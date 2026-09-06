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
import time
from collections import defaultdict, deque
from typing import Any

from sqlalchemy import select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.market import NormalizedCandle
from hunter_core.logging import get_logger
from hunter_market_worker.persist_rows import (
    flush_batch,
    load_market_ids,
    upsert_candles,
    upsert_funding,
    upsert_liquidations,
)
from hunter_market_worker.queues import PersistItem, PersistQueues, item_bytes
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
FLUSH_INTERVAL_S = 1.0
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


async def report_losses(factory: Any, exchange: str, queues: PersistQueues) -> None:
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
        ids = await load_market_ids(session, exchange, {loss.item.symbol for loss in losses})
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
) -> None:
    producer = producer or f"market-worker@{getattr(runtime, 'instance', 'unknown')}"
    batch: list[PersistItem] = []
    batch_bytes = 0
    oldest = time.monotonic()
    warned = False
    while True:
        try:
            await report_losses(factory, exchange_code, queues)
        except Exception:
            runtime.mark_error()
            logger.exception("market_persist_report_losses_failed")
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

            logger.warning("market_persist_lag", lag_s=age)
            try:
                await record_system_event(
                    factory, "persistence_lag", f"lag={age:.1f}s", RiskEventSeverity.WARNING
                )
            except Exception:
                runtime.mark_error()
                logger.exception("market_persist_lag_report_failed")
            warned = True
        try:
            await asyncio.wait_for(
                flush_batch(factory, exchange_code, batch, producer=producer), timeout=10
            )
        except Exception:
            runtime.mark_error()
            logger.exception("market_persist_flush_failed", batch_size=len(batch))
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
        # The events for everything this flush inserted are already committed
        # alongside their rows; all that is left is to let the dispatcher know
        # there is work, so a closed candle does not wait out its poll interval.
        if outbox_wake is not None:
            outbox_wake.set()
        batch, batch_bytes, warned = [], 0, False
