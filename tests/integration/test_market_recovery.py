"""T1.7 item 3: recovery, against real Postgres and the T1.2 public
``FakeExchangeAdapter`` contract (not the internal minimal test double
``services/market-worker/tests/fakes.FakeAdapter`` that package's own unit
suite uses) -- ``.claude/state/brief-T1.7-tests.md`` item 3 and
``docs/plans/M1.md``'s "Decisão conjunta (Recovery)".

Distinct from ``services/market-worker/tests/test_recovery.py`` (which proves
``check_gaps`` unit-by-unit against a from-scratch history): this file proves
the same contract against a series that already has real, persisted candles
with a HOLE PUNCHED IN THE MIDDLE (delete a candle out of an otherwise
contiguous run), and drives the "5 failures -> failed -> cooldown -> reopen"
lifecycle through direct calls to ``check_gaps`` -- ``FAILED_RETRY_AFTER_S``
(3600s) is exercised by rewriting ``detected_at`` in Postgres, never a real
sleep.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import delete, select, update

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_exchanges.testing.fake_adapter import FakeExchangeAdapter
from hunter_market_worker import recovery
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.persist_rows import flush_batch, load_market_ids
from hunter_market_worker.queues import PersistItem
from hunter_market_worker.universe import refresh_universe

from . import pipeline_builders as b

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.settings import Settings

pytestmark = pytest.mark.integration

EXCHANGE = b.EXCHANGE
PRODUCER = "market-worker@recovery-it:1"


def _symbol() -> str:
    return f"REC{uuid.uuid4().hex[:8].upper()}USDT"


async def _seed(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
    symbol: str,
) -> None:
    adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        markets=[b.market(symbol, symbol.removesuffix("USDT"))],
        ticker=b.ticker(symbol, "1"),
    )
    await refresh_universe(
        worker_session_factory, adapter, worker_redis, worker_settings, producer=PRODUCER
    )


async def _market_id(
    worker_session_factory: async_sessionmaker[AsyncSession], symbol: str
) -> uuid.UUID:
    async with worker_session_factory() as session:
        return (await load_market_ids(session, EXCHANGE, {symbol}))[symbol]


async def test_deleting_a_middle_candle_opens_an_internal_gap_and_rest_backfill_recovers_it(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
) -> None:
    symbol = _symbol()
    await _seed(worker_session_factory, worker_redis, worker_settings, symbol)
    market_id = await _market_id(worker_session_factory, symbol)

    end = align_open_time(utcnow() - recovery.DETECTION_GRACE, Timeframe.M1)
    times = [end - timedelta(minutes=n) for n in (2, 1, 0)]  # contiguous 3-minute run
    candles: list[PersistItem] = [b.candle(symbol, t, is_final=True) for t in times]
    await flush_batch(worker_session_factory, EXCHANGE, candles)

    async with worker_session_factory() as session:
        before = (
            (await session.execute(select(Candle).where(Candle.market_id == market_id)))
            .scalars()
            .all()
        )
        assert len(before) == 3

    middle = times[1]
    async with worker_session_factory() as session:
        await session.execute(
            delete(Candle).where(Candle.market_id == market_id, Candle.open_time == middle)
        )
        await session.commit()

    # REST backfill (the fake adapter) has the missing minute available.
    adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        markets=[b.market(symbol, symbol.removesuffix("USDT"))],
        candles=[b.candle(symbol, middle, is_final=True)],
        server_time=utcnow(),
    )
    heartbeat_state = HeartbeatState()
    await recovery.check_gaps(worker_session_factory, adapter, [symbol], heartbeat_state)

    async with worker_session_factory() as session:
        after = (
            (await session.execute(select(Candle).where(Candle.market_id == market_id)))
            .scalars()
            .all()
        )
        # `check_gaps` also flags this freshly seeded market's much older,
        # genuinely never-ingested history as a separate open gap (T1.3's own
        # documented bootstrap-window limitation, docs/plans/M1.md "T1.3
        # (market-worker)" section) -- this test is only about the ONE-MINUTE
        # hole punched into the otherwise contiguous recent run, so it looks
        # up that specific gap by range rather than assuming it is the only
        # ``ingestion_gaps`` row for this market.
        restored = next(c for c in after if c.open_time == middle)
        assert restored.source == "rest"
        assert sum(1 for c in after if c.open_time == middle) == 1  # not duplicated

        gap = await session.scalar(
            select(IngestionGap).where(
                IngestionGap.market_id == market_id,
                IngestionGap.gap_start == middle,
                IngestionGap.gap_end == middle,
            )
        )
    assert gap is not None
    assert gap.status == "recovered"  # candle insert + status transition, same check_gaps call


async def test_five_failed_backfills_mark_the_gap_failed_and_it_reopens_after_cooldown(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
) -> None:
    symbol = _symbol()
    await _seed(worker_session_factory, worker_redis, worker_settings, symbol)
    market_id = await _market_id(worker_session_factory, symbol)

    # No candles configured at all: every REST backfill attempt comes back
    # empty, so the gap can never satisfy `expected_times <= present`.
    starving_adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        markets=[b.market(symbol, symbol.removesuffix("USDT"))],
        candles=[],
        server_time=utcnow(),
    )
    heartbeat_state = HeartbeatState()
    gap: IngestionGap | None = None
    for attempt in range(1, recovery.MAX_ATTEMPTS + 1):
        await recovery.check_gaps(
            worker_session_factory, starving_adapter, [symbol], heartbeat_state
        )
        async with worker_session_factory() as session:
            gap = await session.scalar(
                select(IngestionGap).where(IngestionGap.market_id == market_id)
            )
        assert gap is not None, f"no gap registered after attempt {attempt}"
        if attempt < recovery.MAX_ATTEMPTS:
            assert gap.status == "open", f"gap closed early after attempt {attempt}"
        assert gap.attempts == attempt

    assert gap is not None  # the loop above always runs (MAX_ATTEMPTS >= 1)
    assert gap.status == "failed"
    assert heartbeat_state.open_gaps == 0  # failed is not counted as "open"

    # Astra's second opinion (T1.7): a failed gap must NOT reopen before its
    # cooldown -- backdate `detected_at` to well INSIDE FAILED_RETRY_AFTER_S
    # (3600s) and confirm one more `check_gaps` cycle leaves it `failed`.
    async with worker_session_factory() as session:
        await session.execute(
            update(IngestionGap)
            .where(IngestionGap.id == gap.id)
            .values(detected_at=utcnow() - timedelta(seconds=60))
        )
        await session.commit()
    await recovery.check_gaps(worker_session_factory, starving_adapter, [symbol], heartbeat_state)
    async with worker_session_factory() as session:
        still_failed = await session.get(IngestionGap, gap.id)
    assert still_failed is not None
    assert still_failed.status == "failed"  # too soon for the cooldown to reopen it

    # Cooldown: backdate detected_at past FAILED_RETRY_AFTER_S -- no sleep.
    async with worker_session_factory() as session:
        await session.execute(
            update(IngestionGap)
            .where(IngestionGap.id == gap.id)
            .values(detected_at=utcnow() - timedelta(seconds=recovery.FAILED_RETRY_AFTER_S + 60))
        )
        await session.commit()

    # This time the backfill succeeds -- failed -> open -> recovered in one
    # call. `recover_registered` only accepts a gap once EVERY expected
    # minute in `[gap_start, gap_end]` is present, so the healed adapter
    # supplies the whole range (`recovery.expected_times`, the same helper
    # `check_gaps` itself uses), not just its two boundary minutes.
    healed_adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        markets=[b.market(symbol, symbol.removesuffix("USDT"))],
        candles=[
            b.candle(symbol, t, is_final=True)
            for t in sorted(recovery.expected_times(gap.gap_start, gap.gap_end))
        ],
        server_time=utcnow(),
    )
    await recovery.check_gaps(worker_session_factory, healed_adapter, [symbol], heartbeat_state)

    async with worker_session_factory() as session:
        reopened = await session.get(IngestionGap, gap.id)
    assert reopened is not None
    assert reopened.status == "recovered"
    # `_reopen_stale_failed` resets `attempts` to 0 on reopen (D6: a fresh
    # try, not a continuation of the exhausted one), then `recover_registered`
    # counts this one attempt.
    assert reopened.attempts == 1
