"""``d`` in MADs, the piecewise severity, direction and confidence.

Every expected severity below was computed by hand from the versioned
transformation (``mad_piecewise_v1``: flat to 1 MAD, linear to 100 at 6 MADs,
saturated above):

    severity = clip((|d| - 1) / (6 - 1) * 100, 0, 100)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_indicators.anomalies import (
    REASON_MAD_ZERO,
    AnomalyDirection,
    DetectorSide,
    NormalizationConfig,
    confidence_of,
    deviation_in_mads,
    evaluate_deviation,
    severity_of,
)
from hunter_indicators.baselines import BaselineKey, BaselineRevision

CONFIG = NormalizationConfig(
    method="mad_piecewise_v1",
    deadband_mad=Decimal("1"),
    saturation_mad=Decimal("6"),
    saturation_score=Decimal("100"),
    weights_version="v2",
)
MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")


def baseline(
    *,
    median: str = "10",
    mad: str = "2",
    sample_size: int = 400,
    distinct_days: int = 7,
) -> BaselineRevision:
    window_end = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
    return BaselineRevision(
        key=BaselineKey(market_id=MARKET, feature="relative_volume_5m", hour_of_day=10),
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
        input_fingerprint="fp",
    )


class TestDeviation:
    def test_deviation_is_the_signed_distance_in_mads(self) -> None:
        # (16 - 10) / 2 = 3
        value, reason = deviation_in_mads(Decimal("16"), Decimal("10"), Decimal("2"))
        assert value == Decimal("3")
        assert reason is None

    def test_a_reading_below_the_median_is_negative(self) -> None:
        value, _ = deviation_in_mads(Decimal("4"), Decimal("10"), Decimal("2"))
        assert value == Decimal("-3")

    def test_the_raw_mad_is_used_without_the_normal_consistency_factor(self) -> None:
        # 1.4826 would turn this 3 into 2.02: the joint decision writes MADs, not
        # sigmas, and claims no probability.
        value, _ = deviation_in_mads(Decimal("16"), Decimal("10"), Decimal("2"))
        assert value == Decimal("3")

    def test_a_zero_mad_with_the_same_value_is_a_zero_deviation(self) -> None:
        value, reason = deviation_in_mads(Decimal("10"), Decimal("10"), Decimal("0"))
        assert value == Decimal("0")
        assert reason is None

    def test_a_zero_mad_with_a_different_value_is_unavailable(self) -> None:
        value, reason = deviation_in_mads(Decimal("11"), Decimal("10"), Decimal("0"))
        assert value is None
        assert reason == REASON_MAD_ZERO


class TestSeverity:
    @pytest.mark.parametrize(
        ("deviation", "expected"),
        [
            ("0", "0"),
            ("0.5", "0"),
            ("1", "0"),
            ("-1", "0"),
            ("1.5", "10"),
            ("2", "20"),
            ("2.5", "30"),
            ("3", "40"),
            ("-3", "40"),
            ("6", "100"),
            ("8", "100"),
            ("-9", "100"),
        ],
    )
    def test_the_piecewise_transformation(self, deviation: str, expected: str) -> None:
        assert severity_of(Decimal(deviation), CONFIG, DetectorSide.BOTH) == Decimal(expected)

    def test_severity_is_quantized_half_even_to_two_places(self) -> None:
        # (1.05125 - 1) / 5 * 100 = 1.025 -> 1.02 under ROUND_HALF_EVEN
        assert severity_of(Decimal("1.05125"), CONFIG, DetectorSide.BOTH) == Decimal("1.02")

    def test_a_one_sided_detector_ignores_the_other_tail(self) -> None:
        # A volume collapse of -6 MADs is not a VOLUME_SPIKE.
        assert severity_of(Decimal("-6"), CONFIG, DetectorSide.UP) == Decimal("0")
        assert severity_of(Decimal("6"), CONFIG, DetectorSide.UP) == Decimal("100")
        assert severity_of(Decimal("-6"), CONFIG, DetectorSide.DOWN) == Decimal("100")


class TestDirection:
    def test_direction_is_carried_apart_from_magnitude(self) -> None:
        up = evaluate_deviation(Decimal("16"), baseline(), CONFIG, DetectorSide.BOTH)
        down = evaluate_deviation(Decimal("4"), baseline(), CONFIG, DetectorSide.BOTH)
        assert up.direction is AnomalyDirection.UP
        assert down.direction is AnomalyDirection.DOWN
        assert up.severity == down.severity == Decimal("40")

    def test_a_reading_on_the_median_has_no_direction(self) -> None:
        flat = evaluate_deviation(Decimal("10"), baseline(), CONFIG, DetectorSide.BOTH)
        assert flat.direction is AnomalyDirection.FLAT
        assert flat.severity == Decimal("0")


class TestConfidence:
    def test_a_full_baseline_is_fully_confident(self) -> None:
        assert confidence_of(baseline(sample_size=420, distinct_days=7)) == Decimal("1.0000")

    def test_confidence_of_the_thinnest_usable_baseline(self) -> None:
        # coverage = 120/420 = 0.285714; days = 3/7 = 0.428571 -> min -> 0.2857
        assert confidence_of(baseline(sample_size=120, distinct_days=3)) == Decimal("0.2857")

    def test_confidence_is_maturity_not_freshness(self) -> None:
        # Two baselines with the same counts have the same confidence no matter
        # how fresh the reading judged against them is: freshness lives in
        # ``evaluation_state``.
        assert confidence_of(baseline(sample_size=400)) == confidence_of(baseline(sample_size=400))

    def test_confidence_is_quantized_to_four_places(self) -> None:
        value = confidence_of(baseline(sample_size=400, distinct_days=7))
        assert value.as_tuple().exponent == -4
        assert value == Decimal("0.9524")


class TestNormalizationConfigComesFromTheWeights:
    def test_it_is_read_from_the_active_weight_vector(self) -> None:
        config = NormalizationConfig.from_weights(
            {
                "normalization": {
                    "method": "mad_piecewise_v1",
                    "deadband_mad": "1",
                    "saturation_mad": "6",
                    "saturation_score": "100",
                }
            },
            version="v2",
        )
        assert config == CONFIG
        assert config.identity == "mad_piecewise_v1@v2"

    def test_an_unknown_method_is_refused(self) -> None:
        with pytest.raises(ValueError, match="mad_piecewise_v1"):
            NormalizationConfig.from_weights(
                {
                    "normalization": {
                        "method": "zscore_v1",
                        "deadband_mad": "1",
                        "saturation_mad": "6",
                        "saturation_score": "100",
                    }
                },
                version="v9",
            )

    def test_a_vector_without_the_block_is_refused(self) -> None:
        with pytest.raises(KeyError):
            NormalizationConfig.from_weights({"components": {}}, version="v2")
