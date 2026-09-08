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
from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity, Timeframe
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

BEFORE_LISTING_REASON = "before_listing"
"""T3.7d: the terminal reason for a gap whose whole window is provably before
the market's first known candle -- the exact shape of the 2026-09-08 incident
(`.claude/state/notes-T3.7b-diag.md`): `MARSCOINUSDT` was listed mid-request,
and its four pre-listing windows returned ``200 OK`` with zero candles,
forever, because the exchange will never have data for them."""

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
    earliest_known: datetime | None = None,
    earliest_known_stale: bool = False,
) -> datetime | None:
    """Atomically backfill one gap: candles and the status transition commit
    (or roll back) together via ``begin_nested``.

    ``candles``/``fetch_error`` let a caller fetch over REST *before* opening
    this transaction (M3) — pass neither to fetch here as before (used
    directly by tests and by any caller that already holds a short-lived
    connection budget).

    ``tier`` is the caller's own classification (``recovery.check_gaps``
    already tells live collection apart from history by the age of the gap's
    window before it ever reaches here, PIPELINE.md §1b item 11) — this
    function does not infer it. ``"history"`` (T2.9c) announces the whole
    batch this call actually inserts as one aggregate
    ``market.candles.backfilled`` event instead of one ``market.candles.closed``
    per minute, in the same transaction as the candles and the status
    transition.

    ``earliest_known`` (T3.7d, revised T3.7e) is ``recovery_lifecycle.earliest``'s
    answer for this gap's market, read once at the *start* of this cycle --
    the first final candle this worker has ever persisted for it, or
    ``None`` if it has none yet. A gap entirely older than that is
    *suspected* of being before the market's listing, but T3.7e no longer
    concludes that from ``earliest_known`` alone (reviewer's MEDIUM: a deep
    ``request_backfill.py --days 90`` can make ``earliest_known`` only the
    start of *live* collection, not the listing). The window is fetched
    exactly once, and only an actual empty (``200``, zero rows) response for
    it, together with ``gap.gap_end < earliest_known``, concludes
    ``unrecoverable`` (``reason=before_listing``) -- logged to
    ``system_events``. A non-empty response means ``earliest_known`` was
    wrong, and the gap recovers (or narrows, M2) like any other.

    ``earliest_known_stale`` (T3.7e) is the caller's bookkeeping for the
    defect this revision fixes: ``recovery.check_gaps`` reads
    ``earliest_known`` once per market at the top of the cycle and never
    refreshes it mid-cycle, so a market granted more than one history slot in
    the same cycle (``backfill_priority.interleave``, T3.7d item 2) can have
    an *older* chunk compared against a minimum a *newer* chunk -- processed
    earlier the same cycle -- already proved wrong by *persisting* a candle
    reaching further back (BTCUSDT/UNIUSDT, 2026-09-08: legitimate August
    windows marked ``before_listing`` this way). Set **only** when such an
    earlier chunk actually moved the true minimum (recovering candles
    *after* ``earliest_known`` proves nothing about windows before it, e.g.
    this module's own MARSCOINUSDT test). T3.7f (re-review HIGH): that
    earlier chunk need not reach ``"recovered"`` itself -- a real trading
    pause can leave it ``open`` while it still *persisted* a candle older
    than ``earliest_known``, which is why this function returns the minimum
    ``open_time`` it actually inserted (below), not just the gap's status.
    When true, this call never concludes ``before_listing`` even on an empty
    fetch -- it falls through to the ordinary attempts/failed path instead,
    revisited next cycle once ``check_gaps`` re-reads ``earliest()``.

    Returns the minimum ``open_time`` this call actually inserted (``None``
    on every early-return path, or if it inserted nothing) -- see
    ``earliest_known_stale`` above and :func:`recover_one`'s docstring.
    """
    gap.attempts += 1
    min_open_time: datetime | None = None
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
        if (
            not closed
            and earliest_known is not None
            and gap.gap_end < earliest_known
            and not earliest_known_stale
        ):
            # T3.7e: the exchange's own empty answer for this exact window,
            # not ``earliest_known`` alone -- see the docstring above.
            gap.attempts -= 1  # a conclusive answer, not a failed attempt
            gap.status = "unrecoverable"
            message = (
                f"{symbol}: gap [{gap.gap_start.isoformat()}, {gap.gap_end.isoformat()}] ends "
                f"before the market's earliest known candle ({earliest_known.isoformat()})"
            )
            logger.info(
                "market_gap_unrecoverable",
                reason=BEFORE_LISTING_REASON,
                symbol=symbol,
                market_id=gap.market_id,
                gap_start=gap.gap_start,
                gap_end=gap.gap_end,
                earliest_known=earliest_known,
            )
            session.add(
                SystemEvent(
                    level=RiskEventSeverity.WARNING,
                    component="market-worker",
                    event="market_gap_unrecoverable",
                    message=message,
                    data={
                        "reason": BEFORE_LISTING_REASON,
                        "symbol": symbol,
                        "market_id": str(gap.market_id),
                        "gap_start": gap.gap_start.isoformat(),
                        "gap_end": gap.gap_end.isoformat(),
                        "earliest_known": earliest_known.isoformat(),
                    },
                )
            )
            return None
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
            # same transaction. T3.7f: always collected now (not only for
            # ``history``) so ``min_open_time`` below reflects what this call
            # actually persisted regardless of tier -- ``collected`` never
            # changes what gets announced, only what this list receives.
            newly_inserted: list[Any] = []
            inserted = await upsert_candles(
                session,
                closed,
                {symbol: gap.market_id},
                source="rest",
                announce=tier != "history",
                collected=newly_inserted,
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
        if newly_inserted:
            # T3.7f: the caller's staleness signal (see
            # ``earliest_known_stale`` above) -- computed from what this call
            # actually *persisted* (only reached once the nested transaction
            # above commits without raising), independent of whether the gap
            # as a whole reached ``"recovered"`` this time.
            min_open_time = min(c.open_time for c in newly_inserted)
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
            return None
        logger.exception("market_gap_backfill_failed", symbol=symbol, attempt=gap.attempts)
    # T3.7d: `attempts` is cumulative across every reopen (recovery_lifecycle
    # .reopen_stale_failed no longer resets it), so a life fails on its own
    # MAX_ATTEMPTS-th try -- exactly the multiples of MAX_ATTEMPTS (5, 10, 15,
    # ...) -- never merely "attempts has grown past 5 again", which would
    # fail a reopened gap after a single retry instead of giving it a full
    # new life.
    if gap.status != "recovered" and gap.attempts % MAX_ATTEMPTS == 0:
        gap.status = "failed"
        # D6/Astra: detected_at is the only durable clock the cooldown has.
        # Refresh it on every re-failure, not just the original detection --
        # otherwise a gap reopened once and then failing again would already
        # be past FAILED_RETRY_AFTER_S and get reopened on the very next
        # cycle, turning the cooldown into a tight retry loop.
        gap.detected_at = now
    return min_open_time


async def recover_one(
    session_factory: Any,
    adapter: Any,
    gap_id: Any,
    symbol: str,
    now: datetime,
    *,
    timeout_s: float = FETCH_TIMEOUT_S,
    tier: Tier = "live",
    earliest_known: datetime | None = None,
    earliest_known_stale: bool = False,
) -> tuple[bool, datetime | None]:
    """M3: fetch over REST with no transaction open, then re-check the gap
    ``FOR UPDATE`` and write in one short transaction. ``tier``,
    ``earliest_known`` and ``earliest_known_stale`` pass through to
    :func:`recover_registered` unchanged (see its docstring for what each
    decides).

    T3.7e: a gap suspected of being before the market's listing is fetched
    over REST exactly like any other now -- see :func:`recover_registered`
    for why the earlier zero-REST-weight short-circuit on ``earliest_known``
    alone was wrong. Only one fetch path below, not two.

    Returns ``(recovered, min_open_time)`` -- whether the gap's status became
    ``"recovered"``, and the minimum ``open_time`` this call actually
    persisted (``None`` if nothing) -- so ``recovery.check_gaps`` can mark
    that market's ``earliest_known`` stale for the rest of the cycle when
    this reaches further back than it (T3.7e item 1). T3.7f (re-review
    HIGH): ``recover_registered``'s return value, not ``gap.status ==
    "recovered"`` paired with ``gap.gap_start`` -- a partial recovery still
    persists candles and must still be able to mark staleness.
    """
    async with role_session(session_factory, db_role="hunter_worker") as session:
        gap = await session.scalar(
            select(IngestionGap).where(IngestionGap.id == gap_id, IngestionGap.status == "open")
        )
        if gap is None:
            return False, None
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
            return False, None
        min_open_time = await recover_registered(
            session,
            adapter,
            gap,
            symbol,
            now,
            candles=candles,
            fetch_error=fetch_error,
            timeout_s=timeout_s,
            tier=tier,
            earliest_known=earliest_known,
            earliest_known_stale=earliest_known_stale,
        )
        return gap.status == "recovered", min_open_time
