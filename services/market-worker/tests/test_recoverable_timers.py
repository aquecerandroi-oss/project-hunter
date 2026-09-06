"""Timers and confirmers must survive a restart (T2.9).

Anything the worker "will do later" — a failed gap's retry cooldown, an event
still owed to a stream — has to live in Postgres, not in a process that a
deploy or an OOM kill can take away mid-countdown. Each test here simulates the
restart literally: it throws away every object that held state and re-runs the
work with fresh ones.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select, update

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.events.outbox import OutboxHealth
from hunter_core.events.streams import Streams
from hunter_market_worker import outbox, persist, recovery
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.persist import upsert_candles

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def _status(factory: Any, market_id: Any) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list(
            (
                await session.scalars(
                    select(IngestionGap).where(IngestionGap.market_id == market_id)
                )
            ).all()
        )


async def test_a_failed_gaps_cooldown_is_read_from_postgres_after_a_restart(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry cooldown of a ``failed`` gap has no in-memory half at all: the
    only clock it consults is ``ingestion_gaps.detected_at`` (D6). Two
    independent "processes" below share nothing but the database, and the
    second still refuses to retry — then reopens the moment the durable
    deadline, not any object's lifetime, says it may."""
    monkeypatch.setattr(recovery, "STEADY_WINDOW_MINUTES", 5)
    code = unique_code()
    market_id = await seed_market(db_session_factory, code, "BTCUSDT")
    now = align_open_time(utcnow(), Timeframe.M1)

    class Adapter(FakeAdapter):
        async def server_time(self) -> Any:
            return now

    end = now - recovery.DETECTION_GRACE
    stale_minute = end - timedelta(minutes=3)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await upsert_candles(
            session,
            [
                builders.candle("BTCUSDT", end - timedelta(minutes=i), exchange=code)
                for i in range(recovery.STEADY_WINDOW_MINUTES + 1)
                if end - timedelta(minutes=i) != stale_minute
            ],
            {"BTCUSDT": market_id},
            source="ws",
        )
        gap = IngestionGap(
            market_id=market_id,
            timeframe=Timeframe.M1,
            gap_start=stale_minute,
            gap_end=stale_minute,
            status="failed",
            attempts=5,
            detected_at=now - timedelta(seconds=10),  # deep inside the cooldown
        )
        session.add(gap)
        await session.flush()
        gap_id = gap.id

    # process #1
    await recovery.check_gaps(db_session_factory, Adapter(code), ["BTCUSDT"], HeartbeatState())
    rows = await _status(db_session_factory, market_id)
    assert [(r.id, r.status, r.attempts) for r in rows] == [(gap_id, "failed", 5)]

    # process #2 — brand new adapter and heartbeat state, nothing carried over
    await recovery.check_gaps(db_session_factory, Adapter(code), ["BTCUSDT"], HeartbeatState())
    rows = await _status(db_session_factory, market_id)
    assert [(r.id, r.status, r.attempts) for r in rows] == [(gap_id, "failed", 5)]

    # the durable deadline passes (only the row changes, no code state)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(
            update(IngestionGap)
            .where(IngestionGap.id == gap_id)
            .values(detected_at=now - timedelta(seconds=recovery.FAILED_RETRY_AFTER_S + 10))
        )

    adapter = Adapter(code)
    adapter.candles_response["BTCUSDT"] = [builders.candle("BTCUSDT", stale_minute, exchange=code)]
    await recovery.check_gaps(db_session_factory, adapter, ["BTCUSDT"], HeartbeatState())

    rows = await _status(db_session_factory, market_id)
    assert [(r.id, r.status) for r in rows] == [(gap_id, "recovered")]


async def test_an_event_the_previous_process_never_published_goes_out_at_boot(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The confirmer half: a worker that died between the commit and the
    ``XADD`` leaves a pending row, and the *next* boot's reconciliation is what
    makes that invisible to consumers."""
    code = unique_code()
    await seed_market(db_session_factory, code, "BTCUSDT")
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(delete(OutboxEvent))
    candle = builders.candle("BTCUSDT", exchange=code)

    # the previous process: persisted and queued, then died before publishing
    await persist.flush_batch(db_session_factory, code, [candle])
    assert await redis_client.xrange(Streams.MARKET_CANDLES_CLOSED) == []

    health = OutboxHealth()
    task = asyncio.create_task(
        outbox.run_outbox(db_session_factory, redis_client, health, asyncio.Event())
    )
    try:
        for _ in range(100):
            if await redis_client.xlen(Streams.MARKET_CANDLES_CLOSED):
                break
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert await redis_client.xlen(Streams.MARKET_CANDLES_CLOSED) == 1
    assert health.pending == 0
    assert health.ready(max_pending=outbox.MAX_PENDING, max_lag_s=outbox.MAX_LAG_S) is True
