"""``regime_hourly_v1`` over synthetic series whose answers are known by hand.

Every series below is built so the expected number is arithmetic, not "whatever
the estimator said": linear ramps (so every average is the mean of an arithmetic
progression), alternating fixed-percentage moves (so every absolute return is the
same number), and integers wherever a price can be one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import MarketRegime
from hunter_indicators.regime import (
    REASON_BREADTH_COVERAGE,
    REASON_FUNDING_UNAVAILABLE,
    REASON_SCORE_UNAVAILABLE,
    REASON_TREND_WARMUP,
    REASON_VOL_WARMUP,
    REGIME_HOURLY_VERSION,
    BreadthCount,
    ComponentWeights,
    FundingAverage,
    HourlyThresholds,
    HourlyTrend,
    VolRegime,
    breadth_pct_of,
    build_snapshot,
    classify_trend,
    classify_volatility,
    contiguous_closes,
    count_breadth,
    drawdown_from_high,
    percentile_rank,
    project_regime,
    realised_vol,
    score_of,
    sma,
    vol_readings,
)

pytestmark = pytest.mark.unit

HOUR = timedelta(hours=1)
TS = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
THRESHOLDS = HourlyThresholds()

NO_BREADTH = BreadthCount()
NO_FUNDING = FundingAverage()


def series(values: list[Decimal], *, ts: datetime = TS) -> dict[datetime, Decimal]:
    """``values`` oldest first, the last one closing the bar that ends at ``ts``."""
    start = ts - len(values) * HOUR
    return {start + index * HOUR: value for index, value in enumerate(values)}


def ramp(count: int, *, start: Decimal = Decimal(100), step: Decimal = Decimal(1)) -> list[Decimal]:
    return [start + step * index for index in range(count)]


def alternating(count: int, *, move: Decimal, start: Decimal = Decimal(100)) -> list[Decimal]:
    """Closes whose every absolute return is exactly ``move``."""
    prices = [start]
    for index in range(1, count):
        factor = Decimal(1) + (move if index % 2 else -move)
        prices.append(prices[-1] * factor)
    return prices


# --- the pieces --------------------------------------------------------------


def test_contiguous_closes_stops_at_the_cut_and_at_the_first_hole() -> None:
    closes = series([Decimal(index) for index in range(1, 6)])  # 1..5, last closes at TS
    assert contiguous_closes(closes, ts=TS, limit=10) == (
        Decimal(1),
        Decimal(2),
        Decimal(3),
        Decimal(4),
        Decimal(5),
    )
    # The bar that starts at the cut is not behind it and never enters.
    closes[TS] = Decimal(999)
    assert contiguous_closes(closes, ts=TS, limit=10)[-1] == Decimal(5)
    del closes[TS - 3 * HOUR]
    assert contiguous_closes(closes, ts=TS, limit=10) == (Decimal(4), Decimal(5))


def test_sma_is_the_mean_of_the_last_n_and_none_when_short() -> None:
    values = ramp(50)  # 100..149
    assert sma(values, 50) == Decimal("124.5")
    assert sma(values, 51) is None


def test_realised_vol_is_the_mean_absolute_return() -> None:
    closes = alternating(25, move=Decimal("0.01"))
    readings = vol_readings(closes, window=24)
    assert len(readings) == 1
    assert readings[0] == Decimal("0.0100000000")
    assert realised_vol([Decimal("0.02"), Decimal("0.04")]) == Decimal("0.0300000000")


def test_percentile_rank_splits_ties_so_a_flat_tape_ranks_at_fifty() -> None:
    assert percentile_rank([Decimal(1), Decimal(2), Decimal(3), Decimal(4)], Decimal(3)) == Decimal(
        "62.50"
    )
    assert percentile_rank([Decimal(5)] * 10, Decimal(5)) == Decimal("50.00")
    assert percentile_rank([Decimal(1), Decimal(2)], Decimal(9)) == Decimal("100.00")


# --- trend -------------------------------------------------------------------


def test_a_rising_ramp_is_up_with_the_slope_the_arithmetic_gives() -> None:
    """300 closes of +1/h: SMA50 = 374.5, SMA200 = 299.5, slope = 24/350.5."""
    verdict = classify_trend(ramp(300), THRESHOLDS)
    assert verdict.trend is HourlyTrend.UP
    assert verdict.sma_fast == Decimal("374.5")
    assert verdict.sma_slow == Decimal("299.5")
    assert verdict.slope == Decimal("0.068474")  # 24 / 350.5


def test_a_falling_ramp_is_down() -> None:
    verdict = classify_trend(ramp(300, start=Decimal(400), step=Decimal(-1)), THRESHOLDS)
    assert verdict.trend is HourlyTrend.DOWN
    assert verdict.sma_fast == Decimal("125.5")
    assert verdict.sma_slow == Decimal("200.5")
    assert verdict.slope == Decimal("-0.160535")  # -24 / 149.5


def test_a_flat_tape_is_flat_not_unknown() -> None:
    verdict = classify_trend([Decimal(100)] * 300, THRESHOLDS)
    assert verdict.trend is HourlyTrend.FLAT
    assert verdict.slope == Decimal("0.000000")
    assert verdict.reason is None


def test_structure_without_movement_is_flat() -> None:
    """Stacked averages, price above the slow one, but the slope below the gate.

    +0.001/h on a base of 100 moves SMA50 from 100.2505 to 100.2745 over 24 h:
    0.024 / 100.2505 = 0.000239 < 0.002.
    """
    verdict = classify_trend(ramp(300, step=Decimal("0.001")), THRESHOLDS)
    assert verdict.trend is HourlyTrend.FLAT
    assert verdict.slope == Decimal("0.000239")


def test_too_little_history_is_unknown_and_says_why() -> None:
    verdict = classify_trend(ramp(223), THRESHOLDS)  # 200 + 24 needed
    assert verdict.trend is HourlyTrend.UNKNOWN
    assert verdict.reason == REASON_TREND_WARMUP


# --- volatility --------------------------------------------------------------


def _quiet_then_violent() -> list[Decimal]:
    """721 flat closes, then 24 returns of +1 % — the last reading is the maximum.

    The tail starts at ``1.01 ** 1``: the first of the 24 returns has to be the
    step *out of* the flat stretch, or the window would hold 23 moves and a zero.
    """
    return [Decimal(100)] * 721 + [
        Decimal(100) * (Decimal("1.01") ** index) for index in range(1, 25)
    ]


def test_a_day_of_moves_after_a_month_of_calm_ranks_at_the_top() -> None:
    verdict = classify_volatility(_quiet_then_violent(), THRESHOLDS)
    assert verdict.vol_regime is VolRegime.HIGH
    assert verdict.current == Decimal("0.0100000000")
    assert verdict.percentile == Decimal("100.00")
    assert verdict.samples == 720


def test_a_calm_day_after_a_month_of_moves_ranks_at_the_bottom() -> None:
    closes = alternating(745, move=Decimal("0.01")) + [Decimal(0)] * 0
    closes = closes[:721] + [closes[720]] * 24
    verdict = classify_volatility(closes, THRESHOLDS)
    assert verdict.vol_regime is VolRegime.LOW
    assert verdict.current == Decimal("0E-10")
    assert verdict.percentile == Decimal("0.00")


def test_an_unchanging_distribution_is_normal() -> None:
    verdict = classify_volatility(alternating(900, move=Decimal("0.01")), THRESHOLDS)
    assert verdict.vol_regime is VolRegime.NORMAL
    assert verdict.percentile == Decimal("50.00")


def test_fewer_readings_than_the_minimum_is_unknown() -> None:
    verdict = classify_volatility(alternating(100, move=Decimal("0.01")), THRESHOLDS)
    assert verdict.vol_regime is VolRegime.UNKNOWN
    assert verdict.reason == REASON_VOL_WARMUP
    assert verdict.samples == 75  # 100 closes -> 99 returns -> 76 readings, minus the current


# --- breadth, drawdown, funding ---------------------------------------------


def test_breadth_is_advancing_over_usable_behind_a_coverage_gate() -> None:
    assert breadth_pct_of(BreadthCount(universe=200, usable=200, advancing=50), THRESHOLDS) == (
        Decimal("25.00")
    )
    # 40 % of the universe read: the confirmation is unavailable, not bearish.
    assert breadth_pct_of(BreadthCount(universe=200, usable=80, advancing=0), THRESHOLDS) is None


def test_drawdown_is_measured_from_the_window_high() -> None:
    closes = [Decimal(100)] * 100 + [Decimal(200)] + [Decimal(150)] * 100
    value, high = drawdown_from_high(closes, THRESHOLDS)
    assert (value, high) == (Decimal("25.00"), Decimal(200))
    assert drawdown_from_high([Decimal(100)] * 10, THRESHOLDS) == (None, None)


@pytest.mark.parametrize(
    ("funding", "expected"),
    [
        (Decimal("0"), Decimal("50.00")),
        (Decimal("0.0005"), Decimal("0.00")),
        (Decimal("-0.0005"), Decimal("100.00")),
        (Decimal("0.005"), Decimal("0.00")),  # clamped, never negative
        (Decimal("0.00025"), Decimal("25.00")),
    ],
)
def test_funding_is_centred_on_neutral_and_saturates(funding: Decimal, expected: Decimal) -> None:
    snapshot = build_snapshot(
        ts=TS,
        closes=series(ramp(300)),
        breadth=BreadthCount(universe=10, usable=10, advancing=10),
        funding=FundingAverage(value=funding, markets=10),
        thresholds=THRESHOLDS,
    )
    component = next(item for item in snapshot.components if item.name == "funding")
    assert component.normalized == expected


# --- the snapshot ------------------------------------------------------------


def test_the_decomposition_is_complete_and_the_score_is_its_weighted_mean() -> None:
    """Every component available: trend up (100), breadth 100, vol, dd, funding."""
    closes = ramp(900)  # rising all the way: up, low volatility, no drawdown
    snapshot = build_snapshot(
        ts=TS,
        closes=series(closes),
        breadth=BreadthCount(universe=10, usable=10, advancing=10),
        funding=FundingAverage(value=Decimal("0"), markets=10),
        thresholds=THRESHOLDS,
    )
    assert snapshot.trend is HourlyTrend.UP
    assert snapshot.breadth_pct == Decimal("100.00")
    assert snapshot.drawdown_pct == Decimal("0.00")
    assert snapshot.funding_avg == Decimal("0E-8")
    assert snapshot.confidence == Decimal("1.0000")
    assert snapshot.version == REGIME_HOURLY_VERSION
    by_name = {component.name: component for component in snapshot.components}
    assert set(by_name) == {"trend", "breadth", "volatility", "drawdown", "funding"}
    assert by_name["trend"].normalized == Decimal(100)
    assert by_name["trend"].weight == Decimal("0.35")
    assert by_name["trend"].contribution == Decimal("35.00")
    assert by_name["drawdown"].normalized == Decimal("100.00")
    assert by_name["funding"].normalized == Decimal("50.00")
    total = sum(
        (component.contribution or Decimal(0) for component in snapshot.components), Decimal(0)
    )
    assert snapshot.score_0_100 == total  # every weight available -> sum == mean
    assert snapshot.reasons == ()


def test_a_missing_component_redistributes_its_weight_and_lowers_confidence() -> None:
    """No breadth, no funding: 0.65 of the weight left, and it is said out loud."""
    snapshot = build_snapshot(
        ts=TS,
        closes=series(ramp(900)),
        breadth=NO_BREADTH,
        funding=NO_FUNDING,
        thresholds=THRESHOLDS,
    )
    assert snapshot.breadth_pct is None
    assert snapshot.funding_avg is None
    assert snapshot.confidence == Decimal("0.6500")
    assert set(snapshot.reasons) == {REASON_BREADTH_COVERAGE, REASON_FUNDING_UNAVAILABLE}
    by_name = {component.name: component for component in snapshot.components}
    # trend 100 * 0.35 + volatility n * 0.20 + drawdown 100 * 0.10, over 0.65.
    vol_normalized = by_name["volatility"].normalized
    assert vol_normalized is not None
    expected = (
        Decimal("0.35") * Decimal(100)
        + Decimal("0.20") * vol_normalized
        + Decimal("0.10") * Decimal(100)
    ) / Decimal("0.65")
    assert snapshot.score_0_100 == expected.quantize(Decimal("0.01"))


def test_below_half_the_weight_there_is_no_score() -> None:
    snapshot = build_snapshot(
        ts=TS,
        closes=series(ramp(10)),
        breadth=NO_BREADTH,
        funding=NO_FUNDING,
        thresholds=THRESHOLDS,
    )
    assert snapshot.trend is HourlyTrend.UNKNOWN
    assert snapshot.vol_regime is VolRegime.UNKNOWN
    assert snapshot.score_0_100 is None
    assert snapshot.confidence == Decimal("0.0000")
    assert REASON_SCORE_UNAVAILABLE in snapshot.reasons
    assert snapshot.regime is MarketRegime.UNKNOWN


def test_the_projection_onto_one_label_is_the_v0_table() -> None:
    assert project_regime(HourlyTrend.UP, VolRegime.NORMAL) is MarketRegime.BTC_BULL
    assert project_regime(HourlyTrend.DOWN, VolRegime.NORMAL) is MarketRegime.BTC_BEAR
    assert project_regime(HourlyTrend.FLAT, VolRegime.NORMAL) is MarketRegime.SIDEWAYS
    assert project_regime(HourlyTrend.FLAT, VolRegime.LOW) is MarketRegime.LOW_VOLATILITY
    # High volatility wins over the trend -- the lossy half of the projection.
    assert project_regime(HourlyTrend.DOWN, VolRegime.HIGH) is MarketRegime.HIGH_VOLATILITY
    assert project_regime(HourlyTrend.UNKNOWN, VolRegime.HIGH) is MarketRegime.UNKNOWN


def test_an_overridden_threshold_never_travels_as_the_shipped_version() -> None:
    other = HourlyThresholds(sma_fast_hours=20)
    assert other.identity != REGIME_HOURLY_VERSION
    assert other.identity.startswith(f"{REGIME_HOURLY_VERSION}+")
    assert HourlyThresholds().identity == REGIME_HOURLY_VERSION
    assert HourlyThresholds(weights=ComponentWeights()).identity == REGIME_HOURLY_VERSION


def test_the_snapshot_wire_carries_the_whole_decomposition() -> None:
    snapshot = build_snapshot(
        ts=TS,
        closes=series(ramp(900)),
        breadth=BreadthCount(universe=4, usable=4, advancing=1),
        funding=FundingAverage(value=Decimal("0.0001"), markets=4),
        thresholds=THRESHOLDS,
    )
    wire = snapshot.as_wire()
    assert wire["version"] == REGIME_HOURLY_VERSION
    assert wire["trend"] == "up"
    assert wire["breadth_pct"] == Decimal("25.00")
    assert [component["name"] for component in wire["components"]] == [
        "trend",
        "breadth",
        "volatility",
        "drawdown",
        "funding",
    ]
    for component in wire["components"]:
        assert set(component) == {"name", "raw", "normalized", "weight", "contribution", "reason"}
    assert wire["inputs"]["breadth"] == {"universe": 4, "usable": 4, "advancing": 1}
    assert wire["inputs"]["closes"] == 745  # capped by the deepest window it needs


# --- no look-ahead -----------------------------------------------------------


def test_the_snapshot_does_not_change_when_the_forming_hour_changes() -> None:
    """The proof the whole engine rests on: nothing at or after ``ts`` is read."""
    closes = series(ramp(900))
    before = build_snapshot(
        ts=TS,
        closes=closes,
        breadth=BreadthCount(universe=10, usable=10, advancing=7),
        funding=FundingAverage(value=Decimal("0.0001"), markets=10),
        thresholds=THRESHOLDS,
    )
    contaminated = dict(closes)
    for index in range(6):  # six hours of the future, one of them a crash
        contaminated[TS + index * HOUR] = Decimal(1) if index == 3 else Decimal(100_000)
    after = build_snapshot(
        ts=TS,
        closes=contaminated,
        breadth=BreadthCount(universe=10, usable=10, advancing=7),
        funding=FundingAverage(value=Decimal("0.0001"), markets=10),
        thresholds=THRESHOLDS,
    )
    assert after == before


def test_a_snapshot_of_the_next_hour_is_the_one_that_sees_the_new_bar() -> None:
    closes = dict(series(ramp(900)))
    baseline = build_snapshot(
        ts=TS, closes=closes, breadth=NO_BREADTH, funding=NO_FUNDING, thresholds=THRESHOLDS
    )
    closes[TS] = Decimal(1)
    later = build_snapshot(
        ts=TS + HOUR, closes=closes, breadth=NO_BREADTH, funding=NO_FUNDING, thresholds=THRESHOLDS
    )
    assert baseline.trend is HourlyTrend.UP
    assert later.trend is not HourlyTrend.UP  # the crash is behind the new cut
    assert later.inputs.last_close == Decimal(1)


def test_score_of_is_a_pure_function_of_the_components_it_is_given() -> None:
    snapshot = build_snapshot(
        ts=TS,
        closes=series(ramp(900)),
        breadth=BreadthCount(universe=10, usable=10, advancing=10),
        funding=FundingAverage(value=Decimal("0"), markets=10),
        thresholds=THRESHOLDS,
    )
    assert score_of(snapshot.components, THRESHOLDS) == (
        snapshot.score_0_100,
        snapshot.confidence,
    )


def test_count_breadth_needs_both_conditions_and_a_full_window() -> None:
    """Above the 24 h average **and** up over 24 h; 25 closes or not counted."""
    rising = series(ramp(30))  # above its own average and up over the day
    falling = series(ramp(30, start=Decimal(200), step=Decimal(-1)))
    short = series(ramp(10))  # fewer than the 25 closes the pair of tests needs
    # Up over the day but under a falling average: the V is not advancing.
    v_shape = series([Decimal(200)] * 20 + [Decimal(100)] * 4 + [Decimal(101)] * 6)
    counted = count_breadth(
        {"UP": rising, "DOWN": falling, "SHORT": short, "V": v_shape},
        ts=TS,
        universe=4,
        thresholds=THRESHOLDS,
    )
    assert counted == BreadthCount(universe=4, usable=3, advancing=1)
    assert breadth_pct_of(counted, THRESHOLDS) == Decimal("33.33")
