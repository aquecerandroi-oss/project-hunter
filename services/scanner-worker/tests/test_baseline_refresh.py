"""The hourly refresh: one bucket, and the maturity it may not throw away.

Two properties, both only observable against a real database:

- an hour that closes recomputes **its** bucket and no other. Recomputing all 24
  would be 2.3 M rows a day into an append-only archive;
- a thin live revision must not supersede a mature bootstrap. The projection
  picks the newest admissible revision, with no notion of maturity, so on a fresh
  install the first hourly refresh (60 observations, one distinct day) would take
  the bucket away from a 420-observation bootstrap and then fail the gate — the
  detector would lose the baseline the bootstrap had just given it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import insert, select

from hunter_core.db.models.analysis import FeatureSnapshot
from hunter_core.db.models.analysis_baselines import FeatureBaseline
from hunter_core.db.session import role_session
from hunter_core.domain.enums import BaselineSource
from hunter_indicators.baselines import (
    BaselineCut,
    BaselineKey,
    BaselineRevision,
    Observation,
    SqlBaselineStore,
    compute_revision,
)
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.refresh import closed_hour_before, refresh_hour
from hunter_scanner_worker.registry import MarketRef

from .builders import EXCHANGE
from .db_helpers import seed_market
from .policies import build_policy

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 19, 4, 5, tzinfo=UTC)
CLOSED_HOUR = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)
FEATURE = "return_5m"
FEATURE_VERSION = 1


def _entry(value: str) -> dict[str, Any]:
    return {"value": value, "quality": "ok", "reason": None, "inputs": []}


def _snapshot_rows(market_id: UUID, *, days: range, hours: tuple[int, ...]) -> list[dict[str, Any]]:
    """One row per closed minute — the shape ``rows.feature_snapshot_row`` writes."""
    rows: list[dict[str, Any]] = []
    for day in days:
        for hour in hours:
            for minute in range(60):
                stamp = datetime(2026, 9, day, hour, minute, tzinfo=UTC)
                rows.append(
                    {
                        "market_id": market_id,
                        "ts": stamp,
                        "feature_set_version": "test",
                        "features": {
                            "feature_set_version": "test",
                            "quality_policy_version": "test",
                            "values": {FEATURE: _entry(f"0.00{minute % 9 + 1}")},
                        },
                    }
                )
    return rows


async def _seed_snapshots(factory: Any, rows: list[dict[str, Any]]) -> None:
    async with role_session(factory, db_role="hunter_worker") as session:
        for chunk in range(0, len(rows), 2000):
            await session.execute(insert(FeatureSnapshot).values(rows[chunk : chunk + 2000]))


async def _stored(factory: Any, market_id: UUID) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list(
            (
                await session.execute(
                    select(FeatureBaseline).where(FeatureBaseline.market_id == market_id)
                )
            )
            .scalars()
            .all()
        )


def test_the_closed_hour_is_the_previous_one_never_the_one_still_running() -> None:
    assert closed_hour_before(NOW) == CLOSED_HOUR
    assert closed_hour_before(datetime(2026, 9, 19, 0, 0, 30, tzinfo=UTC)) == datetime(
        2026, 9, 18, 23, 0, tzinfo=UTC
    )


async def test_the_refresh_writes_only_the_bucket_of_the_hour_that_closed(
    db_session_factory: Any, db_engine: Any
) -> None:
    symbol = "REFRESH1USDT"
    market_id = await seed_market(db_session_factory, EXCHANGE, symbol)
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)
    await _seed_snapshots(
        db_session_factory, _snapshot_rows(market_id, days=range(12, 20), hours=(3, 4))
    )
    policy = build_policy()
    cache = BaselineCache(gate=policy.gate)

    outcome = await refresh_hour(
        db_engine,
        [ref],
        cache=cache,
        gate=policy.gate,
        closed_hour=CLOSED_HOUR,
        now=NOW,
    )

    assert outcome.written > 0
    rows = await _stored(db_session_factory, market_id)
    assert {int(row.hour_of_day) for row in rows} == {3}, "only the hour that closed"
    assert {row.source for row in rows} == {BaselineSource.LIVE}
    revision = next(row for row in rows if row.feature == FEATURE)
    assert int(revision.sample_size) == 7 * 60
    assert int(revision.distinct_days) == 7
    assert revision.window_end == CLOSED_HOUR + timedelta(hours=1)


async def test_an_immature_live_revision_does_not_supersede_a_usable_bootstrap(
    db_session_factory: Any, db_engine: Any
) -> None:
    symbol = "REFRESH2USDT"
    market_id = await seed_market(db_session_factory, EXCHANGE, symbol)
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)
    policy = build_policy()
    boot_end = CLOSED_HOUR
    boot_start = boot_end - timedelta(days=7)
    mature = compute_revision(
        key=BaselineKey(market_id=market_id, feature=FEATURE, hour_of_day=3),
        feature_version=FEATURE_VERSION,
        source=BaselineSource.BOOTSTRAP,
        window_start=boot_start,
        window_end=boot_end,
        available_at=boot_end + timedelta(minutes=10),
        observations=[
            Observation(
                ts=boot_start + timedelta(days=day, minutes=minute),
                value=Decimal("0.001") * (minute % 11 + 1),
            )
            for day in range(7)
            for minute in range(60)
        ],
        expected_size=420,
    )
    assert isinstance(mature, BaselineRevision), "420 observations is a revision, not a refusal"
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await SqlBaselineStore(await session.connection()).append([mature])
    cache = BaselineCache(gate=policy.gate)
    async with db_engine.begin() as connection:
        await cache.refresh(connection, [ref], now=NOW)
    assert cache.median_of(market_id, FEATURE, 3) is not None, "the bootstrap must be usable"

    # One single day of live snapshots: 60 observations, one distinct day.
    await _seed_snapshots(
        db_session_factory, _snapshot_rows(market_id, days=range(19, 20), hours=(3,))
    )

    outcome = await refresh_hour(
        db_engine,
        [ref],
        cache=cache,
        gate=policy.gate,
        closed_hour=CLOSED_HOUR,
        now=NOW,
    )

    assert outcome.withheld == 1
    assert outcome.withheld_features == {FEATURE: 1}
    assert outcome.written == 0
    sources = {row.source for row in await _stored(db_session_factory, market_id)}
    assert sources == {BaselineSource.BOOTSTRAP}, "the thin live revision was not published"
    # And the projection still answers with the mature one.
    observed = CLOSED_HOUR + timedelta(minutes=30)
    lookup = cache.projection(market_id, BaselineCut(as_of=NOW, observation_ts=observed)).resolve(
        market_id, FEATURE, observed, feature_version=FEATURE_VERSION
    )
    assert lookup.usable is True
    assert lookup.revision is not None
    assert lookup.revision.source is BaselineSource.BOOTSTRAP


async def test_a_bootstrapped_market_is_usable_without_waiting_for_the_next_hour(
    db_session_factory: Any, db_engine: Any
) -> None:
    """The detectors read the cache, not the archive. A bootstrap that landed at
    10:05 and only entered the projection at 11:00 would leave the market
    unscoreable for the 55 minutes in which its baseline already existed."""
    from hunter_scanner_worker.refresh import reload_market

    symbol = "RELOADUSDT"
    market_id = await seed_market(db_session_factory, EXCHANGE, symbol)
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)
    policy = build_policy()
    cache = BaselineCache(gate=policy.gate)
    async with db_engine.begin() as connection:
        await cache.refresh(connection, [ref], now=NOW)
    assert cache.median_of(market_id, FEATURE, 3) is None

    boot_end = CLOSED_HOUR
    revision = compute_revision(
        key=BaselineKey(market_id=market_id, feature=FEATURE, hour_of_day=3),
        feature_version=FEATURE_VERSION,
        source=BaselineSource.BOOTSTRAP,
        window_start=boot_end - timedelta(days=7),
        window_end=boot_end,
        available_at=boot_end + timedelta(minutes=5),
        observations=[
            Observation(
                ts=boot_end - timedelta(days=7) + timedelta(days=day, minutes=minute),
                value=Decimal("0.001") * (minute % 11 + 1),
            )
            for day in range(7)
            for minute in range(60)
        ],
        expected_size=420,
    )
    assert isinstance(revision, BaselineRevision)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await SqlBaselineStore(await session.connection()).append([revision])

    loaded = await reload_market(db_engine, cache, ref, now=NOW)

    assert loaded == 1
    assert cache.median_of(market_id, FEATURE, 3) is not None


async def test_an_immature_bootstrap_does_not_demote_a_usable_baseline(
    db_session_factory: Any, db_engine: Any
) -> None:
    """The maturity policy belongs to the *publication*, not to one source.

    A re-run over a window with holes (the ledger was lost, or 24 h elapsed)
    produces a non-empty bucket below the gate. Published, it would win the
    projection on ``available_at`` and take the market's only usable baseline
    away — and ``reload_market`` would make the loss immediate.
    """
    from hunter_scanner_worker.refresh import admissible

    symbol = "DEMOTEUSDT"
    market_id = await seed_market(db_session_factory, EXCHANGE, symbol)
    ref = MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)
    policy = build_policy()
    boot_end = CLOSED_HOUR
    mature = compute_revision(
        key=BaselineKey(market_id=market_id, feature=FEATURE, hour_of_day=3),
        feature_version=FEATURE_VERSION,
        source=BaselineSource.BOOTSTRAP,
        window_start=boot_end - timedelta(days=7),
        window_end=boot_end,
        available_at=boot_end + timedelta(minutes=5),
        observations=[
            Observation(
                ts=boot_end - timedelta(days=7) + timedelta(days=day, minutes=minute),
                value=Decimal("0.001") * (minute % 11 + 1),
            )
            for day in range(7)
            for minute in range(60)
        ],
        expected_size=420,
    )
    assert isinstance(mature, BaselineRevision)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await SqlBaselineStore(await session.connection()).append([mature])
    cache = BaselineCache(gate=policy.gate)
    async with db_engine.begin() as connection:
        await cache.refresh(connection, [ref], now=NOW)
    assert cache.median_of(market_id, FEATURE, 3) is not None

    thin = compute_revision(
        key=BaselineKey(market_id=market_id, feature=FEATURE, hour_of_day=3),
        feature_version=FEATURE_VERSION,
        source=BaselineSource.BOOTSTRAP,
        window_start=boot_end - timedelta(days=7),
        window_end=boot_end + timedelta(minutes=1),
        available_at=NOW,
        observations=[
            Observation(
                ts=boot_end - timedelta(days=1) + timedelta(minutes=m), value=Decimal("0.002")
            )
            for m in range(30)
        ],
        expected_size=420,
    )
    assert isinstance(thin, BaselineRevision)

    keep, withheld = admissible([thin], cache, policy.gate)

    assert keep == []
    assert withheld == [thin]
