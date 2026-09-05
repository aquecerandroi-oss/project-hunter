"""Persisted final candle coverage, durable gaps and transactional REST recovery."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.observability import candle_gaps_total, market_ingestion_gaps
from hunter_market_worker import recovery_queries as queries
from hunter_market_worker.persist import load_market_ids, upsert_candles

logger = get_logger(__name__)
CHECK_INTERVAL_S = 60
POLL_S = 5
MAX_ATTEMPTS = 5
MINUTE = timedelta(minutes=1)

# D5: the persistence queue (queues.py PersistQueues.max_age) tolerates up to
# 60s of drain lag by design, so the final candle of a minute can still be
# sitting in the queue, not yet in Postgres, a full minute after its close.
# A grace of two minutes (one more than that tolerance) keeps check_gaps from
# reading that lag as a gap and firing a REST backfill for it.
DETECTION_GRACE = 2 * MINUTE

# M3: bound the REST work of one cycle so a slow backlog cannot push gap
# detection past its one-minute cadence, and give every backfill call a hard
# ceiling instead of letting one stuck connection block the rest.
MAX_GAPS_PER_CYCLE = 50
FETCH_TIMEOUT_S = 20.0

# D6 + MEDIUM-5: a `failed` gap is retried instead of permanently suppressing
# those minutes from `missing`; reopening is bounded per cycle so a bad patch
# of history cannot flood the backfill queue in one pass.
FAILED_RETRY_AFTER_S = 3600
MAX_REOPEN_PER_CYCLE = 20

# How far back a market with no watermark yet (bootstrap) vs. one already
# caught up (steady state) is expected to have final candles.
BOOTSTRAP_WINDOW_MINUTES = 1499
STEADY_WINDOW_MINUTES = 1439


async def server_now(adapter: Any) -> datetime:
    method = getattr(adapter, "server_time", None)
    if method is None:
        logger.warning("market_server_time_unavailable", exchange=adapter.code, fallback="utcnow")
        return utcnow()
    return await method()


def expected_times(start: datetime, end: datetime) -> set[datetime]:
    return {start + MINUTE * n for n in range(int((end - start) / MINUTE) + 1)}


def _missing_ranges(
    start: datetime, end: datetime, persisted: set[datetime], covered: set[datetime]
) -> list[tuple[datetime, datetime]]:
    missing = sorted(expected_times(start, end) - persisted - covered)
    ranges: list[tuple[datetime, datetime]] = []
    while missing:
        first = last = missing.pop(0)
        while missing and missing[0] == last + MINUTE:
            last = missing.pop(0)
        ranges.append((first, last))
    return ranges


def _reopen_stale_failed(
    gaps_by_market: dict[Any, list[IngestionGap]], cutoff: datetime, max_reopen: int
) -> int:
    """D6: a `failed` gap older than ``cutoff`` gets one more try instead of
    permanently subtracting its minutes from ``missing``. Bounded per cycle."""
    reopened = 0
    for gaps in gaps_by_market.values():
        for gap in gaps:
            if reopened >= max_reopen:
                return reopened
            if gap.status == "failed" and gap.detected_at <= cutoff:
                gap.status = "open"
                gap.attempts = 0
                reopened += 1
                logger.info(
                    "market_gap_reopened",
                    market_id=gap.market_id,
                    gap_start=gap.gap_start,
                    gap_end=gap.gap_end,
                )
    return reopened


async def recover_registered(
    session: Any,
    adapter: Any,
    gap: IngestionGap,
    symbol: str,
    now: datetime,
    *,
    candles: list[Any] | None = None,
    fetch_error: BaseException | None = None,
) -> None:
    """Atomically backfill one gap: candles and the status transition commit
    (or roll back) together via ``begin_nested``.

    ``candles``/``fetch_error`` let a caller fetch over REST *before* opening
    this transaction (M3) — pass neither to fetch here as before (used
    directly by tests and by any caller that already holds a short-lived
    connection budget).
    """
    gap.attempts += 1
    try:
        if fetch_error is not None:
            raise fetch_error
        if candles is None:
            candles = await asyncio.wait_for(
                adapter.fetch_candles(symbol, Timeframe.M1, gap.gap_start, gap.gap_end + MINUTE),
                timeout=FETCH_TIMEOUT_S,
            )
        candles = candles or []
        closed = [
            c
            for c in candles
            if c.symbol == symbol
            and c.timeframe == Timeframe.M1
            and c.is_final
            and c.close_time <= now
            and gap.gap_start <= c.open_time <= gap.gap_end
        ]
        if closed:
            # M2: a market listed after gap_start never has candles for the
            # minutes before it existed. An adapter that actually returned
            # candles, starting later than requested, means history simply
            # does not go back further — narrow the gap instead of demanding
            # the impossible range forever.
            earliest = min(c.open_time for c in closed)
            if earliest > gap.gap_start:
                logger.info(
                    "market_gap_history_starts_later",
                    symbol=symbol,
                    old_start=gap.gap_start,
                    new_start=earliest,
                )
                gap.gap_start = earliest
        async with session.begin_nested():
            inserted = await upsert_candles(session, closed, {symbol: gap.market_id}, source="rest")
            present = await queries.persisted(session, gap.market_id, gap.gap_start, gap.gap_end)
            if expected_times(gap.gap_start, gap.gap_end) <= present:
                gap.status = "recovered"
                gap.recovered_at = now
                candle_gaps_total.labels(exchange=adapter.code).inc()
                logger.info("market_gap_recovered", symbol=symbol, candles_inserted=inserted)
    except Exception:
        logger.exception("market_gap_backfill_failed", symbol=symbol, attempt=gap.attempts)
    if gap.status != "recovered" and gap.attempts >= MAX_ATTEMPTS:
        gap.status = "failed"
        # D6/Astra: detected_at is the only durable clock the cooldown has.
        # Refresh it on every re-failure, not just the original detection --
        # otherwise a gap reopened once and then failing again would already
        # be past FAILED_RETRY_AFTER_S and get reopened on the very next
        # cycle, turning the cooldown into a tight retry loop.
        gap.detected_at = now


async def _recover_one(
    session_factory: Any, adapter: Any, gap_id: Any, symbol: str, now: datetime
) -> None:
    """M3: fetch over REST with no transaction open, then re-check the gap
    ``FOR UPDATE`` and write in one short transaction."""
    async with role_session(session_factory, db_role="hunter_worker") as session:
        gap = await session.scalar(
            select(IngestionGap).where(IngestionGap.id == gap_id, IngestionGap.status == "open")
        )
        if gap is None:
            return
        gap_start, gap_end = gap.gap_start, gap.gap_end

    fetch_error: BaseException | None = None
    candles: list[Any] = []
    try:
        candles = await asyncio.wait_for(
            adapter.fetch_candles(symbol, Timeframe.M1, gap_start, gap_end + MINUTE),
            timeout=FETCH_TIMEOUT_S,
        )
    except Exception as exc:
        fetch_error = exc

    async with role_session(session_factory, db_role="hunter_worker") as session:
        gap = await session.scalar(
            select(IngestionGap)
            .where(IngestionGap.id == gap_id, IngestionGap.status == "open")
            .with_for_update()
        )
        if gap is None:
            return
        await recover_registered(
            session, adapter, gap, symbol, now, candles=candles, fetch_error=fetch_error
        )


async def check_gaps(
    session_factory: Any, adapter: Any, symbols: list[str], heartbeat_state: Any
) -> None:
    now = await server_now(adapter)
    end = align_open_time(now, Timeframe.M1) - DETECTION_GRACE
    reopen_cutoff = now - timedelta(seconds=FAILED_RETRY_AFTER_S)

    async with role_session(session_factory, db_role="hunter_worker") as session:
        ids = await load_market_ids(session, adapter.code, set(symbols))
        market_ids = list(ids.values())
        market_watermarks = await queries.watermarks(session, market_ids)
        starts = {
            mid: end
            - MINUTE
            * (
                BOOTSTRAP_WINDOW_MINUTES
                if market_watermarks[mid] is None
                else STEADY_WINDOW_MINUTES
            )
            for mid in market_ids
        }
        global_start = min(starts.values()) if starts else end
        by_market = await queries.persisted_by_market(session, market_ids, global_start, end)
        market_gaps = await queries.gaps_by_market(session, market_ids, ("open", "failed"))

        _reopen_stale_failed(market_gaps, reopen_cutoff, MAX_REOPEN_PER_CYCLE)

        for mid in market_ids:
            start = starts[mid]
            persisted = {t for t in by_market.get(mid, set()) if t >= start}
            gaps = market_gaps.get(mid, [])
            covered: set[datetime] = set()
            for gap in gaps:
                covered |= expected_times(gap.gap_start, gap.gap_end)
            for first, last in _missing_ranges(start, end, persisted, covered):
                session.add(
                    IngestionGap(
                        market_id=mid,
                        timeframe=Timeframe.M1,
                        gap_start=first,
                        gap_end=last,
                        status="open",
                        attempts=0,
                    )
                )
        await session.flush()

    # M3: bound the per-cycle backfill work and fetch outside any open
    # transaction/lock (moved off the detection session above).
    async with role_session(session_factory, db_role="hunter_worker") as session:
        pending = (
            await session.execute(
                select(IngestionGap.id, IngestionGap.market_id)
                .where(IngestionGap.market_id.in_(market_ids), IngestionGap.status == "open")
                .order_by(IngestionGap.detected_at, IngestionGap.id)
                .limit(MAX_GAPS_PER_CYCLE)
            )
        ).all()
    symbol_by_market_id = {v: k for k, v in ids.items()}
    for gap_id, market_id in pending:
        symbol = symbol_by_market_id.get(market_id)
        if symbol is None:
            continue
        await _recover_one(session_factory, adapter, gap_id, symbol, now)

    async with role_session(session_factory, db_role="hunter_worker") as session:
        open_count = await queries.count_by_status(session, market_ids, "open")
        failed_count = await queries.count_by_status(session, market_ids, "failed")
    heartbeat_state.open_gaps = open_count
    market_ingestion_gaps.labels(exchange=adapter.code, status="open").set(open_count)
    market_ingestion_gaps.labels(exchange=adapter.code, status="failed").set(failed_count)


def _should_check(
    now: float, last_check: float, reconnects: int, last_reconnects: int, symbols: list[str]
) -> bool:
    """L3: the cadence gate — pinned by a unit test so an inverted operator
    or a swapped comparison fails loudly instead of silently changing how
    often gaps are detected."""
    if not symbols:
        return False
    if reconnects != last_reconnects:
        return True
    return now - last_check >= CHECK_INTERVAL_S


async def run_recovery(
    session_factory: Any, adapter: Any, universe: Any, heartbeat_state: Any, runtime: Any
) -> None:
    last_check = float("-inf")
    last_reconnects = heartbeat_state.reconnects
    while True:
        await asyncio.sleep(POLL_S)
        now = time.monotonic()
        if not _should_check(
            now, last_check, heartbeat_state.reconnects, last_reconnects, universe.symbols
        ):
            continue
        last_check, last_reconnects = now, heartbeat_state.reconnects
        try:
            await check_gaps(session_factory, adapter, universe.symbols, heartbeat_state)
            runtime.mark_success()
        except Exception:
            logger.exception("market_recovery_failed")
            runtime.mark_error()
