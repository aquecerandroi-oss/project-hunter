"""Coverage, bootstrap, finality and rollback against real Postgres."""

from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.observability import market_ingestion_gaps
from hunter_market_worker import recovery
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.persist import upsert_candles

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_bootstrap_1500_closed_uses_exchange_clock(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

    adapter = Adapter(code)
    # recovery.DETECTION_GRACE (D5) pushes the window one minute earlier than
    # before, so the bootstrap query now spans 1501 minutes back; feed one
    # more candle than that so the fixture still fully covers it.
    adapter.candles_response["BTCUSDT"] = [
        builders.candle("BTCUSDT", now - timedelta(minutes=i), exchange=code) for i in range(1502)
    ]
    state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], state)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        count = await session.scalar(
            select(func.count()).select_from(Candle).where(Candle.market_id == market_id)
        )
        gap = await session.scalar(select(IngestionGap).where(IngestionGap.market_id == market_id))
    assert count == 1500
    assert gap is not None and gap.status == "recovered" and gap.attempts == 1
    assert state.open_gaps == 0
    assert adapter.fetch_candles_calls[0][2:] == (
        now - timedelta(minutes=1501),
        now - timedelta(minutes=1),
    )


async def test_internal_hole_before_watermark_is_recovered(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    end = align_open_time(utcnow(), Timeframe.M1) - recovery.DETECTION_GRACE
    candles = [
        builders.candle("BTCUSDT", end - timedelta(minutes=i), exchange=code) for i in range(1440)
    ]
    missing = candles.pop(17)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await upsert_candles(session, candles, {"BTCUSDT": market_id}, source="ws")
    adapter = FakeAdapter(code)
    adapter.candles_response["BTCUSDT"] = [missing]
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], HeartbeatState())
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = await session.scalar(select(IngestionGap).where(IngestionGap.market_id == market_id))
    assert gap is not None and gap.status == "recovered"
    assert gap.gap_start == gap.gap_end == missing.open_time


async def test_recovery_transition_and_inserts_roll_back_together(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    opened = now - timedelta(minutes=1)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=opened,
            gap_end=opened,
            attempts=0,
            status="open",
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id
    adapter = FakeAdapter(code)
    adapter.candles_response["BTCUSDT"] = [builders.candle("BTCUSDT", opened)]
    with pytest.raises(RuntimeError, match="abort"):
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            saved = await session.get(IngestionGap, gap_id)
            assert saved is not None
            await recovery.recover_registered(session, adapter, saved, "BTCUSDT", now)
            assert saved.status == "recovered"
            raise RuntimeError("abort transaction")
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        saved = await session.get(IngestionGap, gap_id)
        count = await session.scalar(
            select(func.count()).select_from(Candle).where(Candle.market_id == market_id)
        )
    assert saved is not None and saved.status == "open" and saved.attempts == 0
    assert count == 0


async def test_partial_finality_and_incomplete_backfill_after_five(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    opened = now - timedelta(minutes=1)
    partial = builders.candle("BTCUSDT", opened, is_final=False)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert await upsert_candles(session, [partial], {"BTCUSDT": market_id}, source="rest") == 0
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=opened,
            gap_end=opened,
            attempts=0,
            status="open",
        )
        session.add(gap)
        await session.flush()
        adapter = FakeAdapter(code)
        adapter.candles_response["BTCUSDT"] = [partial]
        for _ in range(5):
            await recovery.recover_registered(session, adapter, gap, "BTCUSDT", now)
        assert gap.status == "failed" and gap.attempts == 5


# ---- M2: a newly listed perpetual never demands history before it existed ----


async def test_history_starts_later_narrows_gap_and_recovers(db_session_factory: Any) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    gap_end = now - timedelta(minutes=1)
    gap_start = gap_end - timedelta(minutes=1499)
    listed_at = gap_end - timedelta(minutes=119)  # only the last 120 minutes exist
    candles = [
        builders.candle("BTCUSDT", listed_at + timedelta(minutes=i), exchange=code)
        for i in range(120)
    ]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=gap_start,
            gap_end=gap_end,
            attempts=0,
            status="open",
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id
    adapter = FakeAdapter(code)
    adapter.candles_response["BTCUSDT"] = candles
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        saved = await session.get(IngestionGap, gap_id)
        assert saved is not None
        await recovery.recover_registered(session, adapter, saved, "BTCUSDT", now)
        assert saved.status == "recovered"
        assert saved.gap_start == listed_at
        assert saved.attempts == 1


async def test_empty_fetch_still_increments_attempts_and_eventually_fails(
    db_session_factory: Any,
) -> None:
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    gap_end = now - timedelta(minutes=1)
    gap_start = gap_end - timedelta(minutes=1499)
    adapter = FakeAdapter(code)  # candles_response stays empty -> []
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=gap_start,
            gap_end=gap_end,
            attempts=0,
            status="open",
        )
        session.add(gap)
        await session.flush()
        for _ in range(recovery.MAX_ATTEMPTS):
            await recovery.recover_registered(session, adapter, gap, "BTCUSDT", now)
        assert gap.status == "failed"
        assert gap.attempts == recovery.MAX_ATTEMPTS
        assert gap.gap_start == gap_start  # never narrowed: an empty response
        # is a failed/absent REST call, not proof that history starts later


# ---- D6 + MEDIUM-5: failed gaps are retried, not suppressed forever --------


async def test_failed_gap_past_cooldown_is_reopened_and_recovered(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "STEADY_WINDOW_MINUTES", 5)
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

    end = now - recovery.DETECTION_GRACE
    stale_minute = end - timedelta(minutes=3)
    candles = [
        builders.candle("BTCUSDT", end - timedelta(minutes=i), exchange=code)
        for i in range(recovery.STEADY_WINDOW_MINUTES + 1)
        if end - timedelta(minutes=i) != stale_minute
    ]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await upsert_candles(session, candles, {"BTCUSDT": market_id}, source="ws")
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=stale_minute,
            gap_end=stale_minute,
            status="failed",
            attempts=5,
            detected_at=now - timedelta(seconds=recovery.FAILED_RETRY_AFTER_S + 10),
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id

    adapter = Adapter(code)
    adapter.candles_response["BTCUSDT"] = [builders.candle("BTCUSDT", stale_minute, exchange=code)]
    state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], state)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.scalars(select(IngestionGap).where(IngestionGap.market_id == market_id))
        ).all()
    assert len(rows) == 1  # reopened in place, never duplicated
    assert rows[0].id == gap_id
    assert rows[0].status == "recovered"
    assert rows[0].attempts == 1


async def test_refailed_gap_refreshes_detected_at_so_cooldown_restarts(
    db_session_factory: Any,
) -> None:
    """Astra's second opinion on this brief: detected_at must move forward on
    every re-failure, or a gap reopened once and failing again would already
    be past FAILED_RETRY_AFTER_S and get reopened on the very next cycle."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    old_detected_at = now - timedelta(seconds=recovery.FAILED_RETRY_AFTER_S + 500)
    adapter = FakeAdapter(code)  # empty candles_response -> never covers the gap
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=now - timedelta(minutes=1),
            gap_end=now - timedelta(minutes=1),
            status="open",
            attempts=0,
            detected_at=old_detected_at,
        )
        session.add(gap)
        await session.flush()
        for _ in range(recovery.MAX_ATTEMPTS):
            await recovery.recover_registered(session, adapter, gap, "BTCUSDT", now)
        assert gap.status == "failed"
        assert gap.detected_at == now
        assert gap.detected_at > old_detected_at


async def test_failed_gap_within_cooldown_stays_failed_and_uncounted_as_open(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "STEADY_WINDOW_MINUTES", 5)
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

    end = now - recovery.DETECTION_GRACE
    stale_minute = end - timedelta(minutes=3)
    candles = [
        builders.candle("BTCUSDT", end - timedelta(minutes=i), exchange=code)
        for i in range(recovery.STEADY_WINDOW_MINUTES + 1)
        if end - timedelta(minutes=i) != stale_minute
    ]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await upsert_candles(session, candles, {"BTCUSDT": market_id}, source="ws")
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=stale_minute,
            gap_end=stale_minute,
            status="failed",
            attempts=5,
            detected_at=now - timedelta(seconds=10),  # well inside the cooldown
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id

    adapter = Adapter(code)
    state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], state)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.scalars(select(IngestionGap).where(IngestionGap.market_id == market_id))
        ).all()
    assert len(rows) == 1
    assert rows[0].id == gap_id
    assert rows[0].status == "failed"
    assert rows[0].attempts == 5
    assert adapter.fetch_candles_calls == []
    assert state.open_gaps == 0
    failed_gauge = cast(Any, market_ingestion_gaps.labels(exchange=code, status="failed"))
    open_gauge = cast(Any, market_ingestion_gaps.labels(exchange=code, status="open"))
    assert failed_gauge._value.get() == 1  # pyright: ignore[reportPrivateUsage]
    assert open_gauge._value.get() == 0  # pyright: ignore[reportPrivateUsage]
