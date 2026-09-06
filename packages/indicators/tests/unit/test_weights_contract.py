"""The thresholds this package reads really are the ones the release ships.

Nothing in ``baselines``/``anomalies``/``stage`` may carry a default threshold:
the gate, the MAD normalisation and the stage parameters all come from the active
``opportunity_weights`` vector. This file loads the vector **from the seed
module itself** (by path — ``infra/scripts`` is not an installed package, the
same way ``packages/core/tests/integration/test_schema_seed_and_partitions.py``
does it) and feeds it to the three readers. If a future profile renames a key,
this fails here instead of in the scanner.

It also closes the replay loop the joint decision asks for: the deviation
computed today from the ``baseline_ids`` an envelope recorded yesterday is the
same number, even though a newer revision has been published since.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from hunter_core.domain.enums import AnomalyType, BaselineSource
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
    BaselineRequest,
    BaselineRevision,
    InMemoryBaselineStore,
    Observation,
    compute_revision,
)
from hunter_indicators.features import DEFAULT_REGISTRY, FeatureValue, FeatureVector
from hunter_indicators.stage import StageThresholds

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "infra" / "scripts"
MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")


def _load_seed_reference() -> ModuleType:
    """``infra/scripts/seed_reference.py``, loaded by path (not a package)."""
    path = SCRIPTS_DIR / "seed_reference.py"
    if not path.exists():  # pragma: no cover - the repo always ships it
        pytest.skip(f"{path} is not present")
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("seed_reference_for_tests", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def active_weights() -> tuple[str, dict[str, Any]]:
    module = _load_seed_reference()
    version: str = module.ACTIVE_WEIGHTS_VERSION
    for name, weights, _description in module.OPPORTUNITY_WEIGHTS:
        if name == version:
            return version, weights
    raise AssertionError(f"the active version {version} is not among the shipped vectors")


class TestTheShippedVectorFeedsEveryReader:
    def test_the_baseline_gate_is_the_shipped_one(self) -> None:
        _version, weights = active_weights()
        gate = BaselineGate.from_weights(weights)
        assert gate.min_distinct_days == 3
        assert gate.min_valid_observations == 120
        assert gate.expected_size == 420

    def test_the_normalization_is_the_shipped_one(self) -> None:
        version, weights = active_weights()
        config = NormalizationConfig.from_weights(weights, version=version)
        assert config.deadband_mad == Decimal("1")
        assert config.saturation_mad == Decimal("6")
        assert config.saturation_score == Decimal("100")
        assert config.identity == f"mad_piecewise_v1@{version}"

    def test_the_stage_thresholds_are_the_shipped_ones(self) -> None:
        version, weights = active_weights()
        thresholds = StageThresholds.from_weights(weights, version=version)
        assert thresholds.r_early_max == Decimal("1.5")
        assert thresholds.r_developing_max == Decimal("4")
        assert thresholds.confirmations == 2
        assert thresholds.weights_version == version

    def test_the_profile_declares_the_atr_this_package_uses(self) -> None:
        # The stage is defined over Wilder(14) on 15-minute bars; T2.2's
        # ``atr_14_pct`` is exactly that, and a drift between the two would make
        # ``r`` mean something else.
        _version, weights = active_weights()
        assert weights["stage"]["atr_period"] == 14
        assert weights["stage"]["atr_bar_minutes"] == 15
        definition = DEFAULT_REGISTRY.get("atr_14_pct").definition
        assert definition.params["period"] == 14
        assert definition.params["timeframe"] == "15m"


class TestReplayWithRecordedBaselineIds:
    """Recomputing tomorrow reproduces today's deviation, from the ids recorded."""

    def revision_of(
        self, low: str, high: str, *, days: list[datetime], gate: BaselineGate, feature: str
    ):
        """Three hour-10 buckets of 60 alternating minutes — over the gate, by hand.

        180 observations, half ``low`` and half ``high``: the median is the
        midpoint and the MAD is half the gap, both checkable on paper.
        """
        observations = tuple(
            Observation(
                ts=day + timedelta(minutes=minute),
                value=Decimal(low if minute % 2 == 0 else high),
            )
            for day in days
            for minute in range(60)
        )
        window_end = days[-1] + timedelta(minutes=60)  # half-open: 14:00..14:59 inside
        revision = compute_revision(
            key=BaselineKey(market_id=MARKET, feature=feature, hour_of_day=10),
            feature_version=1,
            source=BaselineSource.LIVE,
            window_start=days[0],
            window_end=window_end,
            available_at=window_end + timedelta(minutes=1),
            observations=observations,
            expected_size=gate.expected_size,
        )
        assert isinstance(revision, BaselineRevision)
        return revision

    async def test_yesterdays_deviation_is_reproduced_from_yesterdays_ids(self) -> None:
        version, weights = active_weights()
        config = NormalizationConfig.from_weights(weights, version=version)
        gate = BaselineGate.from_weights(weights)
        detector = detector_for(AnomalyType.VOLUME_SPIKE)
        feature = detector.feature
        store = InMemoryBaselineStore()

        early_days = [datetime(2026, 9, day, 10, 0, tzinfo=UTC) for day in (4, 5, 6)]
        stored = await store.append(
            [self.revision_of("1", "1.5", days=early_days, gate=gate, feature=feature)]
        )
        observed_at = datetime(2026, 9, 7, 10, 30, tzinfo=UTC)
        cut = BaselineCut(as_of=observed_at + timedelta(seconds=30), observation_ts=observed_at)
        projection = BaselineProjection(stored, cut=cut, gate=gate)
        vector = FeatureVector(
            exchange="binance",
            symbol="BTCUSDT",
            ts=observed_at,
            feature_set_version=DEFAULT_REGISTRY.feature_set_version,
            values={feature: FeatureValue.ok(feature, Decimal("3"))},
        )
        first = evaluate_detector(
            detector, market_id=MARKET, vector=vector, projection=projection, config=config
        )
        # median 1.25, MAD 0.25 -> d = (3 - 1.25) / 0.25 = 7 -> saturated severity
        assert first.baseline == Decimal("1.2500000000")
        assert first.deviation == Decimal("7")
        assert first.severity == Decimal("100.00")

        # A newer revision lands the next day with another median.
        later_days = [datetime(2026, 9, day, 10, 0, tzinfo=UTC) for day in (5, 6, 7)]
        newer = await store.append(
            [self.revision_of("9", "9.5", days=later_days, gate=gate, feature=feature)]
        )
        tomorrow = datetime(2026, 9, 8, 10, 30, tzinfo=UTC)
        newest = await store.load(
            [BaselineRequest(MARKET, feature, 1, 10)],
            cut=BaselineCut(as_of=tomorrow + timedelta(seconds=30), observation_ts=tomorrow),
        )
        assert newest[0].baseline_id == newer[0].baseline_id
        assert newest[0].baseline_id != first.baseline_ids[0]

        # The replay reads the ids the first evaluation recorded and reproduces
        # its numbers, not the newest baseline's.
        replayed_entries = await store.load_ids(list(first.baseline_ids))
        replay_projection = BaselineProjection(replayed_entries, cut=cut, gate=gate)
        second = evaluate_detector(
            detector,
            market_id=MARKET,
            vector=vector,
            projection=replay_projection,
            config=config,
        )
        assert second.deviation == first.deviation
        assert second.severity == first.severity
        assert second.baseline == first.baseline
        assert second.baseline_ids == first.baseline_ids
