"""Why a detector produced nothing — the T3.46b rule: never silent without a reason.

Each test names a *class* of muteness the T3.46 study measured on the VPS and
asserts the vocabulary the heartbeat publishes for it. The point is never the
string for its own sake: it is that an operator reading the Radar coverage strip
can tell "the market is calm" from "this detector cannot fire at all today".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    BaselineSampling,
    BaselineSource,
)
from hunter_indicators.anomalies import (
    REASON_BASELINE_ABSENT,
    REASON_BASELINES_UNDER_CONSTRUCTION,
    REASON_DATA_DEGRADED,
    AnomalyState,
    NormalizationConfig,
    default_detectors,
    detector_for,
    evaluate_detector,
    evaluate_detectors,
    silence_reason,
    silence_reasons,
)
from hunter_indicators.baselines import (
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
        input_fingerprint=f"fp-{feature}-{sample_size}-{distinct_days}",
    )


def projection(*revisions: BaselineRevision) -> BaselineProjection:
    entries = [
        StoredBaseline(baseline_id=uuid.UUID(int=BASELINE_ID.int + index), revision=item)
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


class TestTheRosterCoversEveryType:
    def test_every_anomaly_type_in_the_enum_has_a_registered_detector(self) -> None:
        """T3.46b: ``SOCIAL_SPIKE`` and ``WHALE_ACTIVITY`` were mute *and*
        absent from the roster, so they could never even be reported."""
        assert {detector.type for detector in default_detectors()} == set(AnomalyType)

    def test_the_phase_three_types_are_disarmed_with_a_declared_reason(self) -> None:
        for kind in (AnomalyType.SOCIAL_SPIKE, AnomalyType.WHALE_ACTIVITY):
            detector = detector_for(kind)
            assert detector.enabled is False
            assert detector.disabled_reason == "feature_not_implemented"


class TestOneEvaluation:
    def test_an_immature_baseline_reads_as_baselines_under_construction(self) -> None:
        """The measured cause of ``TRADE_VELOCITY_SPIKE`` and
        ``OPEN_INTEREST_SPIKE`` being mute on the VPS: the feature is computed,
        the detector is armed, and no bucket passes the v2 gate."""
        detector = detector_for(AnomalyType.TRADE_VELOCITY_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector({"trade_velocity_1m": FeatureValue.ok("trade_velocity_1m", Decimal(9))}),
            projection=projection(revision("trade_velocity_1m", sample_size=61, distinct_days=2)),
            config=CONFIG,
        )
        assert evaluation.evaluation_state is AnomalyEvaluationState.UNKNOWN
        assert silence_reason(evaluation) == REASON_BASELINES_UNDER_CONSTRUCTION

    def test_a_book_stamped_after_the_cut_reads_as_feature_after_cut(self) -> None:
        """The measured cause of ``ORDERBOOK_IMBALANCE``: the Redis book carries
        the exchange's clock and the scanner cuts at ``covered_until``, so the
        snapshot is in the future of its own evaluation and no value exists."""
        detector = detector_for(AnomalyType.ORDERBOOK_IMBALANCE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {
                    "orderbook_imbalance_20": FeatureValue.unavailable(
                        "orderbook_imbalance_20", Reason.AFTER_CUT
                    )
                }
            ),
            projection=projection(revision("orderbook_imbalance_20")),
            config=CONFIG,
        )
        assert silence_reason(evaluation) == "feature_after_cut"

    def test_no_baseline_at_all_is_not_the_same_as_an_immature_one(self) -> None:
        detector = detector_for(AnomalyType.TRADE_VELOCITY_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector({"trade_velocity_1m": FeatureValue.ok("trade_velocity_1m", Decimal(9))}),
            projection=projection(),
            config=CONFIG,
        )
        assert silence_reason(evaluation) == REASON_BASELINE_ABSENT

    def test_a_disarmed_detector_reports_its_own_capability_reason(self) -> None:
        detector = detector_for(AnomalyType.LIQUIDATION_CLUSTER)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector({}),
            projection=projection(),
            config=CONFIG,
        )
        assert silence_reason(evaluation) == "feature_not_implemented"

    def test_a_degraded_reading_is_declared_degraded_not_missing(self) -> None:
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {
                    "relative_volume_5m": FeatureValue(
                        key="relative_volume_5m",
                        value=Decimal(2),
                        quality=Quality.DEGRADED,
                        reason=Reason.STALE_INPUT,
                    )
                }
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.evaluation_state is AnomalyEvaluationState.STALE
        assert silence_reason(evaluation) == REASON_DATA_DEGRADED

    def test_a_believed_reading_is_never_reported_as_mute_even_at_severity_zero(self) -> None:
        """A calm market is the one silence that is an *answer*: the detector
        looked, produced a number and the number was 0. Reporting that as a
        disarmed detector would turn "nothing is happening" into an alarm."""
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        evaluation = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector(
                {"relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal(1))}
            ),
            projection=projection(revision("relative_volume_5m")),
            config=CONFIG,
        )
        assert evaluation.severity == Decimal("0.00")
        assert silence_reason(evaluation) is None


class TestOneMarket:
    def test_every_detector_that_cannot_fire_is_named_exactly_once(self) -> None:
        evaluations = evaluate_detectors(
            market_id=MARKET,
            vector=vector(
                {
                    "relative_volume_5m": FeatureValue.ok("relative_volume_5m", Decimal(1)),
                    "trade_velocity_1m": FeatureValue.ok("trade_velocity_1m", Decimal(9)),
                }
            ),
            projection=projection(
                revision("relative_volume_5m"),
                revision("trade_velocity_1m", sample_size=61, distinct_days=2),
            ),
            config=CONFIG,
        )
        reasons = dict(silence_reasons(evaluations))
        assert AnomalyType.VOLUME_SPIKE.value not in reasons  # believed, calm
        assert reasons[AnomalyType.TRADE_VELOCITY_SPIKE.value] == (
            REASON_BASELINES_UNDER_CONSTRUCTION
        )
        assert reasons[AnomalyType.SOCIAL_SPIKE.value] == "feature_not_implemented"
        assert reasons[AnomalyType.LIQUIDATION_CLUSTER.value] == "feature_not_implemented"
        assert len(reasons) == len(set(reasons))
        assert sorted(reasons) == [pair[0] for pair in silence_reasons(evaluations)]

    def test_an_open_anomaly_is_not_a_mute_detector(self) -> None:
        """A market whose ``VOLUME_SPIKE`` is open and whose current reading is
        blind is *producing*: the episode is the output. Reporting it as
        disarmed would hide a live anomaly behind a warm-up label."""
        evaluations = evaluate_detectors(
            market_id=MARKET,
            vector=vector({}),
            projection=projection(),
            config=CONFIG,
        )
        open_state = AnomalyState(
            market_id=MARKET,
            type=AnomalyType.VOLUME_SPIKE,
            status=AnomalyStatus.ACTIVE,
            evaluation_state=AnomalyEvaluationState.UNKNOWN,
            detected_at=OBSERVED_AT - timedelta(minutes=5),
            observation_ts=OBSERVED_AT,
            severity=Decimal("70"),
        )
        blind = dict(silence_reasons(evaluations))
        assert blind[AnomalyType.VOLUME_SPIKE.value] == "feature_not_in_vector"
        producing = dict(silence_reasons(evaluations, states=(open_state,)))
        assert AnomalyType.VOLUME_SPIKE.value not in producing

    def test_the_vocabulary_never_leaks_an_unmapped_reason(self) -> None:
        """Every reason a detector can carry has an operator word. A new one
        must be added deliberately, not appear as raw internals on the page."""
        evaluations = evaluate_detectors(
            market_id=MARKET, vector=vector({}), projection=projection(), config=CONFIG
        )
        for _, reason in silence_reasons(evaluations):
            assert reason
            assert reason.islower()
            assert " " not in reason
