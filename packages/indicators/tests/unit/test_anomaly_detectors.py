"""The roster of ten detectors and what one evaluation says.

Severities here are checked by hand against ``mad_piecewise_v1``; the point of
each test is a *decision* (fire, stay silent, refuse with a reason), never a
number that merely looks plausible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyType,
    BaselineSampling,
    BaselineSource,
)
from hunter_indicators.anomalies import (
    REASON_DISABLED,
    REASON_MAD_ZERO,
    REASON_NO_FEATURE,
    AnomalyDirection,
    DetectorSide,
    NormalizationConfig,
    default_detectors,
    detector_for,
    evaluate_detector,
    evaluate_detectors,
)
from hunter_indicators.baselines import (
    REASON_INSUFFICIENT_HISTORY,
    REASON_NO_BASELINE,
    BaselineCut,
    BaselineGate,
    BaselineKey,
    BaselineProjection,
    BaselineRevision,
    StoredBaseline,
)
from hunter_indicators.features import (
    DEFAULT_REGISTRY,
    FeatureValue,
    FeatureVector,
    Quality,
    Reason,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
BASELINE_ID = uuid.UUID("0199a1d0-0000-7000-8000-0000000000aa")
OBSERVED_AT = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
CUT = BaselineCut(as_of=OBSERVED_AT + timedelta(seconds=30), observation_ts=OBSERVED_AT)
GATE = BaselineGate(min_distinct_days=3, min_valid_observations=120, expected_size=420)
CONFIG = NormalizationConfig(
    method="mad_piecewise_v1",
    deadband_mad=Decimal("1"),
    saturation_mad=Decimal("6"),
    saturation_score=Decimal("100"),
    weights_version="v2",
)


def revision(
    feature: str,
    *,
    median: str = "1",
    mad: str = "0.25",
    sample_size: int = 400,
    distinct_days: int = 7,
) -> BaselineRevision:
    window_end = OBSERVED_AT - timedelta(hours=1)
    return BaselineRevision(
        key=BaselineKey(market_id=MARKET, feature=feature, hour_of_day=10),
        feature_version=1,
        algo_version="median_mad_v1",
        sampling=BaselineSampling.PER_MINUTE,
        source=BaselineSource.LIVE,
        window_start=window_end - timedelta(days=7),
        window_end=window_end,
        available_at=window_end,
        median=Decimal(median),
        mad=Decimal(mad),
        sample_size=sample_size,
        expected_size=420,
        distinct_days=distinct_days,
        coverage=(Decimal(sample_size) / Decimal(420)).quantize(Decimal("0.000001")),
        input_fingerprint=f"fp-{feature}",
    )


def projection(*revisions: BaselineRevision) -> BaselineProjection:
    entries = [
        StoredBaseline(
            baseline_id=uuid.UUID(int=BASELINE_ID.int + index),
            revision=item,
        )
        for index, item in enumerate(revisions)
    ]
    return BaselineProjection(entries, cut=CUT, gate=GATE)


def vector(values: dict[str, FeatureValue]) -> FeatureVector:
    return FeatureVector(
        exchange="binance",
        symbol="BTCUSDT",
        ts=OBSERVED_AT,
        feature_set_version=DEFAULT_REGISTRY.feature_set_version,
        values=values,
    )


class TestRoster:
    def test_the_ten_v1_detectors_are_registered(self) -> None:
        types = {detector.type for detector in default_detectors()}
        assert types == {
            AnomalyType.VOLUME_SPIKE,
            AnomalyType.PRICE_ACCELERATION,
            AnomalyType.MOMENTUM_SHIFT,
            AnomalyType.VOLATILITY_EXPANSION,
            AnomalyType.ORDERBOOK_IMBALANCE,
            AnomalyType.TRADE_VELOCITY_SPIKE,
            AnomalyType.OPEN_INTEREST_SPIKE,
            AnomalyType.FUNDING_ANOMALY,
            AnomalyType.LIQUIDATION_CLUSTER,
            AnomalyType.CROSS_EXCHANGE_DIVERGENCE,
        }

    def test_cross_exchange_divergence_is_registered_and_disarmed(self) -> None:
        detector = detector_for(AnomalyType.CROSS_EXCHANGE_DIVERGENCE)
        assert detector.enabled is False
        assert detector.disabled_reason == "single_exchange_until_m1b"

    def test_liquidation_cluster_is_disarmed_because_its_feature_does_not_exist(self) -> None:
        detector = detector_for(AnomalyType.LIQUIDATION_CLUSTER)
        assert detector.enabled is False
        assert detector.disabled_reason == "feature_not_implemented"

    def test_every_armed_detector_reads_a_feature_this_build_registers(self) -> None:
        keys = set(DEFAULT_REGISTRY.keys())
        for detector in default_detectors():
            if detector.enabled:
                assert detector.feature in keys
                assert (
                    detector.feature_version
                    == DEFAULT_REGISTRY.get(detector.feature).definition.version
                )

    def test_one_sided_detectors_declare_their_tail(self) -> None:
        assert detector_for(AnomalyType.VOLUME_SPIKE).side is DetectorSide.UP
        assert detector_for(AnomalyType.VOLATILITY_EXPANSION).side is DetectorSide.UP
        assert detector_for(AnomalyType.MOMENTUM_SHIFT).side is DetectorSide.BOTH

    def test_thresholds_are_declared_and_versioned(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        assert detector.version == "v1"
        assert detector.fire_min_severity == Decimal("40")
        assert detector.hold_min_severity == Decimal("20")
        assert detector.resolve_after == timedelta(minutes=5)
        assert detector.expire_after == timedelta(hours=4)


class TestOneEvaluation:
    def test_an_injected_spike_fires_with_a_hand_checked_severity(self) -> None:
        # baseline median 1, MAD 0.25; a relative volume of 2 is (2-1)/0.25 = 4
        # MADs -> (4-1)/5*100 = 60.
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("2"))}
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.severity == Decimal("60.00")
        assert evaluation.deviation == Decimal("4")
        assert evaluation.baseline == Decimal("1")
        assert evaluation.current_value == Decimal("2")
        assert evaluation.direction is AnomalyDirection.UP
        assert evaluation.evaluation_state is AnomalyEvaluationState.OK
        assert evaluation.fires(detector) is True
        assert evaluation.baseline_ids

    def test_a_collapse_does_not_fire_a_spike_detector(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("0"))}
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.deviation == Decimal("-4")
        assert evaluation.severity == Decimal("0.00")
        assert evaluation.fires(detector) is False

    def test_a_degraded_reading_is_stale_and_ineligible(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        value = FeatureValue.ok("relative_volume_5m", Decimal("2")).degraded_to(
            Quality.DEGRADED, Reason.STALE_INPUT
        )
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector({"relative_volume_5m": value}),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.evaluation_state is AnomalyEvaluationState.STALE
        assert evaluation.eligible is False
        assert evaluation.severity == Decimal("60.00")  # shown, never acted on

    def test_an_unavailable_reading_is_unknown_with_the_feature_reason(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {
                    "relative_volume_5m": FeatureValue.unavailable(
                        "relative_volume_5m", Reason.WARMUP
                    )
                }
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.evaluation_state is AnomalyEvaluationState.UNKNOWN
        assert evaluation.reason == "warmup"
        assert evaluation.severity is None

    def test_an_immature_baseline_makes_the_detector_unavailable_not_stale(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("2"))}
            ),
            projection=projection(revision("relative_volume_5m", sample_size=100)),
            config=CONFIG,
        )
        assert evaluation.reason == REASON_INSUFFICIENT_HISTORY
        assert evaluation.evaluation_state is AnomalyEvaluationState.UNKNOWN
        assert evaluation.severity is None

    def test_no_baseline_at_all_is_its_own_reason(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("2"))}
            ),
            projection=projection(),
            config=CONFIG,
        )
        assert evaluation.reason == REASON_NO_BASELINE

    def test_a_flat_baseline_refuses_to_measure_a_difference(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("2"))}
            ),
            projection=projection(revision("relative_volume_5m", mad="0")),
            config=CONFIG,
        )
        assert evaluation.reason == REASON_MAD_ZERO
        assert evaluation.severity is None

    def test_a_flat_baseline_with_the_same_reading_is_simply_calm(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("1"))}
            ),
            projection=projection(revision("relative_volume_5m", mad="0")),
            config=CONFIG,
        )
        assert evaluation.severity == Decimal("0.00")
        assert evaluation.evaluation_state is AnomalyEvaluationState.OK

    def test_a_disarmed_detector_says_so_and_never_fires(self) -> None:
        detector = detector_for(AnomalyType.CROSS_EXCHANGE_DIVERGENCE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector({}),
            projection=projection(),
            config=CONFIG,
        )
        assert evaluation.reason == REASON_DISABLED
        assert evaluation.detail == "single_exchange_until_m1b"
        assert evaluation.fires(detector) is False

    def test_a_missing_feature_key_is_not_a_zero(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector({}),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.reason == REASON_NO_FEATURE
        assert evaluation.current_value is None


class TestBatch:
    def test_every_armed_detector_is_evaluated_once_per_market(self) -> None:
        evaluations = evaluate_detectors(
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("2"))}
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        by_type = {evaluation.type: evaluation for evaluation in evaluations}
        assert len(by_type) == len(evaluations)
        assert by_type[AnomalyType.VOLUME_SPIKE].severity == Decimal("60.00")
        assert by_type[AnomalyType.CROSS_EXCHANGE_DIVERGENCE].reason == REASON_DISABLED

    def test_the_evaluation_records_the_versions_that_produced_it(self) -> None:
        evaluation = evaluate_detector(
            detector_for(AnomalyType.VOLUME_SPIKE),
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal("2"))}
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        wire = evaluation.as_wire()
        assert wire["detector_version"] == "VOLUME_SPIKE@v1"
        assert wire["normalization_version"] == "mad_piecewise_v1@v2"
        assert wire["feature"] == "relative_volume_5m"
        assert wire["feature_version"] == 1
