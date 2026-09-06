"""Set-based candle/gap reads for gap detection (HIGH-2).

Extracted out of ``recovery.py`` purely to stay under the 350-line budget —
one per-market query for the watermark, one for persisted candles and one
for existing gaps, each covering the whole monitored universe in a single
round trip instead of one query per market. The same budget is why the
``failed`` reopening and the two-tier pending selection live here rather than
in ``recovery.py``, next to the loop that calls them.
"""

from __future__ import annotations

import zlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.domain.enums import Timeframe
from hunter_core.logging import get_logger

logger = get_logger(__name__)

GAP_PLANNING_LOCK_NAMESPACE = 0x48554E54
"""``pg_advisory_xact_lock`` namespace ("HUNT") for gap creation.

Two writers now create ``ingestion_gaps`` rows for the same market: the
periodic detection and the ``market.backfill.requested`` consumer. Both read
the coverage (persisted candles, existing gaps) and then insert what is
missing, and the table has no uniqueness over the interval — so without
serialization the classic read/read/insert/insert race produces two rows for
the same minutes and two REST fetches for the same candles (Astra,
T2.5-backfill design review, must-fix 2).

The lock is **transaction-scoped** (released by commit or rollback, never
leaked by a crashed session), taken by exchange rather than by market so a
detection cycle that reads the whole universe in one query is covered by one
lock, and no REST call is ever made while holding it: both critical sections
are reads plus inserts against Postgres only.
"""


async def persisted(session: Any, market_id: Any, start: datetime, end: datetime) -> set[datetime]:
    """Persisted final open times for one gap's own coverage check."""
    return set(
        await session.scalars(
            select(Candle.open_time).where(
                Candle.market_id == market_id,
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
                Candle.open_time >= start,
                Candle.open_time <= end,
            )
        )
    )


async def watermarks(session: Any, market_ids: list[Any]) -> dict[Any, datetime | None]:
    """One query for the whole universe instead of one per market."""
    result: dict[Any, datetime | None] = dict.fromkeys(market_ids)
    if not market_ids:
        return result
    rows = (
        await session.execute(
            select(Candle.market_id, func.max(Candle.open_time))
            .where(
                Candle.market_id.in_(market_ids),
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
            )
            .group_by(Candle.market_id)
        )
    ).all()
    result.update({row[0]: row[1] for row in rows})
    return result


async def persisted_by_market(
    session: Any, market_ids: list[Any], start: datetime, end: datetime
) -> dict[Any, set[datetime]]:
    """Persisted open times of every monitored market in the widest window
    needed, one query, grouped in Python."""
    result: dict[Any, set[datetime]] = {mid: set() for mid in market_ids}
    if not market_ids:
        return result
    rows = (
        await session.execute(
            select(Candle.market_id, Candle.open_time).where(
                Candle.market_id.in_(market_ids),
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
                Candle.open_time >= start,
                Candle.open_time <= end,
            )
        )
    ).all()
    for market_id, open_time in rows:
        result[market_id].add(open_time)
    return result


async def gaps_by_market(
    session: Any, market_ids: list[Any], statuses: tuple[str, ...]
) -> dict[Any, list[IngestionGap]]:
    """Every open/failed gap of the monitored universe, one query."""
    result: dict[Any, list[IngestionGap]] = {mid: [] for mid in market_ids}
    if not market_ids:
        return result
    rows = (
        await session.scalars(
            select(IngestionGap).where(
                IngestionGap.market_id.in_(market_ids), IngestionGap.status.in_(statuses)
            )
        )
    ).all()
    for gap in rows:
        result[gap.market_id].append(gap)
    return result


async def count_by_status(session: Any, market_ids: list[Any], status: str) -> int:
    if not market_ids:
        return 0
    return (
        await session.scalar(
            select(func.count())
            .select_from(IngestionGap)
            .where(IngestionGap.market_id.in_(market_ids), IngestionGap.status == status)
        )
        or 0
    )


async def lock_gap_planning(session: Any, exchange: str) -> None:
    """Serialize gap creation for ``exchange`` inside this transaction.

    ``pg_advisory_xact_lock(ns, key)`` blocks rather than failing: the other
    writer's critical section is short and bounded (no REST inside it), so
    waiting is the correct behaviour — the alternative, ``try_lock`` and skip,
    would silently drop a backfill request whenever a detection cycle happened
    to be running.
    """
    key = zlib.crc32(exchange.encode("utf-8")) % 2_000_000_000
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :key)"),
        {"ns": GAP_PLANNING_LOCK_NAMESPACE % 2_000_000_000, "key": key},
    )


def reopen_stale_failed(
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


async def pending_gaps(
    session: Any,
    market_ids: list[Any],
    *,
    live_from: datetime,
    live_limit: int,
    history_limit: int,
) -> tuple[list[tuple[Any, Any]], list[tuple[Any, Any]]]:
    """The ``open`` gaps of this cycle, split into live collection and history.

    A gap whose ``gap_end`` reaches into the detection window is *live*: either
    the collector found it itself or a backfill request named minutes the
    collector would have found anyway. Everything older is *history* — by
    construction, since ``check_gaps`` never *creates* a gap that old.

    That construction is about **creation**, not **origin**: it does not mean a
    gap in this tier was necessarily born from ``market.backfill.requested``.
    A gap ``check_gaps`` or ``persist.report_losses`` created inside the live
    window can still *age* into ``history`` here without anyone ever asking
    for it — REST staying down, or the worker itself being stopped, for longer
    than ``BOOTSTRAP_WINDOW_MINUTES``\\ shifts ``live_from`` past a
    ``gap_end`` that was never touched. ``reopen_stale_failed`` reopens a
    stale ``failed`` gap without moving its bounds either, so a cooldown does
    not reset the clock (Astra, T2.9c review — notes-T2.5.md §25 correction,
    notes-T2.9.md). A caller that needs to say *why* a history-tier chunk was
    recovered has to say "the window aged past the live threshold", not
    "someone requested it".

    Both tiers are ordered by ``gap_end DESC``: the newest missing minute is the
    one whose absence hurts most (it is the one every rolling window is waiting
    for), and ordering by ``detected_at`` let fifty day-old bootstrap gaps
    precede a one-minute hole that had just been detected.

    History is served **only with what the live tier did not spend**, and never
    more than ``history_limit`` — the guarantee is "live collection does not
    queue behind a bootstrap", written as arithmetic rather than as a comment.
    """
    if not market_ids or live_limit <= 0:
        return [], []
    base = select(IngestionGap.id, IngestionGap.market_id).where(
        IngestionGap.market_id.in_(market_ids), IngestionGap.status == "open"
    )
    live = (
        await session.execute(
            base.where(IngestionGap.gap_end >= live_from)
            .order_by(IngestionGap.gap_end.desc(), IngestionGap.id)
            .limit(live_limit)
        )
    ).all()
    leftover = min(history_limit, live_limit - len(live))
    if leftover <= 0:
        return list(live), []
    history = (
        await session.execute(
            base.where(IngestionGap.gap_end < live_from)
            .order_by(IngestionGap.gap_end.desc(), IngestionGap.id)
            .limit(leftover)
        )
    ).all()
    return list(live), list(history)


async def gap_coverage(
    session: Any, market_id: Any, start: datetime, end: datetime
) -> set[datetime]:
    """Minutes of ``[start, end]`` already owned by an ``open``/``failed`` gap.

    The backfill planner subtracts these rather than merging over them: an
    ``open`` gap is already someone's promise to fetch those minutes, and a
    ``failed`` one is serving the cooldown of ``FAILED_RETRY_AFTER_S`` — writing
    a fresh ``open`` row over it would walk around that cooldown.

    Clipped to the window on the way out, so the set is bounded by the request's
    own ceiling (seven days) no matter how long the intersecting gap is.
    """
    minute = timedelta(minutes=1)
    rows = (
        await session.execute(
            select(IngestionGap.gap_start, IngestionGap.gap_end).where(
                IngestionGap.market_id == market_id,
                IngestionGap.timeframe == Timeframe.M1,
                IngestionGap.status.in_(("open", "failed")),
                IngestionGap.gap_end >= start,
                IngestionGap.gap_start <= end,
            )
        )
    ).all()
    covered: set[datetime] = set()
    for gap_start, gap_end in rows:
        first, last = max(gap_start, start), min(gap_end, end)
        covered |= {first + minute * n for n in range(int((last - first) / minute) + 1)}
    return covered


async def try_lock_gap_planning(session: Any, exchange: str) -> bool:
    """:func:`lock_gap_planning`, but never waits. ``False`` = someone else has it.

    The drain loop calls ``report_losses`` on **every** iteration (about once a
    second), and it must not queue behind a detection cycle that is reading the
    coverage of 200 markets: measured on the local stack, blocking there showed
    up as ``market_persist_lag`` of 14s and a flush timing out. Losing the lock
    is harmless for that caller — the losses stay queued and the next iteration
    reports them.
    """
    key = zlib.crc32(exchange.encode("utf-8")) % 2_000_000_000
    return bool(
        await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:ns, :key)"),
            {"ns": GAP_PLANNING_LOCK_NAMESPACE % 2_000_000_000, "key": key},
        )
    )
