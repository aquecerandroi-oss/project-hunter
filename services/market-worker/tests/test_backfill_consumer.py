"""The consumer of ``market.backfill.requested`` — T2.5-backfill.

The scanner publishes windows it cannot fill itself (the joint M2 decision gives
REST to the market-worker alone) and, until this task, nobody read them: 29
messages on the stream and ``XINFO GROUPS`` empty (``.claude/state/t25-proof.md``
§T2.5b/4). These tests cover the whole path — request, gap rows, REST through the
existing recovery, candles in Postgres and one ``market.candles.closed`` per
backfilled minute in the outbox — plus every way a request is *not* served.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.events.consume import is_processed
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME, publish
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.settings import Settings
from hunter_market_worker import backfill, recovery
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.universe import MonitoredUniverse

from . import builders
from .db_helpers import ensure_candle_partition, seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

MINUTE = timedelta(minutes=1)
STREAM = Streams.MARKET_BACKFILL_REQUESTED


def request_payload(
    *, market_id: Any, exchange: str, symbol: str, gap_start: Any, gap_end: Any
) -> dict[str, Any]:
    """Exactly what ``hunter_scanner_worker.backfill.BackfillRequester`` sends.

    Written out rather than imported so this suite does not depend on another
    service's package; the contract itself is pinned against the real producer
    in ``test_the_producers_own_payload_is_understood``.
    """
    return {
        "market_id": str(market_id),
        "exchange": exchange,
        "symbol": symbol,
        "timeframe": "1m",
        "gap_start": gap_start.isoformat(),
        "gap_end": gap_end.isoformat(),
        "reason": "baseline_bootstrap",
        "requested_by": "scanner-worker@test",
    }


async def publish_request(redis: Any, payload: dict[str, Any], *, event_id: Any = None) -> None:
    envelope = EventEnvelope(
        type=STREAM,
        producer="scanner-worker@test",
        key=f"{payload['exchange']}:{payload['symbol']}",
        payload=payload,
        **({"event_id": event_id} if event_id is not None else {}),
    )
    await publish(redis, STREAM, envelope, DEFAULT_MAXLEN[STREAM])


def build_consumer(
    session_factory: Any,
    redis: Any,
    adapter: Any,
    symbols: list[str],
    *,
    shard: str = "0/1",
) -> backfill.BackfillConsumer:
    universe = MonitoredUniverse()
    universe.set(symbols)
    return backfill.BackfillConsumer(
        session_factory,
        adapter,
        redis,
        universe,
        Settings(market_shard=shard),
        instance="test",
        claim_idle_ms=0,
    )


async def gaps_of(session_factory: Any, market_id: Any) -> list[IngestionGap]:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(IngestionGap)
            .where(IngestionGap.market_id == market_id)
            .order_by(IngestionGap.gap_start)
        )
        return list(rows)


async def test_a_request_becomes_gaps_the_recovery_fills_and_the_outbox_announces(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 120 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    await ensure_candle_partition(db_session_factory, window_end)
    adapter = FakeAdapter(code=exchange_code)
    adapter.candles_response["BTCUSDT"] = [
        builders.candle("BTCUSDT", open_time=window_start + MINUTE * n, exchange=exchange_code)
        for n in range(120)
    ]
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="BTCUSDT",
            gap_start=window_start,
            gap_end=window_end,
        ),
    )

    consumer = build_consumer(db_session_factory, redis_client, adapter, ["BTCUSDT"])
    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["accepted"]
    gaps = await gaps_of(db_session_factory, market_id)
    assert [(gap.gap_start, gap.gap_end) for gap in gaps] == [(window_start, window_end - MINUTE)]
    # The window is half-open and the row is inclusive: the last minute asked
    # for is 10:59 when the request said "[.., 11:00)".
    assert gaps[0].status == "open"

    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], HeartbeatState())

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        candles = await session.scalar(
            select(func.count())
            .select_from(Candle)
            .where(
                Candle.market_id == market_id,
                Candle.open_time >= window_start,
                Candle.open_time < window_end,
                Candle.source == "rest",
            )
        )
        announced = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.stream == Streams.MARKET_CANDLES_CLOSED)
        )
    assert candles == 120
    # Every backfilled minute is announced exactly like a live one — the same
    # ``upsert_candles`` path enqueues it in the same transaction (durable.py).
    assert announced == 120
    assert (await gaps_of(db_session_factory, market_id))[0].status == "recovered"


async def test_asking_again_for_a_filled_window_costs_no_rest_call(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ETHUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 60 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    adapter = FakeAdapter(code=exchange_code)
    adapter.candles_response["ETHUSDT"] = [
        builders.candle("ETHUSDT", open_time=window_start + MINUTE * n, exchange=exchange_code)
        for n in range(60)
    ]
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="ETHUSDT",
        gap_start=window_start,
        gap_end=window_end,
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["ETHUSDT"])

    await publish_request(redis_client, payload)
    await consumer.run_once()
    await recovery.check_gaps(db_session_factory, adapter, ["ETHUSDT"], HeartbeatState())
    calls_before = len(adapter.fetch_candles_calls)

    # A different event_id on purpose: the processed-set guard would hide the
    # duplicate, and what is being tested is the *gap-level* idempotency — a
    # window already persisted plans nothing at all.
    await publish_request(redis_client, payload, event_id=uuid4())
    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["empty"]
    # Only the gaps *of the requested window*: ``check_gaps`` legitimately owns
    # a live one for the detection window, where this market has no candles.
    in_window = [
        gap
        for gap in await gaps_of(db_session_factory, market_id)
        if gap.gap_start >= window_start and gap.gap_end < window_end
    ]
    assert len(in_window) == 1
    await recovery.check_gaps(db_session_factory, adapter, ["ETHUSDT"], HeartbeatState())
    assert not [
        call for call in adapter.fetch_candles_calls[calls_before:] if call[2] == window_start
    ]


async def test_a_market_of_another_shard_is_ignored_without_effect(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Every shard has its own group, so every shard sees every request.

    Only the owner plans it; the others acknowledge and write nothing. The
    acknowledgement carries **no** processed mark, so a topology change
    (``MARKET_SHARD`` from 0/2 to 0/3) leaves the new owner free to serve a
    republication of the same ``event_id``.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    adapter = FakeAdapter(code=exchange_code)
    event_id = uuid4()
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="BTCUSDT",
            gap_start=window_end - 60 * MINUTE,
            gap_end=window_end,
        ),
        event_id=event_id,
    )
    # crc32("BTCUSDT") % 2 == 1, so shard 0 of 2 is not the owner.
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["ETHUSDT"], shard="0/2")

    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["ignored"]
    assert await gaps_of(db_session_factory, market_id) == []
    assert not await is_processed(redis_client, consumer.group, str(event_id))


async def test_a_market_outside_the_universe_is_refused_and_served_when_it_returns(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Astra, T2.5-backfill design review, must-fix 1.

    A refusal that depends on *current* state must not be recorded in the
    processed set, or the hourly republication (``REQUEST_TTL_S``) would be
    dropped by the guard before this consumer ever looked at the universe
    again — the market would come back and never be backfilled.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "SOLUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 60 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    adapter = FakeAdapter(code=exchange_code)
    event_id = uuid4()
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="SOLUSDT",
        gap_start=window_start,
        gap_end=window_end,
    )
    await publish_request(redis_client, payload, event_id=event_id)

    refusing = build_consumer(db_session_factory, redis_client, adapter, ["BTCUSDT"])
    outcomes = await refusing.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "market_not_monitored")]
    assert not await is_processed(redis_client, refusing.group, str(event_id))

    await publish_request(redis_client, payload, event_id=event_id)
    serving = build_consumer(db_session_factory, redis_client, adapter, ["SOLUSDT"])
    outcomes = await serving.run_once()

    assert [outcome.name for outcome in outcomes] == ["accepted"]
    assert len(await gaps_of(db_session_factory, market_id)) == 1
    assert await is_processed(redis_client, serving.group, str(event_id))


async def test_a_window_in_the_future_is_refused(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ADAUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    adapter = FakeAdapter(code=exchange_code)
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="ADAUSDT",
            gap_start=now + 10 * MINUTE,
            gap_end=now + 70 * MINUTE,
        ),
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["ADAUSDT"])

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "future_window")]
    assert await gaps_of(db_session_factory, market_id) == []


async def test_a_request_beyond_the_ceiling_is_truncated_to_seven_days(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "AVAXUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 30 * 24 * 60 * MINUTE
    for month_probe in (window_start, window_start + 15 * 24 * 60 * MINUTE, window_end):
        await ensure_candle_partition(db_session_factory, month_probe)
    adapter = FakeAdapter(code=exchange_code)
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="AVAXUSDT",
            gap_start=window_start,
            gap_end=window_end,
        ),
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["AVAXUSDT"])

    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["truncated"]
    gaps = await gaps_of(db_session_factory, market_id)
    assert gaps[0].gap_start == window_end - 7 * 24 * 60 * MINUTE
    assert gaps[-1].gap_end == window_end - MINUTE
    minutes = sum(int((gap.gap_end - gap.gap_start) / MINUTE) + 1 for gap in gaps)
    assert minutes == 7 * 24 * 60


async def test_a_malformed_message_is_quarantined_and_the_next_one_is_served(
    db_session_factory: Any, redis_client: Any
) -> None:
    """A poison message must not take the collector down with it.

    ``hunter_core.events.consume`` deserializes the envelope *before* yielding,
    so an unreadable one raises inside the generator, kills the task and — with
    the ``TaskGroup`` of ``main.py`` — the whole worker, which then meets the
    same message again after the restart (Astra, must-fix 5). This consumer
    reads defensively and acknowledges what it cannot parse.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "DOTUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 60 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    adapter = FakeAdapter(code=exchange_code)

    await redis_client.xadd(STREAM, {FIELD_NAME: b"{not json at all"})
    await redis_client.xadd(STREAM, {b"wrong_field": b"{}"})
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="DOTUSDT",
            gap_start=window_start,
            gap_end=window_end,
        ),
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["DOTUSDT"])

    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["malformed", "malformed", "accepted"]
    assert len(await gaps_of(db_session_factory, market_id)) == 1
    pending = await redis_client.xpending(STREAM, consumer.group)
    assert pending["pending"] == 0


async def test_a_payload_that_is_not_a_backfill_request_is_refused(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = FakeAdapter(code=exchange_code)
    await publish_request(
        redis_client, {"exchange": exchange_code, "symbol": "BTCUSDT", "gap_start": "yesterday"}
    )
    consumer = build_consumer(db_session_factory, redis_client, adapter, ["BTCUSDT"])

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "unreadable_payload")]


async def test_a_timeframe_this_collector_does_not_store_is_refused(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="BTCUSDT",
        gap_start=now - 300 * MINUTE,
        gap_end=now - 240 * MINUTE,
    )
    payload["timeframe"] = "5m"
    await publish_request(redis_client, payload)
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["BTCUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "unsupported_timeframe")]


async def test_a_market_this_database_does_not_know_is_refused(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    now = align_open_time(utcnow(), Timeframe.M1)
    await publish_request(
        redis_client,
        request_payload(
            market_id=uuid4(),
            exchange=exchange_code,
            symbol="GHOSTUSDT",
            gap_start=now - 300 * MINUTE,
            gap_end=now - 240 * MINUTE,
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["GHOSTUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "unknown_market")]


async def test_a_request_naming_another_exchange_is_ignored(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    now = align_open_time(utcnow(), Timeframe.M1)
    await publish_request(
        redis_client,
        request_payload(
            market_id=uuid4(),
            exchange="bybit",
            symbol="BTCUSDT",
            gap_start=now - 300 * MINUTE,
            gap_end=now - 240 * MINUTE,
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["BTCUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("ignored", "other_exchange")]


async def test_minutes_with_no_partition_are_not_planned(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Astra's nice-to-have, promoted after the first test run failed on it.

    ``create_partitions.py`` provisions the current month and the ones ahead, so
    a seven-day request early in a month names minutes no partition accepts. The
    insert would abort the whole transaction — candles, outbox rows and the
    gap's status together — and the gap would spend its five attempts on a
    condition no retry can fix.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "LINKUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    # Two years back: a month that certainly has no partition in any database.
    window_end = now - 730 * 24 * 60 * MINUTE
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="LINKUSDT",
            gap_start=window_end - 120 * MINUTE,
            gap_end=window_end,
        ),
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["LINKUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [(o.name, o.reason) for o in outcomes] == [("refused", "no_partition")]
    assert await gaps_of(db_session_factory, market_id) == []


async def test_a_redelivered_request_does_not_write_the_same_gaps_twice(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Crash between the commit and the ACK: the message comes back."""
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "NEARUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 300 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="NEARUSDT",
        gap_start=window_start,
        gap_end=window_end,
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["NEARUSDT"]
    )
    await publish_request(redis_client, payload)
    await consumer.run_once()
    first = await gaps_of(db_session_factory, market_id)

    await publish_request(redis_client, payload, event_id=uuid4())
    outcomes = await consumer.run_once()

    # ``partial``, not ``empty``: no new rows, but the minutes are owned by the
    # rows the first pass wrote, so the mark is withheld and the word says so.
    assert [outcome.name for outcome in outcomes] == ["partial"]
    assert outcomes[0].chunks == 0
    assert [(g.gap_start, g.gap_end) for g in await gaps_of(db_session_factory, market_id)] == [
        (g.gap_start, g.gap_end) for g in first
    ]


async def test_two_planners_racing_write_one_set_of_gaps(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The advisory lock, from the outside: read/read/insert/insert is a race.

    Without ``recovery_queries.lock_gap_planning`` both transactions see "these
    minutes are missing and no gap owns them" and both insert — two rows, two
    REST fetches for the same candles.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ATOMUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 120 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="ATOMUSDT",
        gap_start=window_start,
        gap_end=window_end,
    )
    one = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["ATOMUSDT"]
    )
    two = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["ATOMUSDT"]
    )

    await asyncio.gather(
        one.plan(payload, now=now),
        two.plan(payload, now=now),
    )

    assert len(await gaps_of(db_session_factory, market_id)) == 1


async def test_the_group_drains_the_backlog_and_reports_no_lag(
    db_session_factory: Any, redis_client: Any
) -> None:
    """What the operational proof reads: ``XINFO GROUPS`` with lag zero."""
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "OPUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    await ensure_candle_partition(db_session_factory, window_end - 600 * MINUTE)
    for n in range(3):
        await publish_request(
            redis_client,
            request_payload(
                market_id=market_id,
                exchange=exchange_code,
                symbol="OPUSDT",
                gap_start=window_end - (600 - 120 * n) * MINUTE,
                gap_end=window_end - (480 - 120 * n) * MINUTE,
            ),
        )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["OPUSDT"]
    )

    await consumer.run_once()

    groups = await redis_client.xinfo_groups(STREAM)
    mine = [g for g in groups if g["name"].decode() == consumer.group]
    assert len(mine) == 1
    assert mine[0]["pending"] == 0
    assert mine[0]["lag"] == 0
    assert len(await gaps_of(db_session_factory, market_id)) == 3


async def test_the_producers_own_payload_is_understood(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Contract test against the real producer, skipped if it is not installed."""
    scanner = pytest.importorskip("hunter_scanner_worker.backfill")
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "MATICUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_end = now - 3 * 24 * 60 * MINUTE
    window_start = window_end - 120 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)

    requester = scanner.BackfillRequester("scanner-worker@contract")
    asked = await requester.request(
        redis_client,
        market_id=market_id,
        exchange=exchange_code,
        symbol="MATICUSDT",
        gap_start=window_start,
        gap_end=window_end,
        reason="baseline_bootstrap",
    )
    assert asked

    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["MATICUSDT"]
    )
    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["accepted"]
    gaps = await gaps_of(db_session_factory, market_id)
    assert (gaps[0].gap_start, gaps[-1].gap_end) == (window_start, window_end - MINUTE)


async def test_a_window_whose_end_has_not_closed_yet_is_not_marked_processed(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Astra, T2.5-backfill diff review, must-fix 1.

    The request reaches into minutes that are not settled. What is settled gets
    planned; the tail is reported and the ``event_id`` is **not** marked, so the
    republication after those minutes close plans them too instead of being
    dropped by the processed guard.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "APTUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    event_id = uuid4()
    await publish_request(
        redis_client,
        request_payload(
            market_id=market_id,
            exchange=exchange_code,
            symbol="APTUSDT",
            gap_start=now - 60 * MINUTE,
            gap_end=now + 30 * MINUTE,
        ),
        event_id=event_id,
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["APTUSDT"]
    )

    outcomes = await consumer.run_once()

    assert [outcome.name for outcome in outcomes] == ["partial"]
    assert outcomes[0].deferred >= 30
    assert not await is_processed(redis_client, consumer.group, str(event_id))
    gaps = await gaps_of(db_session_factory, market_id)
    # Nothing beyond the settled end was ever written.
    assert max(gap.gap_end for gap in gaps) <= now - recovery.DETECTION_GRACE


async def test_a_dropped_candle_and_a_request_do_not_open_two_gaps_for_one_minute(
    db_session_factory: Any, redis_client: Any
) -> None:
    """Astra, T2.5-backfill diff review, must-fix 3: the third writer.

    ``persist.report_losses`` opens a gap for a final candle the queue dropped,
    through the same read-then-insert protocol. Without the shared advisory
    lock it and the consumer both read "missing, no gap" and both insert.
    """
    from hunter_market_worker.persist import report_losses
    from hunter_market_worker.queues import PersistQueues

    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "INJUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    minute = now - 400 * MINUTE
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="INJUSDT",
        gap_start=minute,
        gap_end=minute + MINUTE,
    )
    queues = PersistQueues()
    queues.drop(builders.candle("INJUSDT", open_time=minute, exchange=exchange_code), "age")
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["INJUSDT"]
    )

    await asyncio.gather(
        report_losses(db_session_factory, exchange_code, queues),
        consumer.plan(payload, now=now),
    )

    covering = [
        gap
        for gap in await gaps_of(db_session_factory, market_id)
        if gap.gap_start <= minute <= gap.gap_end
    ]
    assert len(covering) == 1


async def test_the_loss_report_gives_up_the_lock_instead_of_delaying_the_flush(
    db_session_factory: Any, redis_client: Any
) -> None:
    """``report_losses`` runs once per drain iteration; it must never queue.

    Blocking it behind a detection cycle showed up on the local stack as
    ``market_persist_lag lag_s=14`` and a flush timing out — the loss report is
    best-effort, the flush is not. With the lock held elsewhere it writes
    nothing, keeps the loss queued and lets the next iteration try again.
    """
    from sqlalchemy import text

    from hunter_market_worker.persist import report_losses
    from hunter_market_worker.queues import PersistQueues
    from hunter_market_worker.recovery_queries import (
        GAP_PLANNING_LOCK_NAMESPACE,
        lock_gap_planning,
    )

    del redis_client
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "TIAUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    queues = PersistQueues()
    queues.drop(
        builders.candle("TIAUSDT", open_time=now - 5 * MINUTE, exchange=exchange_code), "age"
    )
    assert GAP_PLANNING_LOCK_NAMESPACE  # the namespace both writers share

    async with role_session(db_session_factory, db_role="hunter_worker") as holder:
        await lock_gap_planning(holder, exchange_code)
        await holder.execute(text("SELECT 1"))
        await report_losses(db_session_factory, exchange_code, queues)

        assert len(queues.losses) == 1  # nothing reported, nothing drained

    await report_losses(db_session_factory, exchange_code, queues)

    assert not queues.losses
    assert len(await gaps_of(db_session_factory, market_id)) == 1


async def test_the_same_request_plans_the_tail_once_the_clock_has_moved_on(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The other half of must-fix 1: the withheld mark has to buy something.

    First pass plans what is settled and reports the tail. The **same** window,
    evaluated once those minutes have closed, plans *them* — no new identity
    from the producer, no minute lost.

    It stays ``partial``, and that is the conservative ``Plan.complete`` at
    work: the rows the first pass wrote are still ``open``, so this pass did not
    account for the window *by itself*. It becomes final when those gaps
    recover and the minutes are persisted — the self-healing path.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "SUIUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    window_start = now - 300 * MINUTE
    window_end = now - 100 * MINUTE
    await ensure_candle_partition(db_session_factory, window_start)
    payload = request_payload(
        market_id=market_id,
        exchange=exchange_code,
        symbol="SUIUSDT",
        gap_start=window_start,
        gap_end=window_end,
    )
    consumer = build_consumer(
        db_session_factory, redis_client, FakeAdapter(code=exchange_code), ["SUIUSDT"]
    )

    # "Now" is 150 minutes before the window ends: half of it is not settled.
    early = await consumer.plan(payload, now=window_end - 150 * MINUTE)
    planned_early = [gap.gap_end for gap in await gaps_of(db_session_factory, market_id)]

    late = await consumer.plan(payload, now=now)

    assert (early.name, early.final) == ("partial", False)
    assert early.deferred >= 148
    assert late.chunks >= 1  # the tail the first pass could not settle
    assert (late.name, late.final) == ("partial", False)
    gaps = await gaps_of(db_session_factory, market_id)
    assert max(gap.gap_end for gap in gaps) == window_end - MINUTE
    assert max(planned_early) < window_end - MINUTE
