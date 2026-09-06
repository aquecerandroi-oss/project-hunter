"""Nothing T2.3 decides may move when the candle still forming moves.

T2.2 proves it for the bar features themselves
(``test_no_lookahead.py``); this file proves it for what is built **on top** of
them — the stage, the anomaly evaluation and the baseline population. The
mutation is deliberately violent (the forming minute doubles in price and in
volume, and its ``_live`` features do change), so a classifier that quietly
reached for the partial minute would fail here rather than in production.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import AnomalyType, BaselineSampling, BaselineSource
from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.anomalies import (
    NormalizationConfig,
    detector_for,
    evaluate_detector,
)
from hunter_indicators.baselines import (
    BaselineCut,
    BaselineGate,
    BaselineKey,
    BaselineProjection,
    BaselineRevision,
    StoredBaseline,
    observations_from_vector,
)
from hunter_indicators.features import FeatureVector, build_context, compute_features
from hunter_indicators.stage import StageThresholds, classify_stage
from packages.indicators.tests.factories import EXCHANGE, MINUTE, SYMBOL, candle

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
BASELINE_ID = uuid.UUID("0199a1d0-0000-7000-8000-0000000000aa")
ORIGIN = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
GATE = BaselineGate(min_distinct_days=3, min_valid_observations=120, expected_size=420)
CONFIG = NormalizationConfig(
    method="mad_piecewise_v1",
    deadband_mad=Decimal("1"),
    saturation_mad=Decimal("6"),
    saturation_score=Decimal("100"),
    weights_version="v2",
)
THRESHOLDS = StageThresholds(
    r_early_max=Decimal("1.5"),
    r_developing_max=Decimal("4"),
    relative_volume_1h_min=Decimal("3"),
    trade_velocity_baseline_multiple_min=Decimal("2"),
    open_interest_change_1h_min=Decimal("0.02"),
    buy_pressure_5m_long_min=Decimal("0.60"),
    buy_pressure_5m_short_max=Decimal("0.40"),
    extended_return_4h_atr_multiple=Decimal("3"),
    extended_relative_volume_15m_declines=3,
    extended_relative_volume_15m_closes=4,
    confirmations=2,
    weights_version="v2",
)


def history(minutes: int = 400) -> list[NormalizedCandle]:
    price = Decimal("100")
    out: list[NormalizedCandle] = []
    for index in range(minutes):
        price = price + (Decimal("0.1") if index % 3 else Decimal("-0.05"))
        out.append(
            candle(
                ORIGIN + index * MINUTE,
                close=price,
                high=price + Decimal("0.2"),
                low=price - Decimal("0.2"),
                volume=Decimal(10 + (index % 7)),
            )
        )
    return out


def vector_with_forming(close: str, volume: str) -> FeatureVector:
    """The same closed history, with a forming minute the caller controls."""
    candles = history()
    cut = ORIGIN + 400 * MINUTE + timedelta(seconds=30)
    forming = candle(
        ORIGIN + 400 * MINUTE,
        close=Decimal(close),
        volume=Decimal(volume),
        is_final=False,
        event_ts=cut,
    )
    ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=cut, candles=[*candles, forming])
    return compute_features(ctx).vector


def projection(feature: str, observation_ts: datetime) -> BaselineProjection:
    window_end = observation_ts - timedelta(hours=1)
    revision = BaselineRevision(
        key=BaselineKey(market_id=MARKET, feature=feature, hour_of_day=observation_ts.hour),
        feature_version=1,
        algo_version="median_mad_v1",
        sampling=BaselineSampling.PER_MINUTE,
        source=BaselineSource.LIVE,
        window_start=window_end - timedelta(days=7),
        window_end=window_end,
        available_at=window_end,
        median=Decimal("1"),
        mad=Decimal("0.25"),
        sample_size=400,
        expected_size=420,
        distinct_days=7,
        coverage=Decimal("0.952381"),
        input_fingerprint="fp",
    )
    return BaselineProjection(
        [StoredBaseline(baseline_id=BASELINE_ID, revision=revision)],
        cut=BaselineCut(as_of=observation_ts, observation_ts=observation_ts),
        gate=GATE,
    )


class TestTheMutationIsRealBeforeAnythingElse:
    def test_the_forming_candle_does_move_the_live_features(self) -> None:
        quiet = vector_with_forming("100", "10")
        loud = vector_with_forming("200", "9999")
        assert quiet.number("return_1m_live") != loud.number("return_1m_live")


class TestStage:
    def test_the_stage_does_not_move_with_the_forming_candle(self) -> None:
        quiet = classify_stage(vector_with_forming("100", "10"), thresholds=THRESHOLDS)
        loud = classify_stage(vector_with_forming("200", "9999"), thresholds=THRESHOLDS)
        assert quiet.as_wire() == loud.as_wire()

    def test_the_ratio_itself_is_bar_only(self) -> None:
        quiet = classify_stage(vector_with_forming("100", "10"), thresholds=THRESHOLDS)
        loud = classify_stage(vector_with_forming("200", "9999"), thresholds=THRESHOLDS)
        assert quiet.r == loud.r
        assert quiet.r is not None


class TestAnomalies:
    def test_a_detector_verdict_does_not_move_with_the_forming_candle(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        results = [
            evaluate_detector(
                detector,
                market_id=MARKET,
                vector=vector,
                projection=projection(detector.feature, vector.ts),
                config=CONFIG,
            ).as_wire()
            for vector in (vector_with_forming("100", "10"), vector_with_forming("200", "9999"))
        ]
        assert results[0] == results[1]


class TestBaselineObservations:
    def test_the_population_does_not_move_with_the_forming_candle(self) -> None:
        features = ("relative_volume_5m", "return_1h", "atr_14_pct")
        quiet, _ = observations_from_vector(vector_with_forming("100", "10"), features)
        loud, _ = observations_from_vector(vector_with_forming("200", "9999"), features)
        assert quiet == loud
        assert quiet  # the window really did produce observations
