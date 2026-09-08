"""The hourly regime producer, against a real database.

Everything here is only observable against Postgres, because the point of the job
is the *row*: ``market_regimes`` has no ``(exchange, ts)`` key of its own, so the
idempotency is a property of what this job does with the table, and a fake
session would prove none of it. The arithmetic is already proved with known
values in ``packages/indicators/tests/unit/test_regime_hourly.py``.

The thresholds are **compressed on purpose** (a 6-hour slow average instead of
200, a 2-hour volatility window instead of 24): the production numbers need 745
closed hours of one-minute candles per test, which is 2.7 million rows to seed
and buys nothing the fifteen-hour window does not already show. Compression also
exercises the ``regime_hourly_v1+<digest>`` naming that the shipped defaults
never produce.

The reference series is a **linear ramp** so every answer is arithmetic: prices
rise by a constant amount, so the trend is up, the drawdown is zero, and the
percentage returns shrink monotonically, which puts the newest realised-vol
reading at the bottom of its own distribution — ``low``. Every row of the window
therefore carries the same score, and the score is computed by hand in
``test_the_row_carries_the_whole_decomposition``.

Each test seeds its own exchange, so the ``(exchange, ts)`` lookup keeps one
test's rows out of the next one's window — which is the same property production
needs the day a second exchange produces a series of its own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import insert, text

from hunter_core.db.models.market_data import Candle, FundingRate
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketRegime, Timeframe
from hunter_indicators.regime import REGIME_HOURLY_VERSION, HourlyThresholds
from hunter_scanner_worker.regime_job import RegimeRun, run_regime_once
from hunter_scanner_worker.registry import MarketRef

from .db_helpers import seed_market

pytestmark = pytest.mark.integration

THRESHOLDS = HourlyThresholds(
    sma_fast_hours=3,
    sma_slow_hours=6,
    slope_lookback_hours=2,
    vol_window_hours=2,
    vol_reference_hours=12,
    vol_min_samples=3,
    drawdown_window_hours=12,
    drawdown_min_hours=3,
)
"""Fifteen closed hours of depth instead of 745. Everything else is the default."""

NOW = datetime(2026, 9, 8, 12, 37, tzinfo=UTC)
CUT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
DAYS = 1
HOURS_IN_WINDOW = 25
"""``[CUT - 1 day, CUT]``, both ends included: 24 hours plus the cut itself."""

SEEDED_HOURS = 40
"""24 hours of window plus the 15 of depth the compressed thresholds read."""

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)

FUNDING_RATE = Decimal("0.0001")
"""Settled every eight hours on the falling market only — 0.0001 is the funding
the score maps onto 40 (``50 - (0.0001 / 0.0005) x 50``)."""


def _hours(count: int = SEEDED_HOURS) -> list[datetime]:
    """The ``count`` hour starts ending with the one that closes at ``CUT``."""
    return [CUT - (count - index) * HOUR for index in range(count)]


async def _seed_hours(
    factory: Any,
    market_id: UUID,
    *,
    start: Decimal,
    step: Decimal,
    incomplete: datetime | None = None,
) -> None:
    """Sixty one-minute candles per hour, each hour closing ``step`` above the last.

    ``incomplete`` names an hour whose **last minute** is written not final — the
    one shape a look-ahead bug turns into a complete hour.
    """
    rows: list[dict[str, Any]] = []
    for index, hour in enumerate(_hours()):
        close = start + step * index
        for minute in range(60):
            rows.append(
                {
                    "market_id": market_id,
                    "timeframe": Timeframe.M1,
                    "open_time": hour + minute * MINUTE,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": Decimal(1),
                    "is_final": not (incomplete == hour and minute == 59),
                }
            )
    async with role_session(factory, db_role="hunter_worker") as session:
        for chunk in range(0, len(rows), 2000):
            await session.execute(insert(Candle), rows[chunk : chunk + 2000])


async def _seed_funding(factory: Any, market_id: UUID) -> None:
    """One settlement every eight hours, at the instants Binance settles at."""
    rows = [
        {"market_id": market_id, "funding_time": hour, "rate": FUNDING_RATE}
        for hour in _hours(SEEDED_HOURS + 8)
        if hour.hour % 8 == 0
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(insert(FundingRate), rows)


async def _universe(factory: Any, tag: str) -> tuple[str, list[MarketRef]]:
    """A rising reference and a falling companion, on an exchange of their own."""
    exchange = f"binance-{tag.lower()}"
    refs: list[MarketRef] = []
    for role in ("R", "F"):
        symbol = f"{role}{tag}USDT"
        market_id = await seed_market(factory, exchange, symbol, base=f"{role}{tag}", quote="USDT")
        refs.append(MarketRef(market_id=market_id, exchange=exchange, symbol=symbol))
    reference, falling = refs
    await _seed_hours(factory, reference.market_id, start=Decimal(100), step=Decimal(1))
    await _seed_hours(factory, falling.market_id, start=Decimal(500), step=Decimal(-1))
    await _seed_funding(factory, falling.market_id)
    return exchange, refs


async def _run(
    factory: Any, exchange: str, refs: list[MarketRef], *, now: datetime = NOW
) -> RegimeRun:
    return await run_regime_once(
        factory,
        refs,
        now=now,
        exchange=exchange,
        thresholds=THRESHOLDS,
        days=DAYS,
        reference_symbol=refs[0].symbol,
    )


async def _rows(factory: Any, exchange: str) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list(
            (
                await session.execute(
                    text(
                        "SELECT id, scope::text AS scope, regime::text AS regime, confidence, "
                        "start_time, end_time, classifier_version, supporting_features "
                        "  FROM market_regimes "
                        " WHERE supporting_features ->> 'exchange' = :exchange "
                        " ORDER BY start_time"
                    ),
                    {"exchange": exchange},
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_a_pass_writes_one_closed_row_per_hour_of_the_window(
    db_session_factory: Any,
) -> None:
    """25 hours in, 25 rows out — every one of them closed and hour-aligned."""
    exchange, refs = await _universe(db_session_factory, "W1")

    run = await _run(db_session_factory, exchange, refs)

    assert run.cut == CUT
    assert run.outcomes["inserted"] == HOURS_IN_WINDOW
    assert run.hours == HOURS_IN_WINDOW
    assert run.last_ts == CUT
    rows = await _rows(db_session_factory, exchange)
    assert len(rows) == HOURS_IN_WINDOW
    assert [row.start_time for row in rows] == [
        CUT - (HOURS_IN_WINDOW - 1 - index) * HOUR for index in range(HOURS_IN_WINDOW)
    ]
    for row in rows:
        # Closed, always: the open-per-scope index belongs to the live regime_v0
        # engine, and this series is joined by interval containment.
        assert row.end_time == row.start_time + HOUR
        assert row.scope == "btc"
        assert row.classifier_version == THRESHOLDS.identity
        assert row.classifier_version.startswith(f"{REGIME_HOURLY_VERSION}+")
        assert row.regime == MarketRegime.BTC_BULL.value


@pytest.mark.asyncio
async def test_the_row_carries_the_whole_decomposition(db_session_factory: Any) -> None:
    """trend 100, breadth 50, volatility 100, drawdown 100, funding 40 -> 81.50."""
    exchange, refs = await _universe(db_session_factory, "D1")

    await _run(db_session_factory, exchange, refs)

    row = (await _rows(db_session_factory, exchange))[-1]
    features = row.supporting_features
    assert features["trend"] == "up"
    assert features["vol_regime"] == "low"
    assert features["breadth_pct"] == "50"  # the falling market is half of two
    assert features["funding_avg"] == "0.0001"
    assert features["drawdown_pct"] == "0"
    assert features["score_0_100"] == "81.5"
    assert row.confidence == Decimal("1.0000")
    normalized = {
        component["name"]: component["normalized"] for component in features["components"]
    }
    assert normalized == {
        "trend": "100",
        "breadth": "50",
        "volatility": "100",
        "drawdown": "100",
        "funding": "40",
    }
    contributions = {
        component["name"]: component["contribution"] for component in features["components"]
    }
    assert contributions == {
        "trend": "35",
        "breadth": "12.5",
        "volatility": "20",
        "drawdown": "10",
        "funding": "4",
    }
    assert features["inputs"]["breadth"] == {"universe": "2", "usable": "2", "advancing": "1"}
    assert features["thresholds"]["sma_slow_hours"] == "6"
    assert features["exchange"] == exchange


@pytest.mark.asyncio
async def test_a_rerun_of_the_same_hours_writes_nothing(db_session_factory: Any) -> None:
    """Idempotent on ``(exchange, ts)``: the second pass recognises every hour."""
    exchange, refs = await _universe(db_session_factory, "ID")

    first = await _run(db_session_factory, exchange, refs)
    before = await _rows(db_session_factory, exchange)
    second = await _run(db_session_factory, exchange, refs, now=NOW + timedelta(minutes=20))

    assert first.outcomes["inserted"] == HOURS_IN_WINDOW
    # Only one hour is *due* on the second pass: the 24 behind the cut already
    # have rows, and the cut itself is always recomputed because its candles may
    # still be arriving. Recomputed, and then recognised -- the digest matched.
    assert second.outcomes == {"unchanged": 1}
    assert second.hours == 0
    after = await _rows(db_session_factory, exchange)
    assert len(after) == HOURS_IN_WINDOW
    # The ids survive: agent_signals.regime_id points at them with SET NULL, so a
    # rewrite that deleted and reinserted would erase the regime of every
    # decision that referenced the hour.
    assert [row.id for row in after] == [row.id for row in before]


@pytest.mark.asyncio
async def test_a_minute_that_is_not_final_does_not_complete_its_hour(
    db_session_factory: Any,
) -> None:
    """The anti-look-ahead proof, end to end, and the repair path with it.

    The last minute of ``11:00`` is written not final, so ``11:00`` is not an
    hour: the cut at ``12:00`` walks back from a hole and reads no closes at all,
    and the honest answer is ``UNKNOWN``. Flipping that one bit — what the
    collector does when the minute closes — is what makes the hour exist, and the
    rerun updates the row in place instead of writing a second one.
    """
    exchange, refs = await _universe(db_session_factory, "LA")
    reference = refs[0]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE candles SET is_final = false "
                " WHERE market_id = :market AND open_time = :minute AND timeframe = '1m'"
            ),
            {"market": reference.market_id, "minute": CUT - MINUTE},
        )

    await _run(db_session_factory, exchange, refs)

    row = (await _rows(db_session_factory, exchange))[-1]
    assert row.start_time == CUT
    assert row.regime == MarketRegime.UNKNOWN.value
    assert row.supporting_features["trend"] == "unknown"
    assert row.supporting_features["inputs"]["closes"] == "0"
    row_id = row.id

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE candles SET is_final = true "
                " WHERE market_id = :market AND open_time = :minute AND timeframe = '1m'"
            ),
            {"market": reference.market_id, "minute": CUT - MINUTE},
        )
    repaired = await _run(db_session_factory, exchange, refs, now=NOW + timedelta(minutes=5))

    assert repaired.outcomes == {"updated": 1}  # the cut, and only the cut, was due
    rows = await _rows(db_session_factory, exchange)
    assert len(rows) == HOURS_IN_WINDOW
    assert rows[-1].id == row_id  # updated in place, not replaced
    assert rows[-1].regime == MarketRegime.BTC_BULL.value
    assert rows[-1].supporting_features["inputs"]["closes"] == "15"


@pytest.mark.asyncio
async def test_the_backfill_window_bounds_which_hours_exist(db_session_factory: Any) -> None:
    """``days`` decides how far back the first pass fills, and nothing older."""
    exchange, refs = await _universe(db_session_factory, "BF")

    await run_regime_once(
        db_session_factory,
        refs,
        now=NOW,
        exchange=exchange,
        thresholds=THRESHOLDS,
        days=0,
        reference_symbol=refs[0].symbol,
    )

    rows = await _rows(db_session_factory, exchange)
    assert [row.start_time for row in rows] == [CUT]

    # A later pass with a wider window fills the hours the narrow one skipped,
    # and leaves the one it already wrote alone.
    wider = await _run(db_session_factory, exchange, refs)

    assert wider.outcomes["inserted"] == HOURS_IN_WINDOW - 1
    assert wider.outcomes["unchanged"] == 1
    rows = await _rows(db_session_factory, exchange)
    assert len(rows) == HOURS_IN_WINDOW
    assert rows[0].start_time == CUT - timedelta(days=DAYS)


@pytest.mark.asyncio
async def test_a_universe_without_its_reference_writes_nothing(db_session_factory: Any) -> None:
    """No reference market, no row: every component is anchored on it."""
    exchange, refs = await _universe(db_session_factory, "NR")

    run = await run_regime_once(
        db_session_factory,
        refs,
        now=NOW,
        exchange=exchange,
        thresholds=THRESHOLDS,
        days=DAYS,
        reference_symbol="NOTHINGUSDT",
    )

    assert run.outcomes["no_reference"] == 1
    assert run.hours == 0
    assert await _rows(db_session_factory, exchange) == []
