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

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from sqlalchemy import insert, text

from hunter_core.db.models.market_data import Candle, FundingRate
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketRegime, Timeframe
from hunter_indicators.regime import REGIME_HOURLY_VERSION, HourlyThresholds
from hunter_scanner_worker import regime_job
from hunter_scanner_worker.regime_hourly import claim_cut
from hunter_scanner_worker.regime_job import RegimeRun, run_regime_once
from hunter_scanner_worker.registry import MarketRef

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

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


def _hours(count: int = SEEDED_HOURS, *, end: datetime = CUT) -> list[datetime]:
    """The ``count`` hour starts ending with the one that closes at ``end``."""
    return [end - (count - index) * HOUR for index in range(count)]


async def _seed_hours(
    factory: Any,
    market_id: UUID,
    *,
    start: Decimal,
    step: Decimal,
    incomplete: datetime | None = None,
    count: int = SEEDED_HOURS,
    end: datetime = CUT,
) -> None:
    """Sixty one-minute candles per hour, each hour closing ``step`` above the last.

    ``incomplete`` names an hour whose **last minute** is written not final — the
    one shape a look-ahead bug turns into a complete hour.
    """
    rows: list[dict[str, Any]] = []
    for index, hour in enumerate(_hours(count, end=end)):
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


async def _universe(
    factory: Any, tag: str, *, incomplete: datetime | None = None
) -> tuple[str, list[MarketRef]]:
    """A rising reference and a falling companion, on an exchange of their own."""
    exchange = f"binance-{tag.lower()}"
    refs: list[MarketRef] = []
    for role in ("R", "F"):
        symbol = f"{role}{tag}USDT"
        market_id = await seed_market(factory, exchange, symbol, base=f"{role}{tag}", quote="USDT")
        refs.append(MarketRef(market_id=market_id, exchange=exchange, symbol=symbol))
    reference, falling = refs
    await _seed_hours(
        factory, reference.market_id, start=Decimal(100), step=Decimal(1), incomplete=incomplete
    )
    await _seed_hours(factory, falling.market_id, start=Decimal(500), step=Decimal(-1))
    await _seed_funding(factory, falling.market_id)
    return exchange, refs


async def _run(
    factory: Any,
    exchange: str,
    refs: list[MarketRef],
    *,
    now: datetime = NOW,
    days: int = DAYS,
    repair_hours: int = 72,
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


async def _rows(factory: Any, exchange: str) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list(
            (
                await session.execute(
                    text(
                        "SELECT id, xmin::text AS xmin, scope::text AS scope, "
                        "regime::text AS regime, confidence, "
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
async def test_a_rerun_recomputes_the_repair_window_and_writes_nothing(
    db_session_factory: Any,
) -> None:
    """Idempotent on ``(exchange, ts)``: 25 hours recomputed, zero rows written.

    The repair window (72 h, wider than this test's 25-hour window) makes every
    hour *due* on the second pass — that is the fix for the hour that could
    never heal. What must not follow is a rewrite: ``xmin`` is the transaction
    that last wrote each row, so an unchanged ``xmin`` is the proof that the
    recomputation cost no ``UPDATE`` at all, not merely that the values matched.
    """
    exchange, refs = await _universe(db_session_factory, "ID")

    first = await _run(db_session_factory, exchange, refs)
    before = await _rows(db_session_factory, exchange)
    second = await _run(db_session_factory, exchange, refs, now=NOW + timedelta(minutes=20))

    assert first.outcomes["inserted"] == HOURS_IN_WINDOW
    assert second.outcomes == {"unchanged": HOURS_IN_WINDOW}
    assert second.hours == 0
    after = await _rows(db_session_factory, exchange)
    assert len(after) == HOURS_IN_WINDOW
    # The ids survive: agent_signals.regime_id points at them with SET NULL, so a
    # rewrite that deleted and reinserted would erase the regime of every
    # decision that referenced the hour.
    assert [row.id for row in after] == [row.id for row in before]
    assert [row.xmin for row in after] == [row.xmin for row in before]


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

    # Every hour of the window was recomputed; only the cut read different
    # candles, so only the cut was written.
    assert repaired.outcomes == {"unchanged": HOURS_IN_WINDOW - 1, "updated": 1}
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


BROKEN = CUT - 5 * HOUR
"""The hour whose last minute is missing when the first pass runs. Its hole
truncates the fold of every later hour (``contiguous_closes`` stops at the first
gap), so five rows come out ``unknown`` — a real candle gap, at real depth."""


@pytest.mark.asyncio
async def test_a_historical_hour_written_unknown_is_repaired_after_the_candle_arrives(
    db_session_factory: Any,
) -> None:
    """HIGH-1, end to end: the gap heals, and the old rule is shown not healing it.

    A minute of ``CUT - 5h`` is missing when the first pass runs, so that hour is
    not an hour and the five newest rows are ``UNKNOWN``. The collector then
    delivers the minute. Under the rule this task replaced — recompute only the
    cut and the hours with no row — the four historical rows would stay
    ``UNKNOWN`` forever, which is asserted here before the fix is applied, so the
    test fails if the repair window is ever removed. With the repair window, the
    same candles produce four ``updated`` rows and twenty-one ``unchanged``.
    """
    exchange, refs = await _universe(db_session_factory, "RP", incomplete=BROKEN)
    reference = refs[0]

    await _run(db_session_factory, exchange, refs)

    broken = {row.start_time: row for row in await _rows(db_session_factory, exchange)}
    unknown_hours = [BROKEN + index * HOUR for index in range(1, 6)]
    assert [broken[hour].regime for hour in unknown_hours] == [MarketRegime.UNKNOWN.value] * 5
    assert broken[BROKEN].regime == MarketRegime.BTC_BULL.value  # decided before the hole

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE candles SET is_final = true "
                " WHERE market_id = :market AND open_time = :minute AND timeframe = '1m'"
            ),
            {"market": reference.market_id, "minute": BROKEN + 59 * MINUTE},
        )

    # The old rule: only the cut and the hours with no row. The cut heals; the
    # four hours behind it are the permanent hole this task exists to close.
    old_rule = await _run(
        db_session_factory, exchange, refs, now=NOW + timedelta(minutes=5), repair_hours=0
    )

    assert old_rule.outcomes == {"updated": 1}
    stuck = {row.start_time: row for row in await _rows(db_session_factory, exchange)}
    assert [stuck[hour].regime for hour in unknown_hours[:4]] == [MarketRegime.UNKNOWN.value] * 4

    repaired = await _run(db_session_factory, exchange, refs, now=NOW + timedelta(minutes=10))

    assert repaired.outcomes == {"updated": 4, "unchanged": HOURS_IN_WINDOW - 4}
    assert repaired.hours == 4
    rows = await _rows(db_session_factory, exchange)
    assert len(rows) == HOURS_IN_WINDOW  # repaired in place, never a second row
    assert {row.regime for row in rows} == {MarketRegime.BTC_BULL.value}
    healed = {row.start_time: row for row in rows}
    assert [healed[hour].id for hour in unknown_hours] == [
        broken[hour].id for hour in unknown_hours
    ]
    # And the twenty-one hours nobody touched were not rewritten: same xmin.
    untouched = [hour for hour in healed if hour not in unknown_hours]
    assert [healed[hour].xmin for hour in untouched] == [broken[hour].xmin for hour in untouched]


@pytest.mark.asyncio
async def test_two_producers_of_the_same_cut_write_one_row_per_hour(
    db_session_factory: Any, redis_client: redis_asyncio.Redis
) -> None:
    """The lock, and what it is standing in for.

    ``market_regimes`` has **no** unique index on ``(scope, start_time)`` — the
    one asked for in ``.claude/state/brief-T3.43-db-market-regimes-hourly.md`` —
    so the database would happily accept the same hour twice: two passes reading
    ``existing_hours`` before either of them commits both see an empty window and
    both insert. That index is the real guard; until it exists,
    ``regime:producer:{exchange}:{cut}`` is what makes exactly one of two
    simultaneous producers compute the cut, and this test is the proof for the
    arrangement that is actually deployed.
    """
    exchange, refs = await _universe(db_session_factory, "CC")

    async def producer() -> RegimeRun | None:
        if not await claim_cut(redis_client, exchange, CUT):
            return None
        return await _run(db_session_factory, exchange, refs)

    outcomes = await asyncio.gather(producer(), producer())

    winners = [run for run in outcomes if run is not None]
    assert len(winners) == 1  # one claim, one pass
    assert winners[0].outcomes["inserted"] == HOURS_IN_WINDOW
    rows = await _rows(db_session_factory, exchange)
    assert len(rows) == HOURS_IN_WINDOW
    assert len({row.start_time for row in rows}) == HOURS_IN_WINDOW
    # The claim is not a lease that has to be released: the same cut is refused
    # to anybody else until it expires, and a later cut is a different key.
    assert await claim_cut(redis_client, exchange, CUT) is False
    assert await claim_cut(redis_client, exchange, CUT + HOUR) is True


BACKFILL_TEST_DAYS = 31
BACKFILL_TEST_HOURS = BACKFILL_TEST_DAYS * 24 + 1
"""745: the production backfill window, hour for hour."""

COST_NOW = NOW + timedelta(days=30)
COST_CUT = CUT + timedelta(days=30)
"""A cut a month after every other test's. Thirty-one days of candles behind
``CUT`` would land in 2026-08, and ``candles_1m`` has no partition before
2026-09 (``infra/migrations/ddl/partitions.py``): the seed would be refused, not
slow. Moving the cut instead of creating a partition keeps this test out of the
schema's business."""

BACKFILL_BUDGET_S = 60.0
"""The number the review asked to measure against. Above it, the writes would
have to be batched per day; below it, one transaction per hour keeps the
property that a single bad hour costs that hour and nothing else."""


@pytest.mark.asyncio
async def test_the_thirty_one_day_backfill_costs_one_transaction_per_hour(
    db_session_factory: Any,
) -> None:
    """LOW-4: 745 hours, 745 transactions — measured, not assumed.

    One market only: what is being measured is the write path (a transaction per
    hour), not the universe fold, which is already measured in
    ``.claude/state/notes-T3.43.md``. The second pass is the steady state after
    this fix: the 72-hour repair window is recomputed and, because no candle
    moved, not one row is rewritten — ``xmin`` proves it.
    """
    exchange = "binance-cost"
    symbol = "CSTUSDT"
    market_id = await seed_market(db_session_factory, exchange, symbol, base="CST", quote="USDT")
    refs = [MarketRef(market_id=market_id, exchange=exchange, symbol=symbol)]
    seeded = BACKFILL_TEST_HOURS + 15  # the window plus the depth of THRESHOLDS
    started = time.monotonic()
    await _seed_hours(
        db_session_factory,
        market_id,
        start=Decimal(100),
        step=Decimal(1),
        count=seeded,
        end=COST_CUT,
    )
    seed_s = time.monotonic() - started

    first = await _run(db_session_factory, exchange, refs, now=COST_NOW, days=BACKFILL_TEST_DAYS)
    before = await _rows(db_session_factory, exchange)
    second = await _run(
        db_session_factory,
        exchange,
        refs,
        now=COST_NOW + timedelta(minutes=20),
        days=BACKFILL_TEST_DAYS,
    )
    after = await _rows(db_session_factory, exchange)

    print(  # the measurement is the point of this test
        f"\nregime backfill cost: seed {seeded * 60} candles in {seed_s:.1f}s | "
        f"first pass {first.outcomes['inserted']} rows in {first.duration_s:.1f}s "
        f"({first.duration_s / BACKFILL_TEST_HOURS * 1000:.1f} ms/hour) | "
        f"steady pass {second.outcomes['unchanged']} recomputed, {second.hours} written, "
        f"in {second.duration_s:.1f}s"
    )
    assert first.outcomes == {"inserted": BACKFILL_TEST_HOURS}
    assert len(before) == BACKFILL_TEST_HOURS
    assert first.duration_s < BACKFILL_BUDGET_S
    # Steady state: the repair window and nothing else, and no row rewritten.
    assert second.outcomes == {"unchanged": 73}
    assert second.hours == 0
    assert [row.xmin for row in after] == [row.xmin for row in before]


@pytest.mark.asyncio
async def test_a_batch_that_fails_is_retried_hour_by_hour(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The price of writing a day per transaction, and what pays it back.

    Batching the writes took the 31-day backfill from 186,5 s to ~12 s, but a
    transaction covering twenty-four hours means one unwritable hour rolls back
    twenty-three good ones. So a batch that raises is retried hour by hour, and
    that is asserted here with a writer poisoned twice: every batch fails, and
    inside the retry one specific hour fails too. Twenty-four hours are written
    anyway and the poisoned hour — and only it — is missing.
    """
    exchange, refs = await _universe(db_session_factory, "FB")
    poisoned = CUT - 3 * HOUR
    real = regime_job.write_snapshots

    async def flaky(
        session: Any, snapshots: Any, *, exchange: str, thresholds: HourlyThresholds
    ) -> Any:
        if len(snapshots) > 1:
            raise RuntimeError("the batch cannot be written")
        if snapshots[0].ts == poisoned:
            raise RuntimeError("this hour cannot be written")
        return await real(session, snapshots, exchange=exchange, thresholds=thresholds)

    monkeypatch.setattr(regime_job, "write_snapshots", flaky)

    run = await _run(db_session_factory, exchange, refs)

    assert run.outcomes == {"inserted": HOURS_IN_WINDOW - 1, "failed": 1}
    assert run.hours == HOURS_IN_WINDOW - 1
    rows = await _rows(db_session_factory, exchange)
    assert len(rows) == HOURS_IN_WINDOW - 1
    assert poisoned not in {row.start_time for row in rows}
    # The failure is an outcome, never a hidden hole: the next pass finds the
    # hour missing and produces it (the backfill rule), with no operator.
    monkeypatch.setattr(regime_job, "write_snapshots", real)
    again = await _run(db_session_factory, exchange, refs, now=NOW + timedelta(minutes=5))

    assert again.outcomes == {"inserted": 1, "unchanged": HOURS_IN_WINDOW - 1}
