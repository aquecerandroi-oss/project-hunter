"""The baseline bootstrap over persisted candles, against a real Postgres.

Why testcontainers: the three properties being proved only exist in a database.
``uq_feature_baselines_revision`` is what makes a second run a no-op; the
``sample_size <= expected_size`` CHECK is what a half-open window would trip; and
"which markets still need a bootstrap" is a question about rows, not about a
process — a restart has to answer it from the archive, not from memory.

**The fixture is synthetic and labelled as such.** ``synthetic_minutes`` builds a
deterministic pseudo-random walk (fixed seed, no market data) so the medians and
MADs below are reproducible; nothing here is recorded from an exchange.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import func, insert, select

from hunter_core.db.models.analysis_baselines import FeatureBaseline
from hunter_core.db.models.market_data import Candle
from hunter_core.db.session import role_session
from hunter_core.domain.enums import BaselineSource, Timeframe
from hunter_indicators.baselines import SqlBaselineStore
from hunter_scanner_worker.backfill import BackfillRequester
from hunter_scanner_worker.bootstrap import BootstrapSettings, missing_runs, window_for
from hunter_scanner_worker.registry import MarketRef
from hunter_scanner_worker.replay_io import run_bootstrap

from .builders import EXCHANGE, FakeHotState
from .db_helpers import seed_market
from .policies import build_policy

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 20, 0, 30, tzinfo=UTC)
"""Deliberately inside the partitions ``0001`` creates (2026-09 .. 2026-12)."""

TEST_BUFFER_MINUTES = 400
"""Production replays with the hot state's 1500-minute ring. The tests use 400
so a 10 080-cut replay stays around a minute of CPU; the three features that
need more than 400 minutes of history (``relative_volume_1h``,
``distance_from_24h_high/low``) then have no bucket at all, and *that* is
asserted too — an excluded feature must be visible as a rejection, never as a
number computed from a short window."""


def synthetic_minutes(start: datetime, count: int, *, seed: int = 20260920) -> list[dict[str, Any]]:
    """A deterministic random walk — labelled fixture, not recorded market data."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    price = 100.0
    for index in range(count):
        price = max(1.0, price * (1.0 + rng.gauss(0.0, 0.0009)))
        high = price * (1.0 + abs(rng.gauss(0.0, 0.0006)))
        low = price * (1.0 - abs(rng.gauss(0.0, 0.0006)))
        volume = round(abs(rng.gauss(120.0, 35.0)) + 1.0, 4)
        rows.append(
            {
                "open_time": start + timedelta(minutes=index),
                "open": Decimal(f"{price:.4f}"),
                "high": Decimal(f"{high:.4f}"),
                "low": Decimal(f"{low:.4f}"),
                "close": Decimal(f"{price:.4f}"),
                "volume": Decimal(f"{volume:.4f}"),
                "quote_volume": Decimal(f"{volume * price:.4f}"),
                "trade_count": 40 + index % 23,
                "taker_buy_volume": Decimal(f"{volume / 2:.4f}"),
            }
        )
    return rows


async def _insert_candles(
    factory: Any, market_id: UUID, rows: list[dict[str, Any]], *, skip: set[datetime] | None = None
) -> None:
    payload = [
        {"market_id": market_id, "timeframe": Timeframe.M1, "is_final": True, **row}
        for row in rows
        if skip is None or row["open_time"] not in skip
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        for chunk in range(0, len(payload), 2000):
            await session.execute(insert(Candle).values(payload[chunk : chunk + 2000]))


async def _seed_window(
    factory: Any,
    symbol: str,
    settings: BootstrapSettings,
    *,
    skip: set[datetime] | None = None,
    from_minute: int = 0,
) -> tuple[UUID, MarketRef]:
    """Candles covering the window **and** its warm-up prefix."""
    market_id = await seed_market(factory, EXCHANGE, symbol)
    window = window_for(NOW, days=settings.window_days)
    first = window.start - timedelta(minutes=settings.buffer_minutes)
    minutes = int((window.end - first).total_seconds() // 60)
    rows = synthetic_minutes(first, minutes)[from_minute:]
    await _insert_candles(factory, market_id, rows, skip=skip)
    return market_id, MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol)


async def _count(factory: Any, market_id: UUID) -> int:
    async with role_session(factory, db_role="hunter_worker") as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(FeatureBaseline)
                .where(FeatureBaseline.market_id == market_id)
            )
            or 0
        )


def test_the_window_is_the_seven_days_before_the_hour_that_just_closed() -> None:
    window = window_for(NOW, days=7)

    assert window.end == datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
    assert window.start == datetime(2026, 9, 13, 0, 0, tzinfo=UTC)
    # Half-open: the minute that opens the next window would otherwise be
    # counted twice and trip ``sample_size <= expected_size``.
    cuts = list(window.cuts())
    assert len(cuts) == 7 * 24 * 60
    assert cuts[0] == window.start
    assert cuts[-1] == window.end - timedelta(minutes=1)


def test_every_hole_is_reported_not_only_the_ones_longer_than_five_minutes() -> None:
    start = datetime(2026, 9, 13, tzinfo=UTC)
    rows = synthetic_minutes(start, 120)
    hole = {start + timedelta(minutes=40)}
    candles = [row for row in rows if row["open_time"] not in hole]

    runs = missing_runs(
        [row["open_time"] for row in candles], start=start, end=start + timedelta(minutes=120)
    )

    # One missing minute is not a rounding error: ``relative_volume_1h`` reads
    # 1440 prior minutes, so a single hole costs a whole day of observations
    # (Astra, T2.5b design review, must-fix 4).
    assert runs == [(start + timedelta(minutes=40), start + timedelta(minutes=41))]


async def test_seven_synthetic_days_produce_the_expected_revisions_and_are_idempotent(
    db_session_factory: Any, redis_client: Any
) -> None:
    settings = BootstrapSettings(window_days=7, buffer_minutes=TEST_BUFFER_MINUTES, duty=1.0)
    market_id, ref = await _seed_window(db_session_factory, "BOOTFULLUSDT", settings)

    outcome = await run_bootstrap(
        db_session_factory,
        redis_client,
        BackfillRequester("test"),
        ref,
        window=window_for(NOW, days=settings.window_days),
        settings=settings,
        now=NOW,
    )

    assert outcome.cuts == 7 * 24 * 60
    assert outcome.complete is True
    assert outcome.gaps == ()
    produced = {revision.key.feature for revision in outcome.revisions}
    # Twelve of the fifteen candle-reproducible features; the other three need
    # more history than this test's buffer and must be *absent with a reason*.
    assert "return_5m" in produced and "atr_14_pct" in produced
    for starved in ("relative_volume_1h", "distance_from_24h_high", "distance_from_24h_low"):
        assert starved not in produced
        assert outcome.rejections[starved]["warmup"] > 0

    hours = sorted(
        revision.key.hour_of_day
        for revision in outcome.revisions
        if revision.key.feature == "return_5m"
    )
    assert hours == list(range(24)), "one bucket per UTC hour, every hour"
    sample = next(
        revision
        for revision in outcome.revisions
        if revision.key.feature == "return_5m" and revision.key.hour_of_day == 3
    )
    assert sample.sample_size == 7 * 60
    assert sample.distinct_days == 7
    assert sample.expected_size == 7 * 60
    assert sample.source is BaselineSource.BOOTSTRAP
    assert sample.mad > 0
    gate = build_policy().gate
    assert sample.distinct_days >= gate.min_distinct_days
    assert sample.sample_size >= gate.min_valid_observations

    stored = await _count(db_session_factory, market_id)
    assert stored == len(outcome.revisions) > 0

    # Idempotent by ``input_fingerprint``: the same computation written again is
    # the same row, not a second one. Re-appending the revisions the replay
    # produced exercises exactly the ``ON CONFLICT`` path a retry takes, without
    # paying for a second ten-thousand-cut replay.
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        again = await SqlBaselineStore(await session.connection()).append(list(outcome.revisions))
    assert len(again) == len(outcome.revisions)
    assert await _count(db_session_factory, market_id) == stored


async def test_a_restart_in_the_middle_of_the_bootstrap_resumes_where_it_stopped(
    db_session_factory: Any, redis_client: Any
) -> None:
    from hunter_scanner_worker.ledger import BootstrapLedger, pending_markets

    settings = BootstrapSettings(window_days=1, buffer_minutes=60, duty=1.0)
    window = window_for(NOW, days=settings.window_days)
    _, first = await _seed_window(db_session_factory, "RESUMEAUSDT", settings)
    _, second = await _seed_window(db_session_factory, "RESUMEBUSDT", settings)
    ledger = BootstrapLedger(EXCHANGE)
    refs = [first, second]

    pending = await pending_markets(
        db_session_factory, redis_client, refs, window=window, settings=settings, now=NOW
    )
    assert [ref.symbol for ref in pending] == ["RESUMEAUSDT", "RESUMEBUSDT"]

    outcome = await run_bootstrap(
        db_session_factory,
        redis_client,
        BackfillRequester("test"),
        pending[0],
        window=window,
        settings=settings,
        now=NOW,
    )
    await ledger.record(redis_client, outcome, settings=settings, now=NOW)

    # The process dies here. A new one asks the same question of the archive and
    # the ledger, and must not redo the market that is already written.
    resumed = await pending_markets(
        db_session_factory, redis_client, refs, window=window, settings=settings, now=NOW
    )
    assert [ref.symbol for ref in resumed] == ["RESUMEBUSDT"]


async def test_missing_history_asks_for_one_backfill_per_hole_and_never_calls_rest(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def _forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the scanner must never call an exchange (docs/plans/M2.md, REST)")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _forbidden)

    settings = BootstrapSettings(window_days=1, buffer_minutes=60, duty=1.0)
    window = window_for(NOW, days=settings.window_days)
    hole_start = window.start + timedelta(hours=3)
    skip = {hole_start + timedelta(minutes=offset) for offset in range(20)}
    _, ref = await _seed_window(db_session_factory, "BOOTGAPUSDT", settings, skip=skip)
    requester = BackfillRequester("test")
    stream = FakeHotState()
    # The fake speaks the three commands ``publish`` uses; nothing here may
    # reach a real Redis, and nothing may reach an exchange either.
    fake_redis = cast("Any", stream)

    outcome = await run_bootstrap(
        db_session_factory,
        fake_redis,
        requester,
        ref,
        window=window,
        settings=settings,
        now=NOW,
    )

    assert outcome.complete is False
    assert outcome.reason == "history_incomplete"
    assert outcome.gaps == ((hole_start, hole_start + timedelta(minutes=20)),)
    published = stream.streams.get("market.backfill.requested", [])
    assert len(published) == 1

    # Asked once per hole: a second pass over the same window must not queue the
    # same repair again.
    await run_bootstrap(
        db_session_factory,
        fake_redis,
        requester,
        ref,
        window=window,
        settings=settings,
        now=NOW + timedelta(minutes=1),
    )
    assert len(stream.streams.get("market.backfill.requested", [])) == 1


async def test_slicing_the_replay_does_not_change_a_single_number(
    db_session_factory: Any,
) -> None:
    """The job survives between slices, so the ATR recursion is never re-anchored.

    This is the property that makes the cooperative budget safe to tune: whether
    a market is replayed in one pass or in forty, the revisions it produces are
    identical byte for byte (Astra, T2.5b design review, must-fix 5 — a recreated
    generator would restart Wilder's recursion from a different anchor).
    """
    from hunter_scanner_worker.replay_io import prepare_job

    settings = BootstrapSettings(window_days=1, buffer_minutes=60, duty=1.0, slice_s=0.001)
    window = window_for(NOW, days=settings.window_days)
    _, ref = await _seed_window(db_session_factory, "SLICEDUSDT", settings)

    fingerprints: list[tuple[str, ...]] = []
    for budget in (None, 0.002):
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            job = await prepare_job(session, ref, window=window, settings=settings, now=NOW)
        slices = 0
        while not await job.run_slice(budget):
            slices += 1
            assert slices < 10_000, "the slice budget has to make progress"
        assert job.cuts_done == 24 * 60
        if budget is not None:
            assert slices > 1, "the tiny budget must actually have interrupted the replay"
        fingerprints.append(
            tuple(revision.input_fingerprint for revision in job.revisions(available_at=NOW))
        )

    assert fingerprints[0] == fingerprints[1]


async def test_the_cut_counter_counts_each_minute_once_however_many_slices(
    db_session_factory: Any,
) -> None:
    """``scanner_bootstrap_cuts_total`` is the unit of the bootstrap's cost, so a
    market replayed in forty slices must not read as forty markets: incrementing
    a monotonic counter by the *running total* once per slice multiplies it."""
    from hunter_scanner_worker.metrics import scanner_bootstrap_cuts_total
    from hunter_scanner_worker.replay_io import prepare_job

    settings = BootstrapSettings(window_days=1, buffer_minutes=60, duty=1.0, slice_s=0.001)
    window = window_for(NOW, days=settings.window_days)
    _, ref = await _seed_window(db_session_factory, "COUNTEDUSDT", settings)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        job = await prepare_job(session, ref, window=window, settings=settings, now=NOW)

    def counted() -> float:
        for metric in scanner_bootstrap_cuts_total.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    return float(sample.value)
        raise AssertionError("the counter must expose a _total sample")

    before = counted()
    slices = 0
    while not await job.run_slice(0.002):
        slices += 1
    after = counted()

    assert slices > 1, "the tiny budget must actually have interrupted the replay"
    assert after - before == 24 * 60 == job.cuts_done


async def test_a_roster_change_clears_a_backoff_earned_by_the_previous_one(
    db_session_factory: Any, redis_client: Any
) -> None:
    """A seven-day backoff belongs to the features that earned it.

    Without this, adding a feature would leave every market that had ever ended
    incomplete dismissed for up to a week — with the new feature's buckets never
    computed at all.
    """
    import dataclasses

    from hunter_scanner_worker.bootstrap import BootstrapOutcome
    from hunter_scanner_worker.ledger import BootstrapLedger, pending_markets

    settings = BootstrapSettings(window_days=1, buffer_minutes=60, duty=1.0)
    window = window_for(NOW, days=settings.window_days)
    _, ref = await _seed_window(db_session_factory, "ROSTERUSDT", settings)
    ledger = BootstrapLedger(EXCHANGE)
    await ledger.record(
        redis_client,
        BootstrapOutcome(ref=ref, window=window, complete=False, reason="history_incomplete"),
        settings=settings,
        now=NOW,
    )

    still_waiting = await pending_markets(
        db_session_factory,
        redis_client,
        [ref],
        window=window,
        settings=settings,
        now=NOW,
        ledger=ledger,
    )
    assert still_waiting == [], "the backoff of its own roster still holds"

    other = dataclasses.replace(settings, window_days=2)
    resumed = await pending_markets(
        db_session_factory,
        redis_client,
        [ref],
        window=window,
        settings=other,
        now=NOW,
        ledger=ledger,
    )
    assert [item.symbol for item in resumed] == ["ROSTERUSDT"]


def test_the_scheduler_walks_the_hours_it_missed_instead_of_jumping() -> None:
    """A refresh that failed during hour 10 must not abandon hour 09 for a day."""
    from datetime import timedelta as delta

    from hunter_scanner_worker.baseline_runner import due_hour, sleep_for

    now = datetime(2026, 9, 20, 11, 2, tzinfo=UTC)
    assert due_hour(datetime(2026, 9, 20, 8, 0, tzinfo=UTC), now) == datetime(
        2026, 9, 20, 9, 0, tzinfo=UTC
    )
    # Already caught up: the last closed hour, never one in the future.
    assert due_hour(datetime(2026, 9, 20, 10, 0, tzinfo=UTC), now) == datetime(
        2026, 9, 20, 10, 0, tzinfo=UTC
    )
    assert due_hour(None, now) == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    # And a flat five-minute sleep taken one second before the turn would start
    # the next refresh almost five minutes late.
    assert sleep_for(datetime(2026, 9, 20, 10, 59, 59, tzinfo=UTC), 300.0) <= 3.0
    assert sleep_for(datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC), 300.0) == 300.0
    del delta
