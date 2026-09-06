"""T2.9c: history-tier recovery announces one aggregate event per chunk
instead of one ``market.candles.closed`` per backfilled minute.

Design: ``.claude/state/astra-review-T2.9c-backfill-lane.md``. The live tier
(WS ingest and REST recovery of recent gaps alike) is untouched -- every
assertion here is about the *history* tier only, the one
``recovery_queries.pending_gaps`` already separates by the age of the gap's
window (PIPELINE.md §1b item 7).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.events.outbox import dispatch_pending
from hunter_core.events.streams import Streams
from hunter_market_worker import durable, persist, recovery, recovery_drain
from hunter_market_worker.heartbeat import HeartbeatState

from . import builders
from .db_helpers import ensure_candle_partition, seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

MINUTE = timedelta(minutes=1)
CHUNK_MINUTES = 240


async def add_gap(session_factory: Any, market_id: Any, start: Any, end: Any) -> Any:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=start,
            gap_end=end,
            status="open",
            attempts=0,
        )
        session.add(gap)
        await session.flush()
        return gap.id


async def _clear_outbox(factory: Any) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(delete(OutboxEvent))


async def _counts(factory: Any) -> tuple[int, int]:
    async with role_session(factory, db_role="hunter_worker") as session:
        backfilled = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.stream == Streams.MARKET_CANDLES_BACKFILLED)
        )
        closed = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.stream == Streams.MARKET_CANDLES_CLOSED)
        )
        return backfilled or 0, closed or 0


async def _months_between(session_factory: Any, start: Any, end: Any) -> None:
    """``ensure_candle_partition`` for every calendar month ``[start, end]`` touches."""
    cursor = start.replace(day=1)
    while True:
        await ensure_candle_partition(session_factory, cursor)
        if (cursor.year, cursor.month) == (end.year, end.month):
            return
        year = cursor.year + (cursor.month // 12)
        month = cursor.month % 12 + 1
        cursor = cursor.replace(year=year, month=month)


async def test_a_history_tier_gap_is_announced_as_one_aggregate_event(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    now = align_open_time(utcnow(), Timeframe.M1)
    old_start = now - 6 * 24 * 60 * MINUTE
    await ensure_candle_partition(db_session_factory, old_start)
    gap_id = await add_gap(db_session_factory, market_id, old_start, old_start + 2 * MINUTE)
    adapter = FakeAdapter(code=code)
    adapter.candles_response["BTCUSDT"] = [
        builders.candle("BTCUSDT", open_time=old_start + MINUTE * n, exchange=code)
        for n in range(3)
    ]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = await session.get(IngestionGap, gap_id)
        assert gap is not None
        await recovery_drain.recover_registered(
            session, adapter, gap, "BTCUSDT", now, tier="history"
        )

    backfilled, closed = await _counts(db_session_factory)
    assert backfilled == 1, "one aggregate event for the whole chunk"
    assert closed == 0, "history tier must not also announce per minute"
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.execute(
                select(OutboxEvent.payload).where(
                    OutboxEvent.stream == Streams.MARKET_CANDLES_BACKFILLED
                )
            )
        ).all()
    payload = rows[0][0]["payload"]
    assert payload["count"] == 3
    assert payload["reason"] == "historical_recovery"
    assert payload["source"] == "rest"
    assert payload["start"] == old_start.isoformat()
    assert payload["end"] == (old_start + 3 * MINUTE).isoformat()


async def test_the_default_tier_still_announces_every_minute_individually(
    db_session_factory: Any,
) -> None:
    """Regression: omitting ``tier`` (the live-tier default) must not change
    behaviour for any existing caller."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    now = align_open_time(utcnow(), Timeframe.M1)
    opened = now - MINUTE
    gap_id = await add_gap(db_session_factory, market_id, opened, opened)
    adapter = FakeAdapter(code=code)
    adapter.candles_response["BTCUSDT"] = [builders.candle("BTCUSDT", opened, exchange=code)]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = await session.get(IngestionGap, gap_id)
        assert gap is not None
        await recovery_drain.recover_registered(session, adapter, gap, "BTCUSDT", now)

    backfilled, closed = await _counts(db_session_factory)
    assert backfilled == 0
    assert closed == 1


async def test_check_gaps_tags_a_history_tier_gap_for_aggregation(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "DOTUSDT")
    await _clear_outbox(db_session_factory)
    now = align_open_time(utcnow(), Timeframe.M1)
    old_start = now - 6 * 24 * 60 * MINUTE
    await ensure_candle_partition(db_session_factory, old_start)
    await add_gap(db_session_factory, market_id, old_start, old_start + 2 * MINUTE)
    adapter = FakeAdapter(code=code)
    adapter.candles_response["DOTUSDT"] = [
        builders.candle("DOTUSDT", open_time=old_start + MINUTE * n, exchange=code)
        for n in range(3)
    ]

    await recovery.check_gaps(db_session_factory, adapter, ["DOTUSDT"], HeartbeatState())

    backfilled, closed = await _counts(db_session_factory)
    assert backfilled == 1
    assert closed == 0


async def test_check_gaps_still_announces_a_live_tier_gap_per_minute(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "ADAUSDT")
    await _clear_outbox(db_session_factory)
    now = align_open_time(utcnow(), Timeframe.M1)
    opened = now - 5 * MINUTE
    await add_gap(db_session_factory, market_id, opened, opened)
    adapter = FakeAdapter(code=code)
    adapter.candles_response["ADAUSDT"] = [builders.candle("ADAUSDT", opened, exchange=code)]

    await recovery.check_gaps(db_session_factory, adapter, ["ADAUSDT"], HeartbeatState())

    backfilled, closed = await _counts(db_session_factory)
    assert backfilled == 0
    assert closed == 1


async def test_seven_days_of_history_costs_at_most_forty_two_announcements(
    db_session_factory: Any,
) -> None:
    """Vazão (T2.9c): 7 days x 1 market in 240-minute chunks used to be up to
    10,080 individual ``market.candles.closed`` rows (notes-T2.5.md §28); the
    aggregate event turns that into one per chunk."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    now = align_open_time(utcnow(), Timeframe.M1)
    total_minutes = 7 * 24 * 60
    n_chunks = total_minutes // CHUNK_MINUTES
    assert n_chunks == 42
    window_end = now - (recovery.BOOTSTRAP_WINDOW_MINUTES + 10) * MINUTE
    window_start = window_end - total_minutes * MINUTE
    await _months_between(db_session_factory, window_start, window_end)

    adapter = FakeAdapter(code=code)
    for i in range(n_chunks):
        chunk_start = window_start + i * CHUNK_MINUTES * MINUTE
        chunk_end = chunk_start + (CHUNK_MINUTES - 1) * MINUTE
        gap_id = await add_gap(db_session_factory, market_id, chunk_start, chunk_end)
        adapter.candles_response["BTCUSDT"] = [
            builders.candle("BTCUSDT", open_time=chunk_start + MINUTE * n, exchange=code)
            for n in range(CHUNK_MINUTES)
        ]
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            gap = await session.get(IngestionGap, gap_id)
            assert gap is not None
            await recovery_drain.recover_registered(
                session, adapter, gap, "BTCUSDT", now, tier="history"
            )

    backfilled, closed = await _counts(db_session_factory)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        recovered = await session.scalar(
            select(func.count())
            .select_from(IngestionGap)
            .where(IngestionGap.market_id == market_id, IngestionGap.status == "recovered")
        )
    assert recovered == n_chunks
    assert backfilled == n_chunks
    assert backfilled <= 42, "vs. 10,080 before T2.9c"
    assert closed == 0


async def test_live_candles_are_not_queued_behind_a_cycles_worth_of_history(
    db_session_factory: Any, redis_client: Any
) -> None:
    """One cycle's history budget (``MAX_HISTORY_GAPS_PER_CYCLE`` chunks, now
    one aggregate row each) fits comfortably inside one dispatch sweep, so a
    live candle enqueued right after it goes out in the very same sweep --
    never behind an unbounded per-minute backlog the way up to 1,440 rows
    could before T2.9c."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - (recovery.BOOTSTRAP_WINDOW_MINUTES + 10) * MINUTE
    await ensure_candle_partition(db_session_factory, window_end)

    adapter = FakeAdapter(code=code)
    for i in range(recovery.MAX_HISTORY_GAPS_PER_CYCLE):
        chunk_start = window_end - (i + 1) * CHUNK_MINUTES * MINUTE
        chunk_end = chunk_start + (CHUNK_MINUTES - 1) * MINUTE
        gap_id = await add_gap(db_session_factory, market_id, chunk_start, chunk_end)
        adapter.candles_response["BTCUSDT"] = [
            builders.candle("BTCUSDT", open_time=chunk_start + MINUTE * n, exchange=code)
            for n in range(CHUNK_MINUTES)
        ]
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            gap = await session.get(IngestionGap, gap_id)
            assert gap is not None
            await recovery_drain.recover_registered(
                session, adapter, gap, "BTCUSDT", now, tier="history"
            )

    live_candle = builders.candle("BTCUSDT", exchange=code)
    await persist.flush_batch(db_session_factory, code, [live_candle])

    published = await dispatch_pending(redis_client, db_session_factory)

    assert published == recovery.MAX_HISTORY_GAPS_PER_CYCLE + 1, (
        "the whole cycle's history plus the live candle went out in one sweep"
    )
    entries = list(await redis_client.xrange(Streams.MARKET_CANDLES_CLOSED))
    assert len(entries) == 1
    assert str(durable.candle_event_id(live_candle)).encode() in entries[0][1][b"data"]
