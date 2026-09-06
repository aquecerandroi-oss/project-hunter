"""Persisted final candle coverage, durable gaps and transactional REST recovery."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.observability import market_ingestion_gaps
from hunter_market_worker import recovery_queries as queries
from hunter_market_worker.persist import load_market_ids
from hunter_market_worker.recovery_drain import expected_times, recover_one
from hunter_market_worker.supervision import rest_gate_suspended

logger = get_logger(__name__)
CHECK_INTERVAL_S = 60
POLL_S = 5
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

# T2.5-backfill: the history tier (gaps older than the detection window, i.e.
# whatever `market.backfill.requested` asked for) spends only what live
# collection left of MAX_GAPS_PER_CYCLE, never more than this many rows, and
# never more than HISTORY_BUDGET_S of wall time. The row ceiling bounds the
# REST weight (one 240-minute chunk is one klines page, weight 10 -> 60 of the
# 2400/min quota); the time ceiling is what actually protects the cadence,
# because six slow pages at FETCH_TIMEOUT_S each would be 120s and push the
# next detection two minutes late (Astra, must-fix 3).
MAX_HISTORY_GAPS_PER_CYCLE = 6
HISTORY_BUDGET_S = 30.0
MIN_FETCH_BUDGET_S = 3.0
CYCLE_TAIL_MARGIN_S = 5.0
"""How much of the detection interval is left to the bookkeeping after history.

The budget is a *deadline*, not a stopwatch started when history begins (Astra,
T2.5-backfill diff review, must-fix 2): with live collection spending 45s of the
60s cycle, a fresh 30s of history would make the cycle 81s and push the next
detection more than a minute late. :func:`history_deadline` therefore takes the
earlier of "30s from now" and "the cycle's own end", and the deadline bounds the
**whole** recovery unit — the reads and the write, not only the fetch."""

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


def history_deadline(
    cycle_start: float,
    now: float,
    *,
    budget_s: float | None = None,
    interval_s: float | None = None,
    margin_s: float | None = None,
) -> float:
    """Monotonic instant at which the history tier of this cycle must stop.

    The earlier of the tier's own budget and the cycle's end. Pure, so the
    arithmetic that protects the detection cadence is pinned by a test instead
    of being read off a running worker. The module constants are read **here**,
    not bound as defaults, so an operator (or a test) that changes one changes
    the behaviour.
    """
    budget = HISTORY_BUDGET_S if budget_s is None else budget_s
    interval = CHECK_INTERVAL_S if interval_s is None else interval_s
    margin = CYCLE_TAIL_MARGIN_S if margin_s is None else margin_s
    return min(cycle_start + interval - margin, now + budget)


async def check_gaps(
    session_factory: Any, adapter: Any, symbols: list[str], heartbeat_state: Any
) -> None:
    cycle_start = time.monotonic()
    now = await server_now(adapter)
    end = align_open_time(now, Timeframe.M1) - DETECTION_GRACE
    reopen_cutoff = now - timedelta(seconds=FAILED_RETRY_AFTER_S)

    async with role_session(session_factory, db_role="hunter_worker") as session:
        # Taken before the coverage is read: the backfill consumer creates rows
        # for the same markets through the same read-then-insert protocol, and
        # only a lock held across both halves keeps the two from inserting the
        # same minutes twice (recovery_queries.GAP_PLANNING_LOCK_NAMESPACE).
        await queries.lock_gap_planning(session, adapter.code)
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

        queries.reopen_stale_failed(market_gaps, reopen_cutoff, MAX_REOPEN_PER_CYCLE)

        for mid in market_ids:
            start = starts[mid]
            persisted = {t for t in by_market.get(mid, set()) if t >= start}
            gaps = market_gaps.get(mid, [])
            covered: set[datetime] = set()
            for gap in gaps:
                # Clipped to the detection window (T2.5-backfill): a backfill
                # request can leave seven-day gaps open, and expanding each one
                # to its minutes would build millions of datetimes per cycle to
                # subtract from a window that never contained them.
                if gap.gap_end < start:
                    continue
                covered |= expected_times(max(gap.gap_start, start), gap.gap_end)
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
        live, history = await queries.pending_gaps(
            session,
            market_ids,
            live_from=end - MINUTE * BOOTSTRAP_WINDOW_MINUTES,
            live_limit=MAX_GAPS_PER_CYCLE,
            history_limit=MAX_HISTORY_GAPS_PER_CYCLE,
        )
    symbol_by_market_id = {v: k for k, v in ids.items()}
    for gap_id, market_id in live:
        symbol = symbol_by_market_id.get(market_id)
        if symbol is None:
            continue
        await recover_one(session_factory, adapter, gap_id, symbol, now, tier="live")

    # History last, and under a wall-clock budget: what is left of the cycle
    # decides how much of a bootstrap gets served, never the other way round.
    deadline = history_deadline(cycle_start, time.monotonic())
    for gap_id, market_id in history:
        remaining = deadline - time.monotonic()
        symbol = symbol_by_market_id.get(market_id)
        if remaining < MIN_FETCH_BUDGET_S:
            logger.info("market_backfill_budget_spent", exchange=adapter.code, left=len(history))
            break
        if symbol is None:
            continue
        try:
            # The deadline wraps the **unit**, not only the fetch: the reads,
            # the row lock and the write are on the cycle's clock too. A unit
            # cancelled here rolls its transaction back, so the budget running
            # out never spends one of the gap's MAX_ATTEMPTS — that is the
            # difference between "we ran out of time" and "this gap failed".
            async with asyncio.timeout(remaining):
                # ``timeout_s`` stays the adapter's own budget on purpose. If
                # the *cycle* is what cut the call short, the cancellation must
                # come from the deadline above — which rolls back — and not from
                # the gap's own timeout, which would spend an attempt on a slow
                # cycle rather than on a slow exchange.
                await recover_one(session_factory, adapter, gap_id, symbol, now, tier="history")
        except TimeoutError:
            logger.warning("market_backfill_unit_timeout", symbol=symbol, budget_s=remaining)
            break

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
    waiting_for_gate = False
    while True:
        await asyncio.sleep(POLL_S)
        now = time.monotonic()
        if not _should_check(
            now, last_check, heartbeat_state.reconnects, last_reconnects, universe.symbols
        ):
            continue
        if rest_gate_suspended(adapter):
            # Deliberately *before* ``last_check`` is consumed, so the next
            # poll retries in POLL_S instead of a whole CHECK_INTERVAL_S: the
            # gate can re-open at any moment and the backlog should not wait
            # a minute more than the outage lasted. Not a worker error.
            if not waiting_for_gate:
                logger.warning("market_recovery_waiting_for_rest_gate", exchange=adapter.code)
                waiting_for_gate = True
            continue
        if waiting_for_gate:
            logger.info("market_recovery_rest_gate_reopened", exchange=adapter.code)
            waiting_for_gate = False
        last_check, last_reconnects = now, heartbeat_state.reconnects
        try:
            await check_gaps(session_factory, adapter, universe.symbols, heartbeat_state)
            runtime.mark_success()
        except Exception:
            logger.exception("market_recovery_failed")
            runtime.mark_error()
