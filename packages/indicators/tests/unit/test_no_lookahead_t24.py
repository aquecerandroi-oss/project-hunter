"""Nothing T2.4 decides may move when the candle still forming moves.

The same violent mutation T2.2 and T2.3 use — the forming minute doubles in
price and in volume — carried up to the two things this task adds: the regime
statistics computed from persisted candles, and the score built on the vector.
The ``_live`` features **do** change in every case below, which is what makes the
absence of a change in the score and in the regime a proof rather than a
coincidence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.anomalies import NormalizationConfig
from hunter_indicators.baselines import (
    BaselineCut,
    BaselineGate,
    BaselineKey,
    BaselineProjection,
    BaselineRevision,
    StoredBaseline,
)
from hunter_indicators.features import FeatureVector, build_context, compute_features
from hunter_indicators.opportunity import (
    COMPONENTS,
    ScoreContext,
    WeightProfile,
    score_opportunity,
)
from hunter_indicators.regime import (
    RegimeThresholds,
    hourly_samples,
    return_over,
    trailing_volatility,
    volatility_reference,
)
from packages.indicators.tests.factories import EXCHANGE, MINUTE, SYMBOL, candle
from packages.indicators.tests.scoring import TEST_WEIGHTS

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
PROFILE = WeightProfile.from_weights(TEST_WEIGHTS, version="v2-test")
THRESHOLDS = RegimeThresholds()
MINUTES = 400
CUT = ORIGIN + MINUTES * MINUTE + timedelta(seconds=30)


def history(minutes: int = MINUTES) -> list[NormalizedCandle]:
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


def forming(close: str, volume: str) -> NormalizedCandle:
    return candle(
        ORIGIN + MINUTES * MINUTE,
        close=Decimal(close),
        volume=Decimal(volume),
        is_final=False,
        event_ts=CUT,
    )


def vector_with(close: str, volume: str) -> FeatureVector:
    candles = [*history(), forming(close, volume)]
    ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=CUT, candles=candles)
    return compute_features(ctx).vector


def projection_for(vector: FeatureVector) -> BaselineProjection:
    window_end = vector.ts - timedelta(hours=1)
    entries: list[StoredBaseline] = []
    for index, feature in enumerate(sorted(vector.values)):
        revision = BaselineRevision(
            key=BaselineKey(market_id=MARKET, feature=feature, hour_of_day=vector.ts.hour),
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
            input_fingerprint=f"fp-{feature}",
        )
        entries.append(
            StoredBaseline(baseline_id=uuid.UUID(int=BASELINE_ID.int + index), revision=revision)
        )
    return BaselineProjection(
        entries,
        cut=BaselineCut(as_of=vector.ts, observation_ts=vector.ts),
        gate=GATE,
    )


def score_of(vector: FeatureVector):
    return score_opportunity(
        ScoreContext(
            market_id=MARKET,
            vector=vector,
            projection=projection_for(vector),
            config=CONFIG,
            profile=PROFILE,
            anomalies=[],
        )
    )


class TestTheScoreIgnoresTheFormingMinute:
    def test_the_mutation_really_does_move_the_live_features(self) -> None:
        quiet = vector_with("100", "10")
        violent = vector_with("200", "9999")
        live = [key for key in quiet.values if key.endswith("_live")]
        assert live
        assert any(quiet.number(key) != violent.number(key) for key in live)

    def test_the_score_does_not_change(self) -> None:
        quiet = score_of(vector_with("100", "10"))
        violent = score_of(vector_with("200", "9999"))
        assert quiet.score == violent.score
        assert canonical_json(quiet.decomposition()) == canonical_json(violent.decomposition())

    def test_no_component_declares_a_live_input(self) -> None:
        for definition in COMPONENTS:
            for item in definition.inputs:
                assert not item.feature.endswith("_live"), item.feature


class TestTheRegimeIgnoresTheFormingMinute:
    def test_the_return_does_not_change(self) -> None:
        closed = history()
        assert return_over(closed, minutes=60, as_of=CUT) == return_over(
            [*closed, forming("200", "9999")], minutes=60, as_of=CUT
        )

    def test_the_trailing_volatility_does_not_change(self) -> None:
        closed = history()
        quiet = trailing_volatility(closed, as_of=CUT, thresholds=THRESHOLDS)
        violent = trailing_volatility(
            [*closed, forming("200", "9999")], as_of=CUT, thresholds=THRESHOLDS
        )
        assert quiet is not None
        assert quiet == violent

    def test_the_hourly_reference_does_not_change(self) -> None:
        closed = history()
        thresholds = RegimeThresholds(volatility_min_samples=1, volatility_min_distinct_days=1)
        quiet = volatility_reference(
            hourly_samples(closed, until=CUT, thresholds=thresholds), thresholds
        )
        violent = volatility_reference(
            hourly_samples([*closed, forming("200", "9999")], until=CUT, thresholds=thresholds),
            thresholds,
        )
        assert quiet.median is not None
        assert quiet == violent
