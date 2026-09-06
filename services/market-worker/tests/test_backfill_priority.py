"""Live collection is never queued behind a bootstrap.

``ingestion_gaps`` has no ``source`` column and this task may not add one, so
the two classes of work are told apart by **the age of the window**, which is a
property of the data rather than of who wrote the row: the periodic detection
only ever creates gaps inside its own window (``BOOTSTRAP_WINDOW_MINUTES``, 1499
minutes), so anything older than that is, by construction, history someone asked
for. A backfill request *inside* the last day describes exactly the minutes the
detection would have found by itself, and treating it as live is not a mistake.

What the tier buys is stated as a guarantee and tested as one: the live tier is
served first and in full, history spends only what is left of the per-cycle
budget, and history is additionally bounded in **time** so a slow page of old
candles cannot push the next detection past its one-minute cadence (Astra,
T2.5-backfill design review, must-fix 3).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_market_worker import recovery
from hunter_market_worker import recovery_queries as queries
from hunter_market_worker.heartbeat import HeartbeatState

from . import builders
from .db_helpers import ensure_candle_partition, seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

MINUTE = timedelta(minutes=1)


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


async def test_the_newest_missing_minute_is_recovered_first(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    oldest = await add_gap(db_session_factory, market_id, now - 600 * MINUTE, now - 590 * MINUTE)
    newest = await add_gap(db_session_factory, market_id, now - 5 * MINUTE, now - 4 * MINUTE)
    middle = await add_gap(db_session_factory, market_id, now - 200 * MINUTE, now - 190 * MINUTE)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        live, history = await queries.pending_gaps(
            session,
            [market_id],
            live_from=now - MINUTE * recovery.BOOTSTRAP_WINDOW_MINUTES,
            live_limit=10,
            history_limit=10,
        )

    assert [gap_id for gap_id, _ in live] == [newest, middle, oldest]
    assert history == []


async def test_history_never_takes_the_budget_of_live_collection(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ETHUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    live_from = now - MINUTE * recovery.BOOTSTRAP_WINDOW_MINUTES
    for n in range(3):
        await add_gap(
            db_session_factory, market_id, now - (10 + n) * MINUTE, now - (9 + n) * MINUTE
        )
    old = await add_gap(
        db_session_factory, market_id, live_from - 300 * MINUTE, live_from - 60 * MINUTE
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        live, history = await queries.pending_gaps(
            session, [market_id], live_from=live_from, live_limit=2, history_limit=10
        )

    # The cycle's budget is two gaps and live collection wants three: history
    # gets nothing at all this cycle, not "one of the two".
    assert len(live) == 2
    assert history == []
    assert old not in [gap_id for gap_id, _ in live]


async def test_history_takes_the_leftover_under_its_own_ceiling(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "SOLUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    live_from = now - MINUTE * recovery.BOOTSTRAP_WINDOW_MINUTES
    await add_gap(db_session_factory, market_id, now - 10 * MINUTE, now - 9 * MINUTE)
    for n in range(4):
        start = live_from - MINUTE * (1000 + 300 * n)
        await add_gap(db_session_factory, market_id, start, start + 240 * MINUTE)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        live, history = await queries.pending_gaps(
            session, [market_id], live_from=live_from, live_limit=10, history_limit=2
        )

    assert len(live) == 1
    assert len(history) == 2


async def test_the_boundary_is_the_detection_window_itself(db_session_factory: Any) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "ADAUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    live_from = now - MINUTE * recovery.BOOTSTRAP_WINDOW_MINUTES
    inside = await add_gap(db_session_factory, market_id, live_from, live_from + 5 * MINUTE)
    outside = await add_gap(
        db_session_factory, market_id, live_from - 10 * MINUTE, live_from - MINUTE
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        live, history = await queries.pending_gaps(
            session, [market_id], live_from=live_from, live_limit=10, history_limit=10
        )

    assert [gap_id for gap_id, _ in live] == [inside]
    assert [gap_id for gap_id, _ in history] == [outside]


async def test_a_backfill_gap_older_than_the_detection_window_is_still_drained(
    db_session_factory: Any,
) -> None:
    """The whole point of the feature: a seven-day-old window gets fetched.

    Before this task the pending selection ordered by ``detected_at`` and the
    detection window (1439 minutes) never reached back to it — the row could
    exist and never be drained.
    """
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "DOTUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    old_start = now - 6 * 24 * 60 * MINUTE
    await ensure_candle_partition(db_session_factory, old_start)
    await add_gap(db_session_factory, market_id, old_start, old_start + 2 * MINUTE)
    adapter = FakeAdapter(code=exchange_code)
    adapter.candles_response["DOTUSDT"] = [
        builders.candle("DOTUSDT", open_time=old_start + MINUTE * n, exchange=exchange_code)
        for n in range(3)
    ]

    await recovery.check_gaps(db_session_factory, adapter, ["DOTUSDT"], HeartbeatState())

    assert any(
        call[0] == "DOTUSDT" and call[2] == old_start for call in adapter.fetch_candles_calls
    )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        status = await session.scalar(
            select(IngestionGap.status).where(
                IngestionGap.market_id == market_id, IngestionGap.gap_start == old_start
            )
        )
    assert status == "recovered"


async def test_the_history_tier_stops_when_its_time_budget_is_spent(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "LINKUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    old_start = now - 6 * 24 * 60 * MINUTE
    await ensure_candle_partition(db_session_factory, old_start)
    await add_gap(db_session_factory, market_id, old_start, old_start + 2 * MINUTE)
    adapter = FakeAdapter(code=exchange_code)
    monkeypatch.setattr(recovery, "HISTORY_BUDGET_S", 0.0)

    await recovery.check_gaps(db_session_factory, adapter, ["LINKUSDT"], HeartbeatState())

    assert not any(call[2] == old_start for call in adapter.fetch_candles_calls)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        attempts = await session.scalar(
            select(IngestionGap.attempts).where(
                IngestionGap.market_id == market_id, IngestionGap.gap_start == old_start
            )
        )
    # Not attempted at all: a budget that ran out is not this gap's failure and
    # must not spend one of its MAX_ATTEMPTS.
    assert attempts == 0


def test_the_history_deadline_is_the_cycle_end_when_live_collection_was_slow() -> None:
    """Astra, T2.5-backfill diff review, must-fix 2 — her own numbers.

    Live collection spends 45s of the 60s cycle. A fresh 30s budget starting
    *then* would end the cycle at 81s and push the next detection more than a
    minute late; the deadline is the earlier of the two clocks, so history gets
    the 10s that are actually left.
    """
    cycle_start = 1000.0
    after_live = cycle_start + 45.0

    deadline = recovery.history_deadline(cycle_start, after_live)

    assert deadline == cycle_start + recovery.CHECK_INTERVAL_S - recovery.CYCLE_TAIL_MARGIN_S
    assert deadline - after_live == 10.0


def test_the_history_budget_still_caps_a_cycle_that_started_fast() -> None:
    cycle_start = 1000.0

    deadline = recovery.history_deadline(cycle_start, cycle_start + 1.0)

    assert deadline == cycle_start + 1.0 + recovery.HISTORY_BUDGET_S


async def test_a_unit_that_outlives_the_budget_does_not_spend_an_attempt(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deadline wraps the whole unit, and a cancelled unit rolls back.

    ``recover_one`` increments ``attempts`` inside its own transaction, so a
    unit cancelled by the cycle's deadline must leave the gap untouched — the
    budget running out is not this gap's failure.
    """
    import asyncio

    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "FILUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)
    old_start = now - 6 * 24 * 60 * MINUTE
    await ensure_candle_partition(db_session_factory, old_start)
    await add_gap(db_session_factory, market_id, old_start, old_start + 2 * MINUTE)

    class SlowAdapter(FakeAdapter):
        async def fetch_candles(self, *args: Any, **kwargs: Any) -> list[Any]:
            await asyncio.sleep(30)
            return []

    adapter = SlowAdapter(code=exchange_code)
    monkeypatch.setattr(recovery, "MIN_FETCH_BUDGET_S", 0.05)
    monkeypatch.setattr(recovery, "HISTORY_BUDGET_S", 0.2)

    await recovery.check_gaps(db_session_factory, adapter, ["FILUSDT"], HeartbeatState())

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.execute(
            select(IngestionGap.attempts, IngestionGap.status).where(
                IngestionGap.market_id == market_id, IngestionGap.gap_start == old_start
            )
        )
        attempts, status = row.one()
    assert (attempts, status) == (0, "open")
