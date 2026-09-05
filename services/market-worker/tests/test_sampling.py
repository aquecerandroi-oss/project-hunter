"""Snapshot field staleness, spread_pct convention, UTC-aligned sampling
boundaries and per-cycle OI buckets — fix brief T1.3-A2 (H5, D1, M5, D8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import select

from hunter_core.db.models.market_data import MarketSnapshot, OpenInterestHistory
from hunter_core.db.session import role_session
from hunter_core.observability import (
    market_sampling_bucket_skipped_total,
    market_snapshot_stale_fields_total,
)
from hunter_core.redis import keys
from hunter_core.settings import Settings
from hunter_market_worker import persist, sampling
from hunter_market_worker.persist_rows import oi_bucket
from hunter_market_worker.queues import PersistQueues

from . import builders
from .db_helpers import seed_market
from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


# ---- D1: spread_pct stays a FRACTION -------------------------------------


def test_spread_pct_is_a_fraction_not_a_percentage() -> None:
    """bid 99 / ask 101 -> 0.02, never 2 (docs/DATABASE.md §4, NUMERIC(9,6))."""
    result = sampling._spread_pct(Decimal("99"), Decimal("101"))  # pyright: ignore[reportPrivateUsage]
    assert result == Decimal("0.02")


# ---- H5: per-field staleness ----------------------------------------------


async def test_snapshot_drops_only_the_stale_field_and_counts_it(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    settings = Settings(market_stale_after_s=10)
    observed_at = datetime.now(UTC)
    fresh_ts = observed_at.isoformat()
    stale_ts = (observed_at - timedelta(seconds=settings.market_stale_after_s + 5)).isoformat()

    await redis_client.hset(
        keys.derivatives(exchange_code, "BTCUSDT"),
        mapping={
            "mark_price": "101",
            "index_price": "100.5",
            "mark_ts": stale_ts,  # older than the threshold -> dropped
            "open_interest": "42",
            "open_interest_value": "4200",
            "oi_ts": fresh_ts,  # fresh -> kept
        },
    )
    counter = cast(Any, market_snapshot_stale_fields_total.labels(field="mark_price"))
    before = counter._value.get()

    await sampling.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["BTCUSDT"], settings
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is not None
    assert row.mark_price is None
    assert row.index_price is None
    assert row.open_interest == 42
    assert counter._value.get() == before + 1  # pyright: ignore[reportPrivateUsage]


# ---- M5: UTC-aligned sampling boundaries -----------------------------------


def test_advance_schedule_uses_the_grid_not_interval_after_finish() -> None:
    previous_boundary = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    interval_s = 60
    # work overran two full minutes past the boundary that should have
    # followed (12:01:00)
    finished_at = datetime(2026, 1, 1, 12, 2, 30, tzinfo=UTC)

    metric = cast(Any, market_sampling_bucket_skipped_total.labels(loop="snapshot"))
    before = metric._value.get()

    advance = sampling._advance_schedule  # pyright: ignore[reportPrivateUsage]
    next_boundary = advance(previous_boundary, finished_at, interval_s, "snapshot")

    # next boundary strictly after finished_at, aligned to the grid
    assert next_boundary == datetime(2026, 1, 1, 12, 3, 0, tzinfo=UTC)
    assert metric._value.get() == before + 1  # pyright: ignore[reportPrivateUsage]


def test_advance_schedule_no_skip_when_work_finishes_before_next_boundary() -> None:
    previous_boundary = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    finished_at = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)

    metric = cast(Any, market_sampling_bucket_skipped_total.labels(loop="snapshot"))
    before = metric._value.get()

    advance = sampling._advance_schedule  # pyright: ignore[reportPrivateUsage]
    next_boundary = advance(previous_boundary, finished_at, 60, "snapshot")

    assert next_boundary == datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC)
    assert metric._value.get() == before


# ---- D8: the OI bucket is derived once per cycle, not per reading ---------


def test_oi_rows_share_one_bucket_regardless_of_each_readings_own_ts() -> None:
    oi_a = builders.open_interest("BTCUSDT", "10", ts=datetime(2026, 1, 1, 12, 4, 59, tzinfo=UTC))
    oi_b = builders.open_interest("ETHUSDT", "20", ts=datetime(2026, 1, 1, 12, 5, 1, tzinfo=UTC))
    cycle_bucket = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    market_ids = {"BTCUSDT": "m1", "ETHUSDT": "m2"}

    oi_rows = sampling._oi_rows  # pyright: ignore[reportPrivateUsage]
    rows = oi_rows([oi_a, oi_b], market_ids, cycle_bucket)

    assert {row["ts"] for row in rows} == {cycle_bucket}


def test_oi_rows_next_cycle_uses_the_next_bucket() -> None:
    oi = builders.open_interest("BTCUSDT", "10")
    first_bucket = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    second_bucket = datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)
    market_ids = {"BTCUSDT": "m1"}

    oi_rows = sampling._oi_rows  # pyright: ignore[reportPrivateUsage]
    first = oi_rows([oi], market_ids, first_bucket)
    second = oi_rows([oi], market_ids, second_bucket)

    assert first[0]["ts"] == first_bucket
    assert second[0]["ts"] == second_bucket
    assert first[0]["ts"] != second[0]["ts"]


# ---- D8 (production path): the cycle bucket travels through the queue -----


async def test_queued_oi_cycle_persists_every_reading_in_the_single_cycle_bucket(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``main.py`` always passes ``queues``, so the cycle bucket must survive
    the queue. Otherwise ``upsert_open_interest`` re-derives it from each
    reading own ``ts`` and one round straddling a 5-minute boundary lands on
    two different buckets — the irregular grid D8 exists to kill."""
    exchange_code = unique_code()
    market_ids = {
        symbol: await seed_market(db_session_factory, exchange_code, symbol)
        for symbol in ("BTCUSDT", "ETHUSDT")
    }
    bucket = oi_bucket(datetime.now(UTC))
    cycle_start = bucket + timedelta(minutes=4, seconds=59)
    # The clock crosses the boundary after the cycle started: only the bucket
    # taken once at the top of the round may be used, so a regression that
    # re-read the wall clock per reading would land on the next bucket too.
    ticks = iter([cycle_start])

    def _clock() -> datetime:
        return next(ticks, cycle_start + timedelta(minutes=2))

    monkeypatch.setattr(sampling, "utcnow", _clock)

    adapter = FakeAdapter(code=exchange_code)
    adapter.open_interests["BTCUSDT"] = builders.open_interest(
        "BTCUSDT", "10", ts=cycle_start, exchange=exchange_code
    )
    adapter.open_interests["ETHUSDT"] = builders.open_interest(
        "ETHUSDT", "20", ts=bucket + timedelta(minutes=5, seconds=1), exchange=exchange_code
    )
    queues = PersistQueues()
    runtime: Any = FakeRuntime(redis=redis_client)

    run_cycle = sampling._run_oi_cycle  # pyright: ignore[reportPrivateUsage]
    await run_cycle(
        db_session_factory, redis_client, adapter, ["BTCUSDT", "ETHUSDT"], runtime, queues
    )

    batch = [queues.events.get_nowait() for _ in range(queues.events.qsize())]
    assert len(batch) == 2
    await persist.flush_batch(db_session_factory, exchange_code, batch)

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = list(
            await session.scalars(
                select(OpenInterestHistory).where(
                    OpenInterestHistory.market_id.in_(list(market_ids.values()))
                )
            )
        )
    assert len(rows) == 2
    assert {row.ts for row in rows} == {bucket}


async def test_ws_open_interest_without_a_cycle_still_buckets_from_its_own_ts(
    db_session_factory: Any,
) -> None:
    """The WS path (``ingest.py``) has no polling cycle: a bare
    ``NormalizedOpenInterest`` keeps deriving its bucket from its own ``ts``."""
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    ts = oi_bucket(datetime.now(UTC)) + timedelta(minutes=3, seconds=17)
    oi = builders.open_interest("BTCUSDT", "7", ts=ts, exchange=exchange_code)

    await persist.flush_batch(db_session_factory, exchange_code, [oi])

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(OpenInterestHistory).where(OpenInterestHistory.market_id == market_id)
        )
    assert row is not None
    assert row.ts == oi_bucket(ts)
    assert row.open_interest == Decimal("7")
