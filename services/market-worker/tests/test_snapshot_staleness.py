"""H5 (ticker half) + D9: the ticker hash owns the staleness of the ticker-derived
snapshot fields, and a row whose every observable field was gated away is skipped
rather than written as an all-NULL row that ON CONFLICT DO NOTHING makes permanent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import select

from hunter_core.db.models.market_data import MarketSnapshot
from hunter_core.db.session import role_session
from hunter_core.observability import (
    market_snapshot_skipped_no_data_total,
    market_snapshot_stale_fields_total,
)
from hunter_core.redis import keys
from hunter_core.settings import Settings
from hunter_market_worker import sampling

from .db_helpers import seed_market
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

TICKER_GATED_FIELDS = ("price", "bid", "ask", "spread_pct", "volume_24h", "quote_volume_24h")


async def _write_hashes(
    redis_client: Any, exchange_code: str, ticker: dict[str, str], deriv: dict[str, str]
) -> None:
    if ticker:
        await redis_client.hset(keys.ticker(exchange_code, "BTCUSDT"), mapping=ticker)
    if deriv:
        await redis_client.hset(keys.derivatives(exchange_code, "BTCUSDT"), mapping=deriv)


def _stale_field_counters() -> dict[str, Any]:
    return {
        field: cast(Any, market_snapshot_stale_fields_total.labels(field=field))
        for field in TICKER_GATED_FIELDS
    }


def test_staleness_is_measured_from_the_observation_instant_not_the_aligned_minute() -> None:
    """A round that reads the hashes at 12:00:40 must not grant the ticker 40 s
    of extra slack just because the row is keyed on the aligned minute
    (12:00:00): against the bucket the age would be -5 s and look fresh."""
    observed_at = datetime(2026, 1, 1, 12, 0, 40, tzinfo=UTC)
    ticker = {"ts": datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC).isoformat()}
    row: dict[str, Any] = {field: Decimal("1") for field in TICKER_GATED_FIELDS}

    apply_staleness = sampling._apply_staleness  # pyright: ignore[reportPrivateUsage]
    survived = apply_staleness(row, ticker, {}, observed_at, 10)

    assert survived is False
    assert all(row[field] is None for field in TICKER_GATED_FIELDS)


async def test_snapshot_drops_stale_ticker_fields_and_keeps_the_fresh_deriv(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    settings = Settings(market_stale_after_s=10)
    # built from the real clock, not the aligned minute: write_snapshots
    # measures freshness against the instant it read the hashes.
    observed_at = datetime.now(UTC)
    stale_ts = (observed_at - timedelta(seconds=settings.market_stale_after_s + 5)).isoformat()

    await _write_hashes(
        redis_client,
        exchange_code,
        {
            "last": "100",
            "bid": "99",
            "ask": "101",
            "volume_24h": "5",
            "quote_volume_24h": "500",
            "ts": stale_ts,  # the ticker hash itself is stale -> all six drop
        },
        {"open_interest": "42", "open_interest_value": "4200", "oi_ts": observed_at.isoformat()},
    )
    counters = _stale_field_counters()
    before = {field: counter._value.get() for field, counter in counters.items()}

    await sampling.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["BTCUSDT"], settings
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is not None
    assert (row.price, row.bid, row.ask) == (None, None, None)
    assert (row.spread_pct, row.volume_24h, row.quote_volume_24h) == (None, None, None)
    assert row.open_interest == 42
    for field, counter in counters.items():
        assert counter._value.get() == before[field] + 1, field


async def test_snapshot_keeps_the_fresh_ticker_when_the_mark_is_stale(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    settings = Settings(market_stale_after_s=10)
    # built from the real clock, not the aligned minute: write_snapshots
    # measures freshness against the instant it read the hashes.
    observed_at = datetime.now(UTC)
    stale_ts = (observed_at - timedelta(seconds=settings.market_stale_after_s + 5)).isoformat()

    await _write_hashes(
        redis_client,
        exchange_code,
        {"last": "100", "bid": "99", "ask": "101", "ts": observed_at.isoformat()},
        {"mark_price": "101", "index_price": "100.5", "mark_ts": stale_ts},
    )

    await sampling.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["BTCUSDT"], settings
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is not None
    assert row.price == 100
    assert row.spread_pct == Decimal("0.02")
    assert row.mark_price is None
    assert row.index_price is None


async def test_snapshot_row_is_skipped_when_every_field_is_gated_as_stale(
    db_session_factory: Any, redis_client: Any
) -> None:
    """D9: an all-NULL row would be made permanent by ON CONFLICT DO NOTHING,
    so "nothing fresh to observe" is a skip plus a counter, not a row."""
    exchange_code = unique_code()
    market_id = await seed_market(db_session_factory, exchange_code, "BTCUSDT")
    settings = Settings(market_stale_after_s=10)
    # built from the real clock, not the aligned minute: write_snapshots
    # measures freshness against the instant it read the hashes.
    observed_at = datetime.now(UTC)
    stale_ts = (observed_at - timedelta(seconds=settings.market_stale_after_s + 5)).isoformat()

    await _write_hashes(
        redis_client,
        exchange_code,
        {"last": "100", "bid": "99", "ask": "101", "ts": stale_ts},
        {"mark_price": "101", "mark_ts": stale_ts},
    )
    metric = cast(Any, market_snapshot_skipped_no_data_total)
    before = metric._value.get()

    await sampling.write_snapshots(
        db_session_factory, redis_client, exchange_code, ["BTCUSDT"], settings
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        )
    assert row is None
    assert metric._value.get() == before + 1
