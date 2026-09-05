"""Gap detection and REST backfill — docs/plans/M1.md T1.3 item 4."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event, func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_market_worker import persist, recovery
from hunter_market_worker.heartbeat import HeartbeatState

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_check_gaps_backfills_when_no_candles_exist(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    adapter = FakeAdapter(code=exchange_code)
    # recovery.DETECTION_GRACE (D5): check_gaps' detection window ends two
    # minutes back, not one, so the newest expected minute matches that.
    end = align_open_time(utcnow() - recovery.DETECTION_GRACE, Timeframe.M1)
    # Mid-range, not at the tail: a response that does not reach gap_end
    # never satisfies the M2 "history starts later" narrowing, so this stays
    # a genuinely incomplete backfill (unlike test_recovery_contracts.py's
    # dedicated M2 tests).
    expected_open = end - timedelta(minutes=5)
    adapter.candles_response["BTCUSDT"] = [
        builders.candle("BTCUSDT", open_time=expected_open, exchange=exchange_code)
    ]
    heartbeat_state = HeartbeatState()

    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], heartbeat_state)

    assert adapter.fetch_candles_calls  # REST backfill was attempted
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        candle_count = await session.scalar(
            select(func.count())
            .select_from(Candle)
            .where(Candle.market_id == market_id, Candle.source == "rest")
        )
        gap = await session.scalar(select(IngestionGap).where(IngestionGap.market_id == market_id))
    assert candle_count == 1
    assert gap is not None
    assert gap.status == "open"
    assert heartbeat_state.open_gaps == 1


async def test_check_gaps_widens_an_existing_open_gap_and_marks_failed_on_repeated_error(
    db_session_factory: Any,
) -> None:
    from hunter_exchanges.base import ExchangeUnavailable

    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ETHUSDT")

    # The five cycles below must all see the same "now". A bare FakeAdapter has
    # no server_time(), so recovery.server_now() falls back to utcnow() on every
    # call; a loop crossing a minute boundary shifts the detection window, opens
    # a second gap and the attempts assertion fails intermittently. (The utcnow
    # fallback itself stays covered by the other tests in this module, which use
    # a bare FakeAdapter on purpose.)
    frozen_now = align_open_time(utcnow(), Timeframe.M1)

    class FrozenClockAdapter(FakeAdapter):
        async def server_time(self) -> Any:
            return frozen_now

    adapter = FrozenClockAdapter(code=exchange_code)
    heartbeat_state = HeartbeatState()

    async def _always_fails(symbol: Any, timeframe: Any, start: Any, end: Any):
        raise ExchangeUnavailable("boom", exchange=exchange_code)

    adapter.fetch_candles = _always_fails  # type: ignore[method-assign]

    for _ in range(recovery.MAX_ATTEMPTS):
        await recovery.check_gaps(db_session_factory, adapter, ["ETHUSDT"], heartbeat_state)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = await session.scalar(select(IngestionGap).where(IngestionGap.market_id == market_id))
    assert gap is not None
    assert gap.status == "failed"
    assert gap.attempts == recovery.MAX_ATTEMPTS


async def test_check_gaps_is_a_noop_once_up_to_date(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    # Frozen: seeding 1440 candles takes long enough to cross a minute
    # boundary, after which check_gaps would expect one minute nobody seeded
    # and fire a REST backfill. (The utcnow fallback of server_now stays
    # covered by test_check_gaps_backfills_when_no_candles_exist, which uses a
    # bare FakeAdapter.)
    frozen_now = align_open_time(utcnow(), Timeframe.M1)
    expected_open = align_open_time(frozen_now - recovery.DETECTION_GRACE, Timeframe.M1)
    candles = [
        builders.candle(
            "BTCUSDT", open_time=expected_open - timedelta(minutes=i), exchange=exchange_code
        )
        for i in range(1440)
    ]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_candles(session, candles, {"BTCUSDT": market_id}, source="ws")

    class FrozenClockAdapter(FakeAdapter):
        async def server_time(self) -> Any:
            return frozen_now

    adapter = FrozenClockAdapter(code=exchange_code)
    heartbeat_state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], heartbeat_state)

    assert adapter.fetch_candles_calls == []
    assert heartbeat_state.open_gaps == 0


# ---- D5: detection never races the persistence queue's own lag tolerance --


async def test_check_gaps_grace_period_avoids_racing_the_persistence_queue(
    db_session_factory: Any,
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    t = align_open_time(utcnow(), Timeframe.M1)
    # the final candle for minute t is "enqueued but not flushed" -> simply
    # absent from Postgres; history is otherwise fully caught up through t-1
    candles = [
        builders.candle("BTCUSDT", t - timedelta(minutes=i), exchange=exchange_code)
        for i in range(1, recovery.STEADY_WINDOW_MINUTES + 2)
    ]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await persist.upsert_candles(session, candles, {"BTCUSDT": market_id}, source="ws")

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return t + timedelta(seconds=70)  # "now" = T + 70s

    adapter = Adapter(exchange_code)
    heartbeat_state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], heartbeat_state)

    assert adapter.fetch_candles_calls == []
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap_count = await session.scalar(
            select(func.count())
            .select_from(IngestionGap)
            .where(IngestionGap.market_id == market_id)
        )
    assert gap_count == 0
    assert heartbeat_state.open_gaps == 0


# ---- HIGH-2: detection is set-based, not one round trip per market --------


async def test_check_gaps_detection_statement_count_does_not_grow_with_market_count(
    db_session_factory: Any,
) -> None:
    exchange_code = unique_code()
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

    async def _run(n: int) -> int:
        symbols = [f"SYM{i}USDT" for i in range(n)]
        market_ids = [
            await seed_market(db_session_factory, exchange_code, symbol) for symbol in symbols
        ]
        end = now - recovery.DETECTION_GRACE
        start = end - recovery.MINUTE * recovery.BOOTSTRAP_WINDOW_MINUTES
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            for market_id in market_ids:
                # a `failed` gap inside its cooldown covers the whole
                # bootstrap window, so detection finds nothing missing and
                # the recovery phase (which *does* scale with N) never runs.
                session.add(
                    IngestionGap(
                        market_id=market_id,
                        timeframe=Timeframe.M1,
                        gap_start=start,
                        gap_end=end,
                        status="failed",
                        attempts=recovery.MAX_ATTEMPTS,
                        detected_at=utcnow(),
                    )
                )
            await session.flush()

        adapter = Adapter(exchange_code)
        heartbeat_state = HeartbeatState()
        statements: list[str] = []
        engine = db_session_factory.kw["bind"].sync_engine

        def _listener(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _listener)
        try:
            await recovery.check_gaps(db_session_factory, adapter, symbols, heartbeat_state)
        finally:
            event.remove(engine, "before_cursor_execute", _listener)

        assert adapter.fetch_candles_calls == []  # nothing was missing -> isolates detection
        return len(statements)

    small = await _run(3)
    large = await _run(25)
    assert small == large


# ---- M3: bounded, timed-out, non-blocking per-cycle recovery --------------


async def test_check_gaps_bounds_recovery_work_per_cycle(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "STEADY_WINDOW_MINUTES", 130)
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

        async def fetch_candles(self, *args: Any, **kwargs: Any) -> list[Any]:
            self.fetch_candles_calls.append(args)  # type: ignore[arg-type]
            raise RuntimeError("REST unavailable")

    end = now - recovery.DETECTION_GRACE
    open_minutes = [end - timedelta(minutes=i) for i in range(120)]
    covered_minutes = {
        end - timedelta(minutes=i) for i in range(recovery.STEADY_WINDOW_MINUTES + 1)
    } - set(open_minutes)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        # the watermark (steady state) plus the ten minutes outside the 120
        # open gaps, fully persisted so detection adds nothing new
        await persist.upsert_candles(
            session,
            [builders.candle("BTCUSDT", m, exchange=exchange_code) for m in covered_minutes],
            {"BTCUSDT": market_id},
            source="ws",
        )
        for minute in open_minutes:
            session.add(
                IngestionGap(
                    market_id=market_id,
                    timeframe=Timeframe.M1,
                    gap_start=minute,
                    gap_end=minute,
                    status="open",
                    attempts=0,
                )
            )
        await session.flush()

    adapter = Adapter(exchange_code)
    heartbeat_state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], heartbeat_state)

    assert len(adapter.fetch_candles_calls) == recovery.MAX_GAPS_PER_CYCLE
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        open_count = await session.scalar(
            select(func.count())
            .select_from(IngestionGap)
            .where(IngestionGap.market_id == market_id, IngestionGap.status == "open")
        )
    assert open_count == 120  # all still open: attempts++ on failure, none recovered/failed yet


async def test_recover_registered_times_out_a_hanging_fetch_and_increments_attempts(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery, "FETCH_TIMEOUT_S", 0.05)
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class HangingAdapter(FakeAdapter):
        async def fetch_candles(self, *args: Any, **kwargs: Any) -> list[Any]:
            await asyncio.sleep(10)
            return []

    adapter = HangingAdapter(exchange_code)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=now - timedelta(minutes=1),
            gap_end=now - timedelta(minutes=1),
            attempts=0,
            status="open",
        )
        session.add(gap)
        await session.flush()

        await recovery.recover_registered(session, adapter, gap, "BTCUSDT", now)

        assert gap.attempts == 1
        assert gap.status == "open"  # below MAX_ATTEMPTS, the loop keeps going


async def test_recover_one_fetches_over_rest_with_no_connection_checked_out(
    db_session_factory: Any,
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    gap_minute = now - timedelta(minutes=1)
    engine = db_session_factory.kw["bind"]

    class Adapter(FakeAdapter):
        async def fetch_candles(self, *args: Any, **kwargs: Any) -> list[Any]:
            checked_out_during_fetch.append(engine.pool.checkedout())
            return await super().fetch_candles(*args, **kwargs)

    checked_out_during_fetch: list[int] = []
    adapter = Adapter(exchange_code)
    adapter.candles_response["BTCUSDT"] = [
        builders.candle("BTCUSDT", gap_minute, exchange=exchange_code)
    ]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=gap_minute,
            gap_end=gap_minute,
            attempts=0,
            status="open",
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id

    await recovery._recover_one(  # pyright: ignore[reportPrivateUsage]
        db_session_factory, adapter, gap_id, "BTCUSDT", now
    )

    assert checked_out_during_fetch == [0]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        saved = await session.get(IngestionGap, gap_id)
    assert saved is not None and saved.status == "recovered"
