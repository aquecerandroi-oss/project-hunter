"""End to end on a synthetic series: candles -> features -> baseline -> anomaly.

The detector tests inject a feature value directly; this file injects a **volume
spike into a candle series** and lets the real T2.2 calculators and the real
bootstrap produce the numbers, so what is checked is the whole chain the scanner
will run.

The arithmetic, by hand:

- the calm series repeats volumes 10..16, so the median of the 23 prior
  five-minute windows is 65 and ``relative_volume_5m`` sits at 1 most of the
  time; over three days of the 00:00 UTC bucket that gives median ``1`` and
  ``MAD = 0.0461538462`` (= 0.6/13, at the ten decimals the column keeps);
- five minutes at volume 16 make the window 5 x 16 = 80, so
  ``relative_volume_5m = 80 / 65 = 16/13 = 1.230769...``;
- ``d = (16/13 - 1) / (0.6/13) = 3/0.6 = 5`` MADs (4.999999995 with the MAD
  quantised, which is the number the database would hold);
- ``severity = (5 - 1) / (6 - 1) * 100 = 80``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

import pytest

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyType, BaselineSource
from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.anomalies import (
    AnomalyAction,
    AnomalyDirection,
    NormalizationConfig,
    advance,
    detector_for,
    evaluate_detector,
)
from hunter_indicators.baselines import (
    REASON_INSUFFICIENT_HISTORY,
    BaselineCut,
    BaselineGate,
    BaselineKey,
    BaselineProjection,
    BaselineRevision,
    StoredBaseline,
    bootstrap_observations,
    compute_revision,
)
from hunter_indicators.features import build_context, compute_features
from packages.indicators.tests.factories import EXCHANGE, MINUTE, SYMBOL, candle

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
BASELINE_ID = uuid.UUID("0199a1d0-0000-7000-8000-0000000000aa")
FEATURE = "relative_volume_5m"
HISTORY_START = datetime(2026, 9, 1, 21, 0, tzinfo=UTC)
EVAL_START = datetime(2026, 9, 4, 22, 0, tzinfo=UTC)
EVAL_MINUTES = 150
EVAL_CUT = EVAL_START + EVAL_MINUTES * MINUTE
GATE = BaselineGate(min_distinct_days=3, min_valid_observations=120, expected_size=420)
CONFIG = NormalizationConfig(
    method="mad_piecewise_v1",
    deadband_mad=Decimal("1"),
    saturation_mad=Decimal("6"),
    saturation_score=Decimal("100"),
    weights_version="v2",
)
DETECTOR = detector_for(AnomalyType.VOLUME_SPIKE)


def _series(
    start: datetime, minutes: int, *, spike_from: int | None = None, spike_volume: str = "10"
) -> list[NormalizedCandle]:
    """Volumes cycling 10..16, optionally spiked from ``spike_from`` on."""
    price = Decimal("100")
    out: list[NormalizedCandle] = []
    for index in range(minutes):
        price = price + (Decimal("0.1") if index % 3 else Decimal("-0.05"))
        volume = Decimal(10 + (index % 7))
        if spike_from is not None and index >= spike_from:
            volume = Decimal(spike_volume)
        out.append(
            candle(
                start + index * MINUTE,
                close=price,
                high=price + Decimal("0.2"),
                low=price - Decimal("0.2"),
                volume=volume,
            )
        )
    return out


@lru_cache(maxsize=2)
def _bootstrapped(days: int) -> BaselineRevision:
    """The 00:00 UTC bucket of ``relative_volume_5m`` over ``days`` calm days."""
    candles = _series(HISTORY_START, 3 * 1440 + 4 * 60)
    cuts = [
        datetime(2026, 9, day, 0, 0, tzinfo=UTC) + minute * MINUTE
        for day in range(2, 2 + days)
        for minute in range(60)
    ]
    collector, sampled = bootstrap_observations(
        market_id=MARKET,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        candles=candles,
        cuts=cuts,
        buffer_minutes=180,
    )
    assert sampled == 60 * days
    revision = compute_revision(
        key=BaselineKey(market_id=MARKET, feature=FEATURE, hour_of_day=0),
        feature_version=1,
        source=BaselineSource.BOOTSTRAP,
        window_start=cuts[0] - timedelta(days=7),
        # half-open window: the last sampled minute has to be *inside* it
        window_end=cuts[-1] + timedelta(minutes=1),
        available_at=cuts[-1] + timedelta(minutes=1),
        observations=collector.bucket(FEATURE, 0),
        expected_size=420,
    )
    assert isinstance(revision, BaselineRevision)
    return revision


def _projection(revision: BaselineRevision) -> BaselineProjection:
    return BaselineProjection(
        [StoredBaseline(baseline_id=BASELINE_ID, revision=revision)],
        cut=BaselineCut(as_of=EVAL_CUT, observation_ts=EVAL_CUT),
        gate=GATE,
    )


def _evaluate(spike_volume: str, revision: BaselineRevision):
    candles = _series(
        EVAL_START, EVAL_MINUTES, spike_from=EVAL_MINUTES - 5, spike_volume=spike_volume
    )
    ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=EVAL_CUT, candles=candles)
    vector = compute_features(ctx).vector
    return evaluate_detector(
        DETECTOR,
        market_id=MARKET,
        vector=vector,
        projection=_projection(revision),
        config=CONFIG,
    )


class TestTheBootstrappedBaseline:
    def test_three_calm_days_produce_the_expected_statistics(self) -> None:
        revision = _bootstrapped(3)
        assert revision.median == Decimal("1.0000000000")
        assert revision.mad == Decimal("0.0461538462")  # 0.6/13 at ten decimals
        assert revision.sample_size == 180
        assert revision.distinct_days == 3
        assert revision.coverage == Decimal("0.428571")  # 180/420
        assert revision.source is BaselineSource.BOOTSTRAP
        assert revision.usable_under(GATE) is True

    def test_one_day_is_below_the_gate(self) -> None:
        revision = _bootstrapped(1)
        assert revision.sample_size == 60
        assert revision.distinct_days == 1
        assert revision.usable_under(GATE) is False


class TestTheInjectedSpike:
    def test_a_five_minute_spike_fires_with_the_hand_checked_severity(self) -> None:
        evaluation = _evaluate("16", _bootstrapped(3))
        assert evaluation.current_value == Decimal("16") * 5 / Decimal("65")  # 16/13
        assert evaluation.baseline == Decimal("1.0000000000")
        assert evaluation.deviation == Decimal("4.999999995000000005")
        assert evaluation.severity == Decimal("80.00")
        assert evaluation.direction is AnomalyDirection.UP
        assert evaluation.evaluation_state is AnomalyEvaluationState.OK
        assert evaluation.confidence == Decimal("0.4286")  # min(coverage, 3/7)
        assert evaluation.fires(DETECTOR) is True

    def test_an_enormous_spike_saturates_instead_of_growing(self) -> None:
        evaluation = _evaluate("50", _bootstrapped(3))
        assert evaluation.deviation is not None
        assert evaluation.deviation > Decimal("6")
        assert evaluation.severity == Decimal("100.00")

    def test_the_calm_series_is_exactly_on_its_median(self) -> None:
        evaluation = _evaluate("13", _bootstrapped(3))
        assert evaluation.current_value == Decimal("1")
        assert evaluation.deviation == Decimal("0")
        assert evaluation.severity == Decimal("0.00")
        assert evaluation.fires(DETECTOR) is False

    def test_a_volume_collapse_never_fires_a_spike_detector(self) -> None:
        evaluation = _evaluate("5", _bootstrapped(3))
        assert evaluation.deviation is not None
        assert evaluation.deviation < Decimal("-6")
        assert evaluation.severity == Decimal("0.00")
        assert evaluation.fires(DETECTOR) is False

    def test_an_immature_baseline_leaves_the_detector_unavailable(self) -> None:
        evaluation = _evaluate("16", _bootstrapped(1))
        assert evaluation.severity is None
        assert evaluation.reason == REASON_INSUFFICIENT_HISTORY
        assert evaluation.evaluation_state is AnomalyEvaluationState.UNKNOWN


class TestTheAnomalyThatResults:
    def test_the_spike_opens_an_anomaly_carrying_its_evidence(self) -> None:
        evaluation = _evaluate("16", _bootstrapped(3))
        transition = advance(None, evaluation, DETECTOR)
        assert transition.action is AnomalyAction.OPEN
        state = transition.state
        assert state is not None
        assert state.severity == Decimal("80.00")
        assert state.baseline == Decimal("1.0000000000")
        assert state.deviation == Decimal("4.999999995000000005")
        assert state.detector_version == "VOLUME_SPIKE@v1"
        assert state.baseline_ids == (BASELINE_ID,)
        assert state.unit == "ratio"

    @pytest.mark.parametrize("volume", ["13", "5"])
    def test_a_quiet_market_opens_nothing(self, volume: str) -> None:
        transition = advance(None, _evaluate(volume, _bootstrapped(3)), DETECTOR)
        assert transition.action is AnomalyAction.NONE
        assert transition.state is None
