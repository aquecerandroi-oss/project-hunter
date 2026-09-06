"""Repairing one registered gap: fetch it over REST and write it atomically.

Split out of ``recovery.py`` for the 350-line budget, along a real seam:
``recovery.py`` decides **what** to repair (detection, tiers, budgets) and this
module executes **one** repair — the fetch, the filters that decide which
candles belong to the gap, and the transaction where the candles, the outbox
row(s) and the gap's status transition commit or roll back together.

T2.9c: which outbox row(s) depends on ``tier``, the classification
``recovery.check_gaps`` already computed before calling in. The *live* tier
(the default) announces every inserted minute as its own
``market.candles.closed``, unchanged since T2.9. The *history* tier announces
the whole batch this call actually inserts as one aggregate
``market.candles.backfilled`` instead — publishing history one minute at a
time was measured queuing up to 1,440 events/cycle ahead of live candles in
the dispatcher's ``(created_at, id)`` order (notes-T2.5.md §28, §31;
notes-T2.9.md T2.9c).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.logging import get_logger
from hunter_core.observability import candle_gaps_total
from hunter_exchanges.rate_limit_suspension import is_coordination_outage
from hunter_market_worker import recovery_queries as queries
from hunter_market_worker.backfill_announce import enqueue_candles_backfilled
from hunter_market_worker.persist import upsert_candles
from hunter_market_worker.supervision import rest_gate_suspended

Tier = Literal["live", "history"]
HISTORICAL_RECOVERY_REASON = "historical_recovery"
"""Fixed ``reason`` for every ``market.candles.backfilled`` event: describes
*why this is history* (the window aged past the live threshold), never a
claim about who asked for it -- ``ingestion_gaps`` carries no origin, and a
gap the live tier itself created can age into history without any
``market.backfill.requested`` ever existing
(``recovery_queries.pending_gaps`` docstring; notes-T2.9.md T2.9c)."""

logger = get_logger(__name__)
MINUTE = timedelta(minutes=1)
MAX_ATTEMPTS = 5
FETCH_TIMEOUT_S = 20.0


def expected_times(start: datetime, end: datetime) -> set[datetime]:
    return {start + MINUTE * n for n in range(int((end - start) / MINUTE) + 1)}


async def recover_registered(
    session: Any,
    adapter: Any,
    gap: IngestionGap,
    symbol: str,
    now: datetime,
    *,
    candles: list[Any] | None = None,
    fetch_error: BaseException | None = None,
    timeout_s: float = FETCH_TIMEOUT_S,
    tier: Tier = "live",
) -> None:
    """Atomically backfill one gap: candles and the status transition commit
    (or roll back) together via ``begin_nested``.

    ``candles``/``fetch_error`` let a caller fetch over REST *before* opening
    this transaction (M3) — pass neither to fetch here as before (used
    directly by tests and by any caller that already holds a short-lived
    connection budget).

    ``tier`` is the caller's own classification (``recovery.check_gaps``
    already tells live collection apart from history by the age of the gap's
    window before it ever reaches here, PIPELINE.md §1b item 7) — this
    function does not infer it. ``"history"`` (T2.9c) announces the whole
    batch this call actually inserts as one aggregate
    ``market.candles.backfilled`` event instead of one ``market.candles.closed``
    per minute, in the same transaction as the candles and the status
    transition.
    """
    gap.attempts += 1
    try:
        if fetch_error is not None:
            raise fetch_error
        if candles is None:
            candles = await asyncio.wait_for(
                adapter.fetch_candles(symbol, Timeframe.M1, gap.gap_start, gap.gap_end + MINUTE),
                timeout=timeout_s,
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
            # ``upsert_candles`` queues one ``market.candles.closed`` per
            # inserted minute for the live tier -- a recovered candle
            # announced exactly like a live one (T2.9). The history tier
            # (T2.9c) opts out of that and gets the actually-inserted batch
            # back instead, to announce as one aggregate event below, in this
            # same transaction.
            newly_inserted: list[Any] = []
            inserted = await upsert_candles(
                session,
                closed,
                {symbol: gap.market_id},
                source="rest",
                announce=tier != "history",
                collected=newly_inserted if tier == "history" else None,
            )
            if tier == "history" and newly_inserted:
                await enqueue_candles_backfilled(
                    session, newly_inserted, reason=HISTORICAL_RECOVERY_REASON
                )
            present = await queries.persisted(session, gap.market_id, gap.gap_start, gap.gap_end)
            if expected_times(gap.gap_start, gap.gap_end) <= present:
                gap.status = "recovered"
                gap.recovered_at = now
                candle_gaps_total.labels(exchange=adapter.code).inc()
                logger.info("market_gap_recovered", symbol=symbol, candles_inserted=inserted)
    except Exception as exc:
        if is_coordination_outage(exc) or rest_gate_suspended(adapter):
            # T2.9: the outage started mid-cycle, after the gate was checked.
            # It must not spend an attempt towards MAX_ATTEMPTS, which would
            # park the gap as ``failed`` for FAILED_RETRY_AFTER_S.
            #
            # The *state* of the gate decides, not only the exception type
            # (Astra, round 4): FETCH_TIMEOUT_S is 20s and the limiter's
            # max_wait_s is 30s, so the usual way this shows up is the fetch
            # being cancelled by the timeout long before ``acquire`` gets to
            # raise ``RateLimited(reason="redis_unavailable")``.
            gap.attempts -= 1  # an infrastructure outage is not this gap's fault
            logger.warning("market_gap_deferred_rest_gate", symbol=symbol)
            return
        logger.exception("market_gap_backfill_failed", symbol=symbol, attempt=gap.attempts)
    if gap.status != "recovered" and gap.attempts >= MAX_ATTEMPTS:
        gap.status = "failed"
        # D6/Astra: detected_at is the only durable clock the cooldown has.
        # Refresh it on every re-failure, not just the original detection --
        # otherwise a gap reopened once and then failing again would already
        # be past FAILED_RETRY_AFTER_S and get reopened on the very next
        # cycle, turning the cooldown into a tight retry loop.
        gap.detected_at = now


async def recover_one(
    session_factory: Any,
    adapter: Any,
    gap_id: Any,
    symbol: str,
    now: datetime,
    *,
    timeout_s: float = FETCH_TIMEOUT_S,
    tier: Tier = "live",
) -> None:
    """M3: fetch over REST with no transaction open, then re-check the gap
    ``FOR UPDATE`` and write in one short transaction. ``tier`` passes
    through to :func:`recover_registered` unchanged."""
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
            timeout=timeout_s,
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
            session,
            adapter,
            gap,
            symbol,
            now,
            candles=candles,
            fetch_error=fetch_error,
            timeout_s=timeout_s,
            tier=tier,
        )
