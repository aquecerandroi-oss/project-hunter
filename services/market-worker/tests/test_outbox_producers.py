"""The market-worker's durable producers publish through the outbox (T2.9).

Durable means: someone persists an effect from the event, so it may not be lost
when Redis is unavailable. Those events are queued **in the transaction that
persists the row** and reach the stream from the dispatcher. Ephemeral events
(``market.ticks``, ``rt:*``, the WS funding *estimate*) keep publishing
directly — losing one only costs a refresh.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import to_wire
from hunter_core.events.outbox import dispatch_pending
from hunter_core.events.streams import Streams
from hunter_market_worker import backfill_announce, durable, persist, persist_rows
from hunter_market_worker.publication import liquidation_id
from hunter_market_worker.queues import OpenInterestSample, PersistItem, RealizedFunding

from . import builders
from .db_helpers import seed_market
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def _outbox(factory: Any) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await session.execute(
            select(OutboxEvent.event_id, OutboxEvent.stream, OutboxEvent.payload).order_by(
                OutboxEvent.created_at, OutboxEvent.id
            )
        )
        return list(rows.all())


async def _clear_outbox(factory: Any) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(delete(OutboxEvent))


# --- closed candles ---------------------------------------------------------


async def test_a_persisted_candle_queues_exactly_one_event_in_the_same_transaction(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code)

    await persist.flush_batch(db_session_factory, code, [candle])

    rows = await _outbox(db_session_factory)
    assert len(rows) == 1
    assert rows[0].stream == Streams.MARKET_CANDLES_CLOSED
    assert rows[0].event_id == durable.candle_event_id(candle)
    assert rows[0].payload["payload"] == to_wire(candle)
    assert rows[0].payload["key"] == f"{code}:BTCUSDT"

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Candle).where(Candle.market_id == market_id)
            )
            == 1
        )


async def test_a_redelivered_candle_queues_nothing_new(db_session_factory: Any) -> None:
    """``ON CONFLICT DO NOTHING`` on the candle means no second event: the
    first delivery already published it."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code)

    await persist.flush_batch(db_session_factory, code, [candle])
    await persist.flush_batch(db_session_factory, code, [candle])

    assert len(await _outbox(db_session_factory)) == 1


async def test_an_unfinished_candle_queues_nothing(db_session_factory: Any) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code, is_final=False)

    await persist.flush_batch(db_session_factory, code, [candle])

    assert await _outbox(db_session_factory) == []


async def test_a_rollback_leaves_neither_the_candle_nor_the_event(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Injected failure before the commit: nothing persisted, nothing queued."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code)

    async def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("crash before commit")

    monkeypatch.setattr(persist_rows, "upsert_snapshots", boom)
    with pytest.raises(RuntimeError, match="crash before commit"):
        await persist.flush_batch(db_session_factory, code, [candle])

    assert await _outbox(db_session_factory) == []
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Candle).where(Candle.market_id == market_id)
            )
            == 0
        )


async def test_a_rest_backfilled_candle_is_published_too(db_session_factory: Any) -> None:
    """The recovery path writes candles nobody saw over the WS. If only
    ``flush_batch`` queued events, a backfilled minute would be persisted and
    never announced (Astra, T2.9 round 1)."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        inserted = await persist.upsert_candles(
            session, [candle], {"BTCUSDT": market_id}, source="rest"
        )

    assert inserted == 1
    rows = await _outbox(db_session_factory)
    assert [row.event_id for row in rows] == [durable.candle_event_id(candle)]
    # The backfill carries the service-level ``producer``, not the
    # instance-scoped ``market-worker@{instance}`` the WS flush passes:
    # ``recovery.py`` has no runtime in scope. Pinned rather than left to
    # chance, because ``producer`` is the field an operator reads to tell
    # which shard emitted an event, and identity (``event_id``) does not
    # depend on it. Plumbing it through is a follow-up in notes-T2.9.md.
    assert rows[0].payload["producer"] == durable.PRODUCER


async def test_upsert_candles_can_skip_the_per_minute_announcement_and_collect_instead(
    db_session_factory: Any,
) -> None:
    """T2.9c: the history-tier recovery path opts out of ``enqueue_candles``
    and gets the inserted rows back instead, so its caller can build one
    aggregate announcement rather than one per minute."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code)
    collected: list[Any] = []

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        inserted = await persist.upsert_candles(
            session,
            [candle],
            {"BTCUSDT": market_id},
            source="rest",
            announce=False,
            collected=collected,
        )

    assert inserted == 1
    assert collected == [candle]
    assert await _outbox(db_session_factory) == []


# --- aggregated history announcement (T2.9c) --------------------------------


async def test_a_history_backfill_batch_is_announced_as_one_aggregate_event(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    base = builders.candle("BTCUSDT", exchange=code).open_time
    candles = [
        builders.candle("BTCUSDT", open_time=base + timedelta(minutes=n), exchange=code)
        for n in range(3)
    ]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await backfill_announce.enqueue_candles_backfilled(
            session, candles, reason="historical_recovery"
        )

    rows = await _outbox(db_session_factory)
    assert len(rows) == 1
    assert rows[0].stream == Streams.MARKET_CANDLES_BACKFILLED
    payload = rows[0].payload["payload"]
    assert payload["exchange"] == code
    assert payload["symbol"] == "BTCUSDT"
    assert payload["timeframe"] == Timeframe.M1.value
    assert payload["start"] == base.isoformat()
    assert payload["end"] == (base + timedelta(minutes=3)).isoformat()
    assert payload["count"] == 3
    assert payload["source"] == "rest"
    assert payload["reason"] == "historical_recovery"
    assert market_id  # the market exists; the event does not carry its id


async def test_an_empty_backfill_batch_announces_nothing(db_session_factory: Any) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await backfill_announce.enqueue_candles_backfilled(
            session, [], reason="historical_recovery"
        )

    assert await _outbox(db_session_factory) == []


async def test_two_disjoint_backfill_batches_get_different_identities(
    db_session_factory: Any,
) -> None:
    """Two committed batches for the same market/timeframe can never share a
    minimum -- ``ON CONFLICT DO NOTHING`` never lets the same minute be
    inserted twice -- so their spans are disjoint and the identity derived
    from ``min``/``max`` open_time never collides."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    base = builders.candle("BTCUSDT", exchange=code).open_time
    first_batch = [
        builders.candle("BTCUSDT", open_time=base + timedelta(minutes=n), exchange=code)
        for n in range(2)
    ]
    second_batch = [
        builders.candle("BTCUSDT", open_time=base + timedelta(minutes=n), exchange=code)
        for n in range(2, 4)
    ]

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await backfill_announce.enqueue_candles_backfilled(
            session, first_batch, reason="historical_recovery"
        )
        await backfill_announce.enqueue_candles_backfilled(
            session, second_batch, reason="historical_recovery"
        )

    rows = await _outbox(db_session_factory)
    assert len(rows) == 2
    assert rows[0].event_id != rows[1].event_id


async def test_a_spot_and_a_perp_history_batch_of_the_same_span_get_different_identities(
    db_session_factory: Any,
) -> None:
    """T3.0d: ``candles_backfilled_event_id`` had the same collision as
    ``candle_event_id`` -- a spot and a perpetual history recovery batch
    covering the same ``[start, end)`` for the same symbol/timeframe hashed to
    one uuid5. The perpetual's id is pinned against the pre-fix formula; the
    spot batch's is merely required to differ."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    base = builders.candle("BTCUSDT", exchange=code).open_time
    perp_batch = [builders.candle("BTCUSDT", open_time=base, exchange=code)]
    spot_batch = [
        builders.candle("BTCUSDT", open_time=base, exchange=code, market_type=MarketType.SPOT)
    ]
    end = base + timedelta(minutes=1)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await backfill_announce.enqueue_candles_backfilled(
            session, perp_batch, reason="historical_recovery"
        )
        await backfill_announce.enqueue_candles_backfilled(
            session, spot_batch, reason="historical_recovery"
        )

    rows = await _outbox(db_session_factory)
    assert len(rows) == 2, "both announcements survive -- neither is dropped as a duplicate"
    ids_by_type = {row.payload["payload"]["market_type"]: row.event_id for row in rows}
    assert set(ids_by_type) == {"perpetual", "spot"}
    assert ids_by_type["perpetual"] != ids_by_type["spot"]
    assert ids_by_type["perpetual"] == backfill_announce.candles_backfilled_event_id(
        code, "BTCUSDT", "1m", base, end, MarketType.PERPETUAL
    )
    assert ids_by_type["spot"] == backfill_announce.candles_backfilled_event_id(
        code, "BTCUSDT", "1m", base, end, MarketType.SPOT
    )


# --- liquidations, realized funding, open interest --------------------------


async def test_only_newly_inserted_liquidations_are_queued(db_session_factory: Any) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    liq = builders.liquidation("BTCUSDT", exchange=code)

    await persist.flush_batch(db_session_factory, code, [liq, liq])
    await persist.flush_batch(db_session_factory, code, [liq])

    rows = await _outbox(db_session_factory)
    assert len(rows) == 1
    assert rows[0].stream == Streams.MARKET_LIQUIDATIONS
    assert rows[0].event_id == liquidation_id(liq), "one identity end to end"


async def test_realized_funding_is_queued_as_realized(db_session_factory: Any) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    realized = RealizedFunding.model_validate(to_wire(builders.funding("BTCUSDT", exchange=code)))

    await persist.flush_batch(db_session_factory, code, [realized])

    rows = await _outbox(db_session_factory)
    assert len(rows) == 1
    assert rows[0].stream == Streams.MARKET_DERIVATIVES
    assert rows[0].payload["payload"]["funding_kind"] == "realized"
    assert rows[0].payload["payload"]["funding_rate"] == str(realized.funding_rate)


async def test_a_ws_funding_estimate_is_never_queued(db_session_factory: Any) -> None:
    """It is not persisted, so nothing durable depends on it: ephemeral."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)

    await persist.flush_batch(
        db_session_factory, code, [builders.funding("BTCUSDT", exchange=code)]
    )

    assert await _outbox(db_session_factory) == []


async def test_open_interest_is_queued_on_its_persisted_bucket(db_session_factory: Any) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    oi = builders.open_interest("BTCUSDT", exchange=code)
    bucket = persist_rows.oi_bucket(oi.ts)
    sample = OpenInterestSample(reading=oi, bucket_ts=bucket)

    await persist.flush_batch(db_session_factory, code, [sample])
    await persist.flush_batch(db_session_factory, code, [sample])  # same bucket, no second event

    rows = await _outbox(db_session_factory)
    assert len(rows) == 1
    assert rows[0].stream == Streams.MARKET_DERIVATIVES
    assert rows[0].event_id == durable.open_interest_event_id(oi, bucket)
    assert rows[0].payload["payload"]["bucket_ts"] == bucket.isoformat()
    assert rows[0].payload["payload"]["open_interest"] == str(oi.open_interest)


# --- end to end -------------------------------------------------------------


async def test_the_dispatcher_puts_the_queued_candle_on_the_stream(
    db_session_factory: Any, redis_client: Any
) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    await _clear_outbox(db_session_factory)
    candle = builders.candle("BTCUSDT", exchange=code)

    await persist.flush_batch(db_session_factory, code, [candle])
    assert await dispatch_pending(redis_client, db_session_factory) == 1

    entries = list(await redis_client.xrange(Streams.MARKET_CANDLES_CLOSED))
    assert len(entries) == 1
    assert str(durable.candle_event_id(candle)).encode() in entries[0][1][b"data"]
    assert await _outbox(db_session_factory) != []
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        undispatched = await session.scalar(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))
        )
    assert undispatched == 0


async def test_candle_event_ids_are_stable_and_market_specific() -> None:
    first = builders.candle("BTCUSDT", exchange="binance")
    same = builders.candle("BTCUSDT", exchange="binance", open_time=first.open_time)
    other = builders.candle("ETHUSDT", exchange="binance", open_time=first.open_time)
    later = builders.candle(
        "BTCUSDT", exchange="binance", open_time=first.open_time + timedelta(minutes=1)
    )

    assert durable.candle_event_id(first) == durable.candle_event_id(same)
    assert durable.candle_event_id(first) != durable.candle_event_id(other)
    assert durable.candle_event_id(first) != durable.candle_event_id(later)
    assert isinstance(durable.candle_event_id(first), uuid.UUID)


async def test_a_perp_and_a_spot_candle_of_the_same_minute_get_different_ids(
    db_session_factory: Any,
) -> None:
    """T3.0d, bloqueante da T3.0d (review-T3.0b.md item 1, notes-T3.0c.md §12
    ressalva 9): reproduced live on 2026-09-07 -- the same
    exchange/symbol/timeframe/``open_time`` on the two listings hashed to one
    uuid5, and the outbox's ``ON CONFLICT (event_id) DO NOTHING`` silently
    dropped whichever ``market.candles.closed`` committed second. Fixing the
    perpetual's id to the exact value it had *before* this fix pins the
    other, non-negotiable half of the contract: no id already announced in
    production may change.
    """
    code = unique_code()
    perp_market_id = await seed_market(
        db_session_factory, code, "BTCUSDT", market_type=MarketType.PERPETUAL
    )
    spot_market_id = await seed_market(
        db_session_factory, code, "BTCUSDT", market_type=MarketType.SPOT
    )
    await _clear_outbox(db_session_factory)
    open_time = builders.candle("BTCUSDT", exchange=code).open_time
    perp = builders.candle("BTCUSDT", exchange=code, open_time=open_time)
    spot = builders.candle(
        "BTCUSDT", exchange=code, open_time=open_time, market_type=MarketType.SPOT
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist_rows.upsert_candles(session, [perp], {"BTCUSDT": perp_market_id}, source="ws")
        await persist_rows.upsert_candles(session, [spot], {"BTCUSDT": spot_market_id}, source="ws")

    rows = await _outbox(db_session_factory)
    assert len(rows) == 2, "both closes are announced -- neither is dropped as a duplicate"
    ids = {row.event_id for row in rows}
    assert len(ids) == 2
    assert durable.candle_event_id(perp) != durable.candle_event_id(spot)


def test_the_perpetuals_candle_event_id_is_the_exact_value_it_had_before_market_type_existed() -> (
    None
):
    """The non-negotiable half of the fix above: adding ``market_type`` to the
    id's inputs must not change a single id already announced in production.
    ``PERPETUAL`` is the identity's default and its venue segment is the bare
    ``exchange`` (``keys.market_slug(..., PERPETUAL).rstrip(":")``), so this
    value is pinned by hand against the formula as it stood before T3.0d."""
    from datetime import UTC, datetime

    from hunter_core.domain.enums import Timeframe as TF

    candle = builders.candle(
        "BTCUSDT",
        exchange="binance",
        open_time=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
        timeframe=TF.M1,
    )

    assert str(durable.candle_event_id(candle)) == "40b42f73-c29e-5e66-ad43-670b8f7d1ae4"


async def test_handle_event_no_longer_publishes_a_closed_candle_directly(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The eager publish is gone: a candle on the stream that the persist
    transaction later rolled back is exactly the divergence T2.9 removes."""
    from hunter_market_worker import hot_state, ingest
    from hunter_market_worker.queues import PersistQueues

    queues = PersistQueues()
    coalescer = ingest.TickCoalescer()
    candle = builders.candle("BTCUSDT", exchange="binance", timeframe=Timeframe.M1)

    await ingest.handle_event(
        candle,
        redis_client,
        "market-worker@test",
        queues,
        coalescer,
        ingest.AcceptedEvents(),
        hot_state.TradeMemory(),
    )

    assert list(await redis_client.xrange(Streams.MARKET_CANDLES_CLOSED)) == []
    assert queues.events.qsize() == 1, "it still reaches the persist queue"


async def test_a_whole_flush_of_candles_costs_one_insert(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A minute boundary closes every monitored market at once. One statement
    per candle put ~200 extra round trips inside the flush transaction, on the
    drain's hot path — measured pushing ``/ready``'s persistence check red on
    the local stack."""
    code = unique_code()
    symbols = [f"SYM{i}USDT" for i in range(10)]
    for symbol in symbols:
        await seed_market(db_session_factory, code, symbol)
    await _clear_outbox(db_session_factory)
    candles: list[PersistItem] = [builders.candle(symbol, exchange=code) for symbol in symbols]

    statements: list[str] = []
    original = durable.enqueue_many

    async def counting(session: Any, envelopes: Any) -> int:
        statements.append("insert")
        return await original(session, envelopes)

    monkeypatch.setattr(durable, "enqueue_many", counting)
    await persist.flush_batch(db_session_factory, code, candles)

    assert len(await _outbox(db_session_factory)) == 10
    assert statements.count("insert") == 1, "one statement for the whole batch"
