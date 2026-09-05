"""Durability before publication, observable XADD loss, stable buckets and queue drops."""

import asyncio
from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.market_data import (
    IngestionGap,
    Liquidation,
    MarketSnapshot,
    OpenInterestHistory,
)
from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.events.envelope import EventEnvelope
from hunter_core.observability import market_publish_failures_total
from hunter_market_worker import ingest, persist, publication
from hunter_market_worker.queues import Loss, PersistQueues, Snapshot

from . import builders
from .db_helpers import seed_market
from .fakes import FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_liquidation_commits_before_publication_with_same_uuid(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    liq = builders.liquidation("BTCUSDT", exchange=code)
    same = liq.model_copy(update={"price": liq.price.quantize(builders.Decimal("0.00"))})
    assert publication.liquidation_id(liq) == publication.liquidation_id(same)
    observed = asyncio.Event()
    original = ingest.publish_liquidation

    async def check_commit(redis: Any, producer: str, item: Any) -> None:
        # D11: the stored ts is truncated to the millisecond to match the
        # precision liquidation_id() hashes — not the raw microsecond value.
        expected_ts = item.ts.replace(microsecond=(item.ts.microsecond // 1000) * 1000)
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = await session.scalar(
                select(Liquidation).where(Liquidation.id == publication.liquidation_id(item))
            )
            assert row is not None and row.ts == expected_ts
        await original(redis, producer, item)
        observed.set()

    monkeypatch.setattr(ingest, "publish_liquidation", check_commit)
    monkeypatch.setattr(persist, "FLUSH_INTERVAL_S", 0.01)
    queues = PersistQueues()
    queues.events.put_nowait(liq)
    task = asyncio.create_task(
        persist.drain_loop(db_session_factory, code, queues, FakeRuntime(redis_client))
    )
    try:
        await asyncio.wait_for(observed.wait(), 5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    rows = await redis_client.xrange("market.liquidations")
    envelope = EventEnvelope.from_bytes(rows[0][1][b"data"])
    assert envelope.event_id == publication.liquidation_id(liq)


async def test_duplicate_liquidation_in_one_batch_is_published_exactly_once(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M1/D7 (Astra's second opinion): a within-batch redelivery collapses to
    one persisted row, and must not be republished twice just because both
    occurrences share the id of the one row that was actually inserted."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    liq = builders.liquidation("BTCUSDT", exchange=code)
    monkeypatch.setattr(persist, "FLUSH_INTERVAL_S", 0.01)
    queues = PersistQueues()
    queues.events.put_nowait(liq)
    queues.events.put_nowait(liq)  # redelivered within the same drain cycle
    runtime = FakeRuntime(redis_client)

    task = asyncio.create_task(persist.drain_loop(db_session_factory, code, queues, runtime))
    try:
        await asyncio.wait_for(runtime.success.wait(), 5)
        await asyncio.sleep(0.05)  # give a (buggy) second publish time to land
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    rows = await redis_client.xrange("market.liquidations")
    matching = [
        r
        for r in rows
        if EventEnvelope.from_bytes(r[1][b"data"]).event_id == publication.liquidation_id(liq)
    ]
    assert len(matching) == 1


async def test_xadd_failure_records_metric_and_system_warning(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*args: Any) -> Any:
        raise ConnectionError("xadd failed")

    monkeypatch.setattr(publication, "core_publish", fail)
    metric = market_publish_failures_total.labels(stream="market.liquidations")
    before = cast(Any, metric)._value.get()
    envelope = EventEnvelope(
        type="market.liquidations", producer="test", key="fake:BTCUSDT", payload={}
    )
    token = publication.publication_sessions.set(db_session_factory)
    try:
        assert await publication.publish(None, envelope.type, envelope, 20000) is None
    finally:
        publication.publication_sessions.reset(token)
    assert metric._value.get() == before + 1  # pyright: ignore[reportPrivateUsage]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(SystemEvent).where(
                SystemEvent.event == "market_publish_failed",
                SystemEvent.message.contains(str(envelope.event_id)),
            )
        )
    assert row is not None and row.level.value == "warning"


async def test_snapshot_retry_preserves_bucket_and_oi_uses_five_minutes(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = builders.utcnow().replace(second=0, microsecond=0)
    snapshot = Snapshot("BTCUSDT", {"ts": now, "price": builders.Decimal("100")})
    oi = builders.open_interest("BTCUSDT", ts=now + timedelta(seconds=17), exchange=code)
    await persist.flush_batch(db_session_factory, code, [snapshot, oi])
    await persist.flush_batch(db_session_factory, code, [snapshot, oi])
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = list(
            await session.scalars(
                select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
            )
        )
        interests = list(
            await session.scalars(
                select(OpenInterestHistory).where(OpenInterestHistory.market_id == market_id)
            )
        )
    assert len(rows) == len(interests) == 1
    assert rows[0].ts == now
    assert interests[0].ts.minute % 5 == 0 and interests[0].ts.second == 0


async def test_dropped_final_opens_registered_gap(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    queues = PersistQueues(max_items=1)
    queues.events.put_nowait(builders.liquidation("BTCUSDT"))
    final = builders.candle("BTCUSDT", exchange=code)
    queues.events.put_nowait(final)
    await persist.report_losses(db_session_factory, code, queues)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = await session.scalar(select(IngestionGap).where(IngestionGap.market_id == market_id))
    assert gap is not None and gap.status == "open" and gap.gap_start == final.open_time


async def test_transient_failure_retries_original_batch(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    snapshot = Snapshot("BTCUSDT", {"ts": builders.utcnow().replace(second=0, microsecond=0)})
    calls = 0
    completed = asyncio.Event()
    original = persist.flush_batch

    async def flaky(*args: Any) -> None:
        nonlocal calls
        calls += 1
        await original(*args)
        if calls == 1:
            raise ConnectionError("commit response lost")
        completed.set()

    monkeypatch.setattr(persist, "flush_batch", flaky)
    monkeypatch.setattr(persist, "FLUSH_INTERVAL_S", 0.01)
    queues = PersistQueues()
    queues.events.put_nowait(snapshot)
    task = asyncio.create_task(persist.drain_loop(db_session_factory, code, queues, FakeRuntime()))
    try:
        await asyncio.wait_for(completed.wait(), 5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        count = await session.scalar(
            select(func.count())
            .select_from(MarketSnapshot)
            .where(MarketSnapshot.market_id == market_id)
        )
    assert calls == 2 and count == 1


class _ErrorCountingRuntime(FakeRuntime):
    """``FakeRuntime`` plus an event set on the *second* ``mark_error`` — proves
    ``drain_loop`` kept iterating instead of dying after the first failure."""

    def __init__(self) -> None:
        super().__init__()
        self.errored_twice = asyncio.Event()

    def mark_error(self) -> None:
        super().mark_error()
        if self.error_count >= 2:
            self.errored_twice.set()


async def test_report_losses_failure_leaves_drain_loop_alive_and_losses_intact(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1: a transient DB blip while reporting losses must degrade, not kill
    the whole worker — the sibling ``flush_batch`` already has this guard."""

    async def failing_report_losses(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("postgres blip")

    monkeypatch.setattr(persist, "report_losses", failing_report_losses)
    monkeypatch.setattr(persist, "FLUSH_INTERVAL_S", 0.01)
    queues = PersistQueues()
    pending = builders.liquidation("BTCUSDT")
    queues.losses.append(Loss(pending, "capacity"))
    runtime = _ErrorCountingRuntime()

    task = asyncio.create_task(persist.drain_loop(db_session_factory, "fake", queues, runtime))
    try:
        await asyncio.wait_for(runtime.errored_twice.wait(), 2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert list(queues.losses) == [Loss(pending, "capacity")]
    assert runtime.error_count >= 2


async def test_report_losses_drain_is_robust_to_concurrent_eviction(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2: ``queues.losses`` is a bounded deque; if it shrinks between the
    snapshot and the post-commit drain (concurrent eviction), popping must
    stop at an empty deque instead of raising ``IndexError``."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    queues = PersistQueues(max_items=5)
    queues.drop(builders.liquidation("BTCUSDT", exchange=code), "capacity")
    queues.drop(builders.liquidation("BTCUSDT", exchange=code, qty="2"), "capacity")
    original_load_market_ids = persist.load_market_ids

    async def draining_load_market_ids(session: Any, exchange: str, symbols: set[str]) -> Any:
        result = await original_load_market_ids(session, exchange, symbols)
        queues.losses.clear()  # a concurrent eviction empties the deque mid-flight
        return result

    monkeypatch.setattr(persist, "load_market_ids", draining_load_market_ids)

    await persist.report_losses(db_session_factory, code, queues)  # must not raise

    assert len(queues.losses) == 0


async def test_report_losses_drain_keeps_losses_added_concurrently(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2 (Astra's second opinion): the drain removes exactly the reported
    items, by identity — not just by count. A full deque whose reported
    entries are evicted (from the *left*, on ``append``) by brand-new losses
    arriving while the report's session is still open must not have those new,
    never-reported losses swept away by a naive ``popleft() * len(reported)``."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    queues = PersistQueues(max_items=2)
    reported_a = builders.liquidation("BTCUSDT", exchange=code, qty="1")
    reported_b = builders.liquidation("BTCUSDT", exchange=code, qty="2")
    queues.drop(reported_a, "capacity")
    queues.drop(reported_b, "capacity")  # deque is now full: [reported_a, reported_b]
    concurrent_new = [
        builders.liquidation("BTCUSDT", exchange=code, qty="3"),
        builders.liquidation("BTCUSDT", exchange=code, qty="4"),
    ]
    original_load_market_ids = persist.load_market_ids

    async def appending_load_market_ids(session: Any, exchange: str, symbols: set[str]) -> Any:
        result = await original_load_market_ids(session, exchange, symbols)
        for item in concurrent_new:
            # each append evicts the oldest *reported* entry — by the time the
            # session below commits, neither reported_a nor reported_b is
            # still in the deque; both slots now hold never-reported losses.
            queues.drop(item, "capacity")
        return result

    monkeypatch.setattr(persist, "load_market_ids", appending_load_market_ids)

    await persist.report_losses(db_session_factory, code, queues)

    remaining = [loss.item for loss in queues.losses]
    assert remaining == concurrent_new


async def test_dropping_the_same_final_candle_twice_creates_exactly_one_gap(
    db_session_factory: Any,
) -> None:
    """MEDIUM-8: redelivery-then-capacity-drop of the same final candle must
    not open two identical gaps for the same minute."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    candle = builders.candle("BTCUSDT", exchange=code)
    queues = PersistQueues()
    queues.drop(candle, "capacity")
    queues.drop(candle, "age")

    await persist.report_losses(db_session_factory, code, queues)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gaps = list(
            await session.scalars(
                select(IngestionGap).where(
                    IngestionGap.market_id == market_id,
                    IngestionGap.gap_start == candle.open_time,
                )
            )
        )
    assert len(gaps) == 1


async def test_dropping_an_already_persisted_candle_creates_no_gap(
    db_session_factory: Any,
) -> None:
    """MEDIUM-8: a flush that times out after the commit already succeeded
    must not open a phantom gap for a candle that is already durable."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    candle = builders.candle("BTCUSDT", exchange=code)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_candles(session, [candle], {"BTCUSDT": market_id}, source="ws")
    queues = PersistQueues()
    queues.drop(candle, "age")

    await persist.report_losses(db_session_factory, code, queues)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gaps = list(
            await session.scalars(
                select(IngestionGap).where(
                    IngestionGap.market_id == market_id,
                    IngestionGap.gap_start == candle.open_time,
                )
            )
        )
    assert gaps == []
