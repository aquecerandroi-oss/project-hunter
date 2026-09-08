"""Coverage, bootstrap, finality and rollback against real Postgres."""

from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy import func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.observability import market_ingestion_gaps
from hunter_market_worker import recovery, recovery_drain, recovery_lifecycle
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.persist import upsert_candles

from . import builders
from .db_helpers import ensure_candle_partition, seed_market
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
            await recovery_drain.recover_registered(session, adapter, saved, "BTCUSDT", now)
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
            await recovery_drain.recover_registered(session, adapter, gap, "BTCUSDT", now)
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
        await recovery_drain.recover_registered(session, adapter, saved, "BTCUSDT", now)
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
        for _ in range(recovery_drain.MAX_ATTEMPTS):
            await recovery_drain.recover_registered(session, adapter, gap, "BTCUSDT", now)
        assert gap.status == "failed"
        assert gap.attempts == recovery_drain.MAX_ATTEMPTS
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
    # T3.7d: attempts is never reset across a reopen any more -- the seeded
    # life-1 failure already spent recovery_drain.MAX_ATTEMPTS (5), and this
    # cycle's single successful fetch after the reopen is the 6th.
    assert rows[0].attempts == 6


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
        for _ in range(recovery_drain.MAX_ATTEMPTS):
            await recovery_drain.recover_registered(session, adapter, gap, "BTCUSDT", now)
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


# ---- T3.7d item 1: a window entirely before the market's listing is terminal,
# never a failed/reopen loop (`.claude/state/notes-T3.7b-diag.md`) ------------


async def test_a_window_entirely_before_the_market_listing_becomes_unrecoverable(
    db_session_factory: Any,
) -> None:
    """The incident's direct cause: MARSCOINUSDT's four pre-listing windows
    returned ``200 OK`` with zero candles, forever, because the exchange will
    never have data for them. Classified on sight -- before any REST call and
    before spending an attempt -- from data this worker already has."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "MARSCOINUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    listed_at = now - timedelta(days=7)
    gap_start = listed_at - timedelta(minutes=1440)
    gap_end = listed_at - timedelta(minutes=1)
    adapter = FakeAdapter(code)  # no candles_response configured for this symbol

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
        await recovery_drain.recover_registered(
            session, adapter, gap, "MARSCOINUSDT", now, earliest_known=listed_at
        )
        assert gap.status == "unrecoverable"
        assert gap.attempts == 0  # never spent -- this was never an attempt
        event = await session.scalar(
            select(SystemEvent).where(
                SystemEvent.event == "market_gap_unrecoverable",
                SystemEvent.data["market_id"].astext == str(market_id),
            )
        )
        assert event is not None
        assert event.data["reason"] == "before_listing"
    assert adapter.fetch_candles_calls == []  # zero REST weight spent


async def test_a_window_at_or_after_the_market_listing_still_recovers_normally(
    db_session_factory: Any,
) -> None:
    """``earliest_known`` only vetoes a window strictly *older* than it --
    a window that reaches the market's first known candle (or later) fetches
    exactly as before T3.7d."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "MARSCOINUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    listed_at = now - timedelta(minutes=120)
    gap_start, gap_end = listed_at, listed_at + timedelta(minutes=1)
    adapter = FakeAdapter(code)
    adapter.candles_response["MARSCOINUSDT"] = [
        builders.candle("MARSCOINUSDT", gap_start, exchange=code),
        builders.candle("MARSCOINUSDT", gap_end, exchange=code),
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
        await recovery_drain.recover_registered(
            session, adapter, gap, "MARSCOINUSDT", now, earliest_known=listed_at
        )
        assert gap.status == "recovered"
    assert adapter.fetch_candles_calls  # a real fetch happened


async def test_check_gaps_classifies_pre_listing_history_and_recovers_post_listing_history(
    db_session_factory: Any,
) -> None:
    """End to end through ``recovery.check_gaps``: a market with one
    pre-listing history gap and one post-listing history gap resolves the
    first as ``unrecoverable`` and the second as ``recovered`` in the same
    cycle, and the heartbeat counts the terminal one apart from ``open_gaps``."""
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "MARSCOINUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

    listed_at = now - timedelta(days=6)
    await ensure_candle_partition(db_session_factory, listed_at)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await upsert_candles(
            session,
            [builders.candle("MARSCOINUSDT", listed_at, exchange=code)],
            {"MARSCOINUSDT": market_id},
            source="ws",
        )
    pre_start, pre_end = listed_at - timedelta(minutes=10), listed_at - timedelta(minutes=1)
    post_start, post_end = listed_at + timedelta(minutes=10), listed_at + timedelta(minutes=11)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        session.add(
            IngestionGap(
                market_id=market_id,
                timeframe=Timeframe.M1,
                gap_start=pre_start,
                gap_end=pre_end,
                status="open",
                attempts=0,
            )
        )
        session.add(
            IngestionGap(
                market_id=market_id,
                timeframe=Timeframe.M1,
                gap_start=post_start,
                gap_end=post_end,
                status="open",
                attempts=0,
            )
        )
        await session.flush()

    adapter = Adapter(code)
    adapter.candles_response["MARSCOINUSDT"] = [
        builders.candle("MARSCOINUSDT", post_start, exchange=code),
        builders.candle("MARSCOINUSDT", post_end, exchange=code),
    ]
    state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, adapter, ["MARSCOINUSDT"], state)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = {
            (r.gap_start, r.gap_end): r.status
            for r in (
                await session.scalars(
                    select(IngestionGap).where(IngestionGap.market_id == market_id)
                )
            ).all()
        }
    assert rows[(pre_start, pre_end)] == "unrecoverable"
    assert rows[(post_start, post_end)] == "recovered"
    assert state.unrecoverable_gaps == 1


# ---- T3.7d item 3: a `failed` gap reopens a bounded number of times, then
# becomes `unrecoverable` (reason=exhausted) instead of looping forever ------


async def test_a_failed_gap_past_its_reopen_budget_becomes_exhausted_not_reopened(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gap already on its second life (``attempts = 2 * MAX_ATTEMPTS``) is
    past ``max_reopens=1``: the very next detection cycle must exhaust it
    outright, cooldown or not -- an exhausted gap is not waiting for a timer,
    it is simply not retried again."""
    monkeypatch.setattr(recovery, "STEADY_WINDOW_MINUTES", 5)
    monkeypatch.setattr(recovery_lifecycle, "MAX_REOPEN_ATTEMPTS", 1)
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
            attempts=2 * recovery_drain.MAX_ATTEMPTS,  # life_count = 2 > max_reopens (1)
            detected_at=now,
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id

    state = HeartbeatState()
    await recovery.check_gaps(db_session_factory, Adapter(code), ["BTCUSDT"], state)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        saved = await session.get(IngestionGap, gap_id)
        event = await session.scalar(
            select(SystemEvent).where(
                SystemEvent.event == "market_gap_unrecoverable",
                SystemEvent.data["market_id"].astext == str(market_id),
            )
        )
    assert saved is not None and saved.status == "unrecoverable"
    assert event is not None and event.data["reason"] == "exhausted"
    assert state.unrecoverable_gaps == 1
