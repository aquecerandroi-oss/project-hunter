"""The hourly beta producer, against a real database.

Everything here is only observable against Postgres, because the whole point of
the job is the *row*: ``market_betas`` decides which revision is in force with a
partial unique index, refuses an edit with a trigger, and is what the execution
worker reads through ``bridge_universe.current_beta``. A fake session would
prove the arithmetic — which ``packages/indicators`` already proves, with known
expected values — and none of the things that can actually go wrong here.

The spec is **compressed on purpose** (``window_days=1``, ``min_contiguous_days=1``
-> 24 hourly bars instead of 480): thirty days of one-minute candles is 43 200
rows per market, and seeding two markets of those per test buys nothing the
24-bar window does not already show. It also exercises the ``beta_v1+<digest>``
naming of an overridden parameter set, which the production default never does.

The synthetic series is built so the expected numbers are exact rather than
"whatever the estimator said": the asset moves exactly twice the reference in
the two bars where either of them moves at all, and every other bar is flat, so
every price stays an integer and ``beta = 2``, ``alpha = 0``, ``R^2 = 1`` hold to
the storage quantum.

Each test seeds its **own** reference and asset markets. The database is shared
by the module (one container, one schema), and a shared ``BTCUSDT`` would mean
one test's candles deciding the next test's answer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import insert, text

from hunter_core.db.models.market_data import Candle
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_indicators.beta import BetaSpec, beta_version
from hunter_scanner_worker.beta_job import BetaRun, run_beta_once
from hunter_scanner_worker.registry import MarketRef

from .builders import EXCHANGE
from .db_helpers import seed_market

pytestmark = pytest.mark.integration

SPEC = BetaSpec(window_days=1, min_contiguous_days=1)
"""24 hourly bars, one anchor bar before them. Everything else is the default."""

NOW = datetime(2026, 9, 8, 12, 37, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - SPEC.window
ANCHOR = WINDOW_START - SPEC.bar
BUCKETS = [ANCHOR + timedelta(hours=index) for index in range(25)]

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)

REFERENCE_MOVES = {5: Decimal("0.2"), 17: Decimal("-0.1")}
ASSET_MOVES = {5: Decimal("0.4"), 17: Decimal("-0.2")}
"""Exactly twice the reference, in the only two bars where anything moves."""


def _series(moves: dict[int, Decimal], *, start: Decimal = Decimal(100)) -> dict[datetime, Decimal]:
    """Bar closes, flat except at the bars named in ``moves``."""
    closes: dict[datetime, Decimal] = {}
    price = start
    for index, bucket in enumerate(BUCKETS):
        if index in moves:
            price = price * (Decimal(1) + moves[index])
        closes[bucket] = price
    return closes


async def _seed_bars(
    factory: Any,
    market_id: UUID,
    closes: dict[datetime, Decimal],
    *,
    incomplete: datetime | None = None,
) -> None:
    """Sixty 1-minute candles per bar, all closing at that bar's close.

    ``incomplete`` names a bar whose last minute is written **not final** — the
    one shape a look-ahead bug turns into a complete hour.
    """
    rows: list[dict[str, Any]] = []
    for bucket, close in closes.items():
        for minute in range(60):
            rows.append(
                {
                    "market_id": market_id,
                    "timeframe": Timeframe.M1,
                    "open_time": bucket + minute * MINUTE,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": Decimal("1"),
                    "is_final": not (incomplete == bucket and minute == 59),
                }
            )
    async with role_session(factory, db_role="hunter_worker") as session:
        for chunk in range(0, len(rows), 2000):
            await session.execute(insert(Candle), rows[chunk : chunk + 2000])


async def _revisions(factory: Any, market_id: UUID) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list(
            (
                await session.execute(
                    text(
                        "SELECT * FROM market_betas WHERE market_id = :market "
                        "ORDER BY as_of, computed_at, id"
                    ),
                    {"market": market_id},
                )
            ).all()
        )


async def _current(factory: Any, market_id: UUID, at: datetime) -> Any:
    """What ``bridge_universe.current_beta`` reads: the in-force, usable revision."""
    async with role_session(factory, db_role="hunter_worker") as session:
        return (
            await session.execute(
                text(
                    "SELECT beta, as_of, n FROM market_betas WHERE market_id = :market "
                    "AND superseded_at IS NULL AND valid AND beta IS NOT NULL "
                    "AND available_at <= :now AND window_end <= :now AND valid_until > :now "
                    "ORDER BY as_of DESC LIMIT 1"
                ),
                {"market": market_id, "now": at},
            )
        ).one_or_none()


async def _pair(factory: Any, tag: str) -> tuple[MarketRef, MarketRef]:
    """One reference market and one asset, named after the test that asked."""
    refs: list[MarketRef] = []
    for role in ("R", "A"):
        symbol = f"{role}{tag}USDT"
        market_id = await seed_market(factory, EXCHANGE, symbol, base=f"{role}{tag}", quote="USDT")
        refs.append(MarketRef(market_id=market_id, exchange=EXCHANGE, symbol=symbol))
    return refs[0], refs[1]


async def _run(
    factory: Any, reference: MarketRef, *refs: MarketRef, now: datetime = NOW
) -> BetaRun:
    return await run_beta_once(
        factory,
        [reference, *refs],
        now=now,
        spec=SPEC,
        reference_symbol=reference.symbol,
    )


@pytest.mark.asyncio
async def test_a_valid_revision_carries_the_numbers_the_estimator_produces(
    db_session_factory: Any,
) -> None:
    """beta = 2, alpha = 0, R^2 = 1 — the series says so, and so must the row."""
    reference, asset = await _pair(db_session_factory, "V1")
    await _seed_bars(db_session_factory, reference.market_id, _series(REFERENCE_MOVES))
    await _seed_bars(db_session_factory, asset.market_id, _series(ASSET_MOVES))

    run = await _run(db_session_factory, reference, asset)

    rows = await _revisions(db_session_factory, asset.market_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.valid is True
    assert row.reason is None
    assert row.beta == Decimal("2.00000000")
    assert row.alpha == Decimal("0.00000000")
    assert row.r_squared == Decimal("1.000000")
    assert row.n == 24
    assert row.contiguous_bars == 24
    assert row.estimator == "ols_with_intercept"
    assert row.beta_version == beta_version(SPEC)
    assert row.reference_market_id == reference.market_id
    # The cut is the closed hour, never the wall clock: 12:37 measures 12:00.
    assert row.as_of == WINDOW_END
    assert row.window_end == WINDOW_END
    assert row.window_start == WINDOW_START
    assert row.input_start == ANCHOR
    assert row.valid_until == WINDOW_END + HOUR
    assert row.superseded_at is None
    assert run.valid_markets == 2  # the asset, plus the reference's identity row
    current = await _current(db_session_factory, asset.market_id, NOW)
    assert current is not None
    assert current.beta == Decimal("2.00000000")


@pytest.mark.asyncio
async def test_a_rerun_of_the_same_closed_hour_inserts_nothing(db_session_factory: Any) -> None:
    """Idempotent per (market, closed hour, estimator): the second pass is a no-op."""
    reference, asset = await _pair(db_session_factory, "ID")
    await _seed_bars(db_session_factory, reference.market_id, _series(REFERENCE_MOVES))
    await _seed_bars(db_session_factory, asset.market_id, _series(ASSET_MOVES))

    first = await _run(db_session_factory, reference, asset)
    second = await _run(db_session_factory, reference, asset, now=NOW + timedelta(minutes=20))

    assert first.outcomes["valid"] == 2
    assert second.outcomes["unchanged"] == 2
    assert second.outcomes.get("valid", 0) == 0
    for ref in (reference, asset):
        rows = await _revisions(db_session_factory, ref.market_id)
        assert len(rows) == 1
        assert rows[0].superseded_at is None


@pytest.mark.asyncio
async def test_the_reference_is_one_by_identity_and_is_never_regressed(
    db_session_factory: Any,
) -> None:
    """The reference's row is a definition: no R^2, no pairs, no maturity gate."""
    reference, _ = await _pair(db_session_factory, "ONE")
    await _seed_bars(db_session_factory, reference.market_id, _series(REFERENCE_MOVES))

    await _run(db_session_factory, reference)

    rows = await _revisions(db_session_factory, reference.market_id)
    assert len(rows) == 1
    assert rows[0].estimator == "definition"
    assert rows[0].beta == Decimal("1.00000000")
    assert rows[0].r_squared is None
    assert rows[0].n == 0
    assert rows[0].valid is True
    assert rows[0].reference_market_id == reference.market_id


@pytest.mark.asyncio
async def test_a_market_short_of_the_run_is_stored_invalid_with_no_beta(
    db_session_factory: Any,
) -> None:
    """Warm-up is a row with a reason, never a fabricated number."""
    reference, asset = await _pair(db_session_factory, "WARM")
    await _seed_bars(db_session_factory, reference.market_id, _series(REFERENCE_MOVES))
    partial = {
        bucket: close for bucket, close in _series(ASSET_MOVES).items() if bucket >= BUCKETS[14]
    }
    await _seed_bars(db_session_factory, asset.market_id, partial)

    run = await _run(db_session_factory, reference, asset)

    rows = await _revisions(db_session_factory, asset.market_id)
    assert len(rows) == 1
    assert rows[0].valid is False
    assert rows[0].reason == "insufficient_history"
    assert rows[0].beta is None
    assert rows[0].alpha is None
    assert rows[0].r_squared is None
    assert run.outcomes["invalid"] == 1
    assert await _current(db_session_factory, asset.market_id, NOW) is None


@pytest.mark.asyncio
async def test_a_hole_in_the_recent_run_is_a_gap_not_a_beta(db_session_factory: Any) -> None:
    """The reach is there, the run is broken: ``gaps``, and no coefficients."""
    reference, asset = await _pair(db_session_factory, "GAP")
    await _seed_bars(db_session_factory, reference.market_id, _series(REFERENCE_MOVES))
    holed = {
        bucket: close for bucket, close in _series(ASSET_MOVES).items() if bucket != BUCKETS[20]
    }
    await _seed_bars(db_session_factory, asset.market_id, holed)

    await _run(db_session_factory, reference, asset)

    rows = await _revisions(db_session_factory, asset.market_id)
    assert rows[0].valid is False
    assert rows[0].reason == "gaps"
    assert rows[0].beta is None
    assert rows[0].contiguous_bars < 24


@pytest.mark.asyncio
async def test_without_the_reference_series_every_market_says_btc_missing(
    db_session_factory: Any,
) -> None:
    """No bar of the reference pairs: the asset is refused, and the row says why."""
    reference, asset = await _pair(db_session_factory, "NOREF")
    await _seed_bars(db_session_factory, asset.market_id, _series(ASSET_MOVES))

    await _run(db_session_factory, reference, asset)

    rows = await _revisions(db_session_factory, asset.market_id)
    assert rows[0].valid is False
    assert rows[0].reason == "btc_missing"
    assert rows[0].beta is None
    # The reference's own identity row does not depend on any data at all.
    assert (await _revisions(db_session_factory, reference.market_id))[0].valid is True


@pytest.mark.asyncio
async def test_a_minute_that_is_not_final_does_not_complete_its_bar(
    db_session_factory: Any,
) -> None:
    """The look-ahead proof: the still-printing minute is not evidence.

    The same bar, the same sixty rows, one bit different — and the difference is
    a valid beta or none at all. Flipping that bit to ``true``, which is what the
    collector does when the minute closes, is what makes the hour exist; and the
    recomputation of the *same* cut supersedes the revision it corrects instead
    of editing it.
    """
    reference, asset = await _pair(db_session_factory, "FINAL")
    await _seed_bars(db_session_factory, reference.market_id, _series(REFERENCE_MOVES))
    await _seed_bars(
        db_session_factory, asset.market_id, _series(ASSET_MOVES), incomplete=BUCKETS[24]
    )

    await _run(db_session_factory, reference, asset)
    rows = await _revisions(db_session_factory, asset.market_id)
    assert rows[0].valid is False
    assert rows[0].reason == "gaps"

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE candles SET is_final = true WHERE market_id = :market "
                "AND timeframe = '1m' AND open_time = :minute"
            ),
            {"market": asset.market_id, "minute": BUCKETS[24] + 59 * MINUTE},
        )

    await _run(db_session_factory, reference, asset)
    rows = await _revisions(db_session_factory, asset.market_id)
    assert len(rows) == 2
    assert rows[0].superseded_at is not None
    assert rows[1].valid is True
    assert rows[1].beta == Decimal("2.00000000")
    assert rows[1].as_of == WINDOW_END
    current = await _current(db_session_factory, asset.market_id, NOW)
    assert current is not None
    assert current.beta == Decimal("2.00000000")


@pytest.mark.asyncio
async def test_the_hour_that_has_not_closed_is_never_measured(db_session_factory: Any) -> None:
    """Two runs inside the same hour agree; the next closed hour is a new cut.

    The bar starting at the cut is seeded **complete and final** on purpose — a
    shape the collector cannot produce, and exactly the one a query that read
    ``open_time <= now`` instead of ``open_time < window_end`` would swallow.
    """
    reference, asset = await _pair(db_session_factory, "BOUND")
    reference_closes = _series(REFERENCE_MOVES) | {WINDOW_END: Decimal("999")}
    asset_closes = _series(ASSET_MOVES) | {WINDOW_END: Decimal("1")}
    await _seed_bars(db_session_factory, reference.market_id, reference_closes)
    await _seed_bars(db_session_factory, asset.market_id, asset_closes)

    early = await _run(db_session_factory, reference, asset, now=WINDOW_END + timedelta(seconds=2))
    late = await _run(
        db_session_factory, reference, asset, now=WINDOW_END + timedelta(minutes=59, seconds=59)
    )

    assert early.window_end == WINDOW_END
    assert late.window_end == WINDOW_END
    assert late.outcomes["unchanged"] == 2
    rows = await _revisions(db_session_factory, asset.market_id)
    assert len(rows) == 1
    assert rows[0].beta == Decimal("2.00000000")

    later = await _run(
        db_session_factory, reference, asset, now=WINDOW_END + timedelta(hours=1, minutes=1)
    )
    assert later.window_end == WINDOW_END + HOUR
    rows = await _revisions(db_session_factory, asset.market_id)
    assert len(rows) == 2
    assert {row.as_of for row in rows} == {WINDOW_END, WINDOW_END + HOUR}
