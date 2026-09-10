"""The deep repair: an hour written ``UNKNOWN`` **by warm-up** heals only if asked.

This is the T3.76 blocker, in miniature and against a real database. On
2026-09-08 the producer's first pass filled thirty-one days while ``candles``
only went back to 2026-08-08, so the oldest hours of that pass had no history
behind them and were classified ``UNKNOWN`` -- honestly, and permanently:

- they **have** a row, so the backfill rule ("every hour of the window with no
  row") will never look at them again;
- they are weeks old, so the repair rule ("every hour of the last 72 h") does not
  reach them either.

The candle backfill that arrived afterwards (90 days, T3.62) made those same
hours classifiable, and nothing in the steady-state cadence would ever notice.
``regime_hourly --once --repair-days N`` is the documented operator lever
(``docs/PIPELINE.md`` section 4b item 7) and this file is the proof that it is
the lever that heals *this* shape -- the sibling test in ``test_regime_job.py``
proves the other shape, an hour holed by a missing minute **inside** the repair
window.

Three properties, in the order an operator meets them:

1. with the default repair window the warm-up hours stay ``UNKNOWN`` after the
   candles arrive (the failure this task exists to fix, asserted so that a future
   change that "fixes" it silently has to explain itself);
2. with a repair window as deep as the backfill window the same hours are
   **updated in place** -- same ids, because ``agent_signals.regime_id`` and its
   two siblings point at them with ``ON DELETE SET NULL``;
3. a second deep pass over the same candles writes **nothing**. Idempotency is a
   property of the digest, not of the operator's discipline -- the thing that
   makes it safe to run the ninety-day repair twice on the VPS to prove it.

Same compressed thresholds as ``test_regime_job.py`` (a 6-hour slow average
instead of 200): the production numbers would need 2.7 million candle rows per
test and would show nothing this window does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import insert, text

from hunter_core.db.models.market_data import Candle, FundingRate
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketRegime, Timeframe
from hunter_scanner_worker.regime_job import RegimeRun, run_regime_once
from hunter_scanner_worker.registry import MarketRef

from .db_helpers import seed_market
from .test_regime_job import THRESHOLDS

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 8, 12, 37, tzinfo=UTC)

DAYS = 5
"""Five days, so the oldest hours of the window sit well outside the 72-hour
repair window -- the whole point of the scenario."""

WINDOW_HOURS = DAYS * 24 + 1
"""``[CUT - 5 days, CUT]``, both ends included."""

SHALLOW_HOURS = 120
"""How much candle history exists when the first pass runs: exactly the window
and not one hour more, which is what puts its oldest hours in warm-up."""

REFERENCE_START = Decimal(1000)
FALLING_START = Decimal(5000)
"""High enough that twenty-four more hours of the same ramp behind the window
stay positive: a zero close ends ``absolute_returns`` and would change what is
under test into a different bug."""

DEEPER_HOURS = 24
"""What the candle backfill adds *behind* the window afterwards."""

WARMUP_HOURS = THRESHOLDS.sma_slow_hours + THRESHOLDS.slope_lookback_hours
"""Closes a trend verdict needs (8 here, 224 in production): the hours of the
window with fewer than this behind them come out ``UNKNOWN``."""

REPAIR_DEFAULT_H = 72
DEEP_REPAIR_H = DAYS * 24
"""What ``--repair-days 5`` asks for, in the units ``run_regime_once`` takes."""

HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)
FUNDING_RATE = Decimal("0.0001")


async def _seed_hours(
    factory: Any, market_id: Any, *, start: Decimal, step: Decimal, count: int, end: datetime
) -> None:
    """Sixty final one-minute candles per hour, each hour ``step`` above the last.

    Seeded here rather than imported from ``test_regime_job`` so that this file
    owns the one thing it varies -- how deep the history goes -- instead of
    reaching into another module's private helpers for it.
    """
    rows: list[dict[str, Any]] = []
    for index in range(count):
        hour = end - (count - index) * HOUR
        close = start + step * index
        rows.extend(
            {
                "market_id": market_id,
                "timeframe": Timeframe.M1,
                "open_time": hour + minute * MINUTE,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": Decimal(1),
                "is_final": True,
            }
            for minute in range(60)
        )
    async with role_session(factory, db_role="hunter_worker") as session:
        for chunk in range(0, len(rows), 2000):
            await session.execute(insert(Candle), rows[chunk : chunk + 2000])


async def _seed_funding(factory: Any, market_id: Any) -> None:
    """One settlement every eight hours over the whole window."""
    rows = [
        {"market_id": market_id, "funding_time": CUT - hour * HOUR, "rate": FUNDING_RATE}
        for hour in range(SHALLOW_HOURS + 8)
        if (CUT - hour * HOUR).hour % 8 == 0
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(insert(FundingRate), rows)


async def _rows(factory: Any, exchange: str) -> list[Any]:
    """Every row this exchange's producer wrote, oldest first, with ``xmin``."""
    async with role_session(factory, db_role="hunter_worker") as session:
        result = await session.execute(
            text(
                "SELECT id, xmin::text AS xmin, regime::text AS regime, start_time, "
                "       supporting_features "
                "  FROM market_regimes "
                " WHERE supporting_features ->> 'exchange' = :exchange "
                " ORDER BY start_time"
            ),
            {"exchange": exchange},
        )
        return list(result.all())


async def _pass(
    factory: Any,
    exchange: str,
    refs: list[MarketRef],
    *,
    now: datetime,
    days: int = DAYS,
    repair_hours: int = REPAIR_DEFAULT_H,
) -> RegimeRun:
    return await run_regime_once(
        factory,
        refs,
        now=now,
        exchange=exchange,
        thresholds=THRESHOLDS,
        days=days,
        repair_hours=repair_hours,
        reference_symbol=refs[0].symbol,
    )


async def _warm_start(factory: Any, tag: str) -> tuple[str, list[MarketRef]]:
    """A universe whose candles begin exactly where the regime window begins.

    One unbroken ramp per market over ``SHALLOW_HOURS`` and not one hour more:
    ``_deepen`` then continues the *same* ramp behind it, so the only thing that
    changes between the two passes is how much history exists -- never the shape
    of the series, which would confound "the repair reached it" with "the numbers
    moved".
    """
    exchange = f"binance-{tag.lower()}"
    refs: list[MarketRef] = []
    for role in ("R", "F"):
        symbol = f"{role}{tag}USDT"
        market_id = await seed_market(factory, exchange, symbol, base=f"{role}{tag}", quote="USDT")
        refs.append(MarketRef(market_id=market_id, exchange=exchange, symbol=symbol))
    reference, falling = refs
    await _seed_hours(
        factory,
        reference.market_id,
        start=REFERENCE_START,
        step=Decimal(1),
        count=SHALLOW_HOURS,
        end=CUT,
    )
    await _seed_hours(
        factory,
        falling.market_id,
        start=FALLING_START,
        step=Decimal(-1),
        count=SHALLOW_HOURS,
        end=CUT,
    )
    await _seed_funding(factory, falling.market_id)
    return exchange, refs


async def _deepen(factory: Any, refs: list[MarketRef]) -> None:
    """The candle backfill arriving: history *behind* the oldest window hour."""
    reference, falling = refs
    end = CUT - SHALLOW_HOURS * HOUR
    await _seed_hours(
        factory,
        reference.market_id,
        start=REFERENCE_START - DEEPER_HOURS,
        step=Decimal(1),
        count=DEEPER_HOURS,
        end=end,
    )
    await _seed_hours(
        factory,
        falling.market_id,
        start=FALLING_START + DEEPER_HOURS,
        step=Decimal(-1),
        count=DEEPER_HOURS,
        end=end,
    )


def _labels(rows: list[Any]) -> dict[datetime, str]:
    return {row.start_time: row.regime for row in rows}


@pytest.mark.asyncio
async def test_warm_up_hours_stay_unknown_under_the_default_repair_window(
    db_session_factory: Any,
) -> None:
    """The blocker: candles arrive, the steady-state pass never revisits them."""
    exchange, refs = await _warm_start(db_session_factory, "DR")

    first = await _pass(db_session_factory, exchange, refs, now=NOW, days=DAYS)

    assert first.outcomes == {"inserted": WINDOW_HOURS}
    before = _labels(await _rows(db_session_factory, exchange))
    oldest = CUT - SHALLOW_HOURS * HOUR
    warmup = [oldest + index * HOUR for index in range(WARMUP_HOURS)]
    assert [before[hour] for hour in warmup] == [MarketRegime.UNKNOWN.value] * WARMUP_HOURS

    await _deepen(db_session_factory, refs)
    steady = await _pass(
        db_session_factory,
        exchange,
        refs,
        now=NOW + timedelta(minutes=5),
        days=DAYS,
        repair_hours=REPAIR_DEFAULT_H,
    )

    # Only the repair window was even looked at, and nothing in it moved.
    assert steady.outcomes == {"unchanged": REPAIR_DEFAULT_H + 1}
    assert steady.hours == 0
    after = _labels(await _rows(db_session_factory, exchange))
    assert [after[hour] for hour in warmup] == [MarketRegime.UNKNOWN.value] * WARMUP_HOURS


@pytest.mark.asyncio
async def test_a_repair_as_deep_as_the_window_heals_them_in_place(
    db_session_factory: Any,
) -> None:
    """``--repair-days N``: the same hours, classified, with their ids intact."""
    exchange, refs = await _warm_start(db_session_factory, "DP")
    await _pass(db_session_factory, exchange, refs, now=NOW, days=DAYS)
    before = {row.start_time: row for row in await _rows(db_session_factory, exchange)}
    oldest = CUT - SHALLOW_HOURS * HOUR
    warmup = [oldest + index * HOUR for index in range(WARMUP_HOURS)]

    await _deepen(db_session_factory, refs)
    deep = await _pass(
        db_session_factory,
        exchange,
        refs,
        now=NOW + timedelta(minutes=5),
        days=DAYS,
        repair_hours=DEEP_REPAIR_H,
    )

    rows = await _rows(db_session_factory, exchange)
    healed = {row.start_time: row for row in rows}
    assert len(rows) == WINDOW_HOURS  # updated in place, never a second row
    assert MarketRegime.UNKNOWN.value not in {healed[hour].regime for hour in warmup}
    assert [healed[hour].id for hour in warmup] == [before[hour].id for hour in warmup]
    assert deep.outcomes["updated"] >= WARMUP_HOURS
    assert deep.outcomes["updated"] + deep.outcomes["unchanged"] == WINDOW_HOURS
    # The hours whose digest did not move were not rewritten: same xmin.
    untouched = [
        hour
        for hour in healed
        if healed[hour].supporting_features["digest"] == before[hour].supporting_features["digest"]
    ]
    assert untouched
    assert [healed[hour].xmin for hour in untouched] == [before[hour].xmin for hour in untouched]


@pytest.mark.asyncio
async def test_the_second_deep_pass_writes_nothing(db_session_factory: Any) -> None:
    """Idempotency of the ninety-day repair: the proof the VPS run owes."""
    exchange, refs = await _warm_start(db_session_factory, "DI")
    await _pass(db_session_factory, exchange, refs, now=NOW, days=DAYS)
    await _deepen(db_session_factory, refs)
    await _pass(
        db_session_factory,
        exchange,
        refs,
        now=NOW + timedelta(minutes=5),
        days=DAYS,
        repair_hours=DEEP_REPAIR_H,
    )
    healed = {row.start_time: row.xmin for row in await _rows(db_session_factory, exchange)}

    again = await _pass(
        db_session_factory,
        exchange,
        refs,
        now=NOW + timedelta(minutes=10),
        days=DAYS,
        repair_hours=DEEP_REPAIR_H,
    )

    assert again.outcomes == {"unchanged": WINDOW_HOURS}
    assert again.hours == 0
    assert {row.start_time: row.xmin for row in await _rows(db_session_factory, exchange)} == healed
