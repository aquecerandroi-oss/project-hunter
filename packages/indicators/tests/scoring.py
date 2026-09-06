"""Shared fixtures for the T2.4 scorer tests: vectors, baselines, stage, regime.

Built from the same public types the scanner will use, so a test that passes here
is a statement about the contract and not about a private helper.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    BaselineSampling,
    BaselineSource,
    OpportunityStage,
    TradeDirection,
)
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.anomalies import (
    AnomalyDirection,
    AnomalyState,
    NormalizationConfig,
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
from hunter_indicators.regime import (
    Breadth,
    RegimeObservation,
    RegimeState,
    RegimeThresholds,
    RegimeTrend,
    RegimeVolatility,
    VolatilityReference,
    classify_regime,
)
from hunter_indicators.stage import StageDecision, StageState, StageThresholds

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
BASELINE_ID = uuid.UUID("0199a1d0-0000-7000-8000-0000000000aa")
REGIME_ID = uuid.UUID("0199a1d0-0000-7000-8000-0000000000bb")
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
"""``deadband 1``, ``saturation 6``: severity = clip((|d| - 1) / 5 * 100, 0, 100)."""


def _coverage(sample_size: int) -> Decimal:
    """Under ``CONTEXT``, like ``compute_revision`` — a fixture that rounded with
    the ambient precision would break the tests that *change* it."""
    with localcontext(CONTEXT):
        return (Decimal(sample_size) / Decimal(420)).quantize(Decimal("0.000001"))


def revision(
    feature: str,
    *,
    median: str = "1",
    mad: str = "0.25",
    sample_size: int = 400,
    distinct_days: int = 7,
) -> BaselineRevision:
    """A mature baseline: median 1, MAD 0.25, so ``x = 2`` sits at 4 MADs."""
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
        coverage=_coverage(sample_size),
        input_fingerprint=f"fp-{feature}",
    )


def projection(*revisions: BaselineRevision) -> BaselineProjection:
    entries = [
        StoredBaseline(baseline_id=uuid.UUID(int=BASELINE_ID.int + index), revision=item)
        for index, item in enumerate(revisions)
    ]
    return BaselineProjection(entries, cut=CUT, gate=GATE)


def baselines_for(features: Sequence[str], **kwargs: Any) -> BaselineProjection:
    return projection(*(revision(feature, **kwargs) for feature in features))


def ok(key: str, value: str) -> FeatureValue:
    return FeatureValue.ok(key, Decimal(value))


def degraded(key: str, value: str) -> FeatureValue:
    return FeatureValue.ok(key, Decimal(value)).degraded_to(Quality.DEGRADED, Reason.STALE_INPUT)


def missing(key: str, reason: Reason = Reason.WARMUP) -> FeatureValue:
    return FeatureValue.unavailable(key, reason)


def vector(values: Mapping[str, FeatureValue], *, ts: datetime = OBSERVED_AT) -> FeatureVector:
    return FeatureVector(
        exchange="binance",
        symbol="BTCUSDT",
        ts=ts,
        feature_set_version=DEFAULT_REGISTRY.feature_set_version,
        values=dict(values),
    )


def anomaly(
    kind: AnomalyType,
    severity: str,
    *,
    state: AnomalyEvaluationState = AnomalyEvaluationState.OK,
    status: AnomalyStatus = AnomalyStatus.ACTIVE,
    confidence: str = "0.9000",
) -> AnomalyState:
    return AnomalyState(
        market_id=MARKET,
        type=kind,
        status=status,
        evaluation_state=state,
        detected_at=OBSERVED_AT - timedelta(minutes=5),
        observation_ts=OBSERVED_AT,
        severity=Decimal(severity),
        confidence=Decimal(confidence),
        baseline=Decimal("1"),
        current_value=Decimal("4"),
        deviation=Decimal("12"),
        direction=AnomalyDirection.UP,
        unit="ratio",
        detector_version=f"{kind.value}@v1",
        normalization_version="mad_piecewise_v1@v2",
    )


STAGE_THRESHOLDS = StageThresholds(
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


def stage_decision(
    stage: OpportunityStage,
    *,
    direction: TradeDirection = TradeDirection.LONG,
    ts: datetime = OBSERVED_AT,
) -> StageDecision:
    """A published stage, as the T2.3 classifier would hand it over."""
    state_out = StageState(
        stage=stage,
        basis="ratio",
        candidate=stage,
        confirmations=0,
        last_observation_ts=ts,
        direction=direction,
        candidate_direction=direction,
    )
    return StageDecision(
        stage=stage,
        candidate=stage,
        observation_ts=ts,
        state_in=state_out,
        state_out=state_out,
        thresholds_version="v2",
        basis="ratio",
        direction=direction,
        r=Decimal("1.2"),
    )


def regime_decision(
    *,
    trend: RegimeTrend = RegimeTrend.BULL,
    volatility: RegimeVolatility = RegimeVolatility.NORMAL,
    ts: datetime = OBSERVED_AT,
):
    """A published regime, built by running the real classifier to its transition."""
    thresholds = RegimeThresholds()
    reference = VolatilityReference(
        median=Decimal("0.001"), samples=600, distinct_days=25, window_days=30, usable=True
    )
    volatility_value = {
        RegimeVolatility.HIGH: "0.003",
        RegimeVolatility.NORMAL: "0.001",
        RegimeVolatility.LOW: "0.0004",
    }[volatility]
    returns = {
        RegimeTrend.BULL: ("0.06", "0.12"),
        RegimeTrend.BEAR: ("-0.06", "-0.12"),
        RegimeTrend.SIDEWAYS: ("0", "0"),
    }[trend]
    breadth = Breadth(
        fraction=Decimal("0.7"),
        coverage=Decimal("1"),
        universe_size=10,
        usable_markets=10,
        advancing=7,
        usable=True,
    )
    state = RegimeState()
    decision = None
    for index in range(thresholds.confirmations):
        decision = classify_regime(
            state=state,
            observation=RegimeObservation(
                observation_ts=ts - (thresholds.confirmations - 1 - index) * timedelta(minutes=1),
                return_4h=Decimal(returns[0]),
                return_1d=Decimal(returns[1]),
                atr_pct=Decimal("0.02"),
                volatility=Decimal(volatility_value),
            ),
            reference=reference,
            breadth=breadth,
            thresholds=thresholds,
        )
        state = decision.state_out
    assert decision is not None
    return decision


def pending_regime_decision(*, ts: datetime = OBSERVED_AT):
    """A published bull regime with one bear reading against it.

    The hysteresis holds the pair and the classifier reports **no** confidence
    for the minute (``state_out.pair != reading.pair``), which is the real shape
    of the case the scorer has to refuse — built by running the classifier into
    it rather than by writing ``confidence=None`` on a decision by hand (Astra,
    cross review of these fixes).
    """
    thresholds = RegimeThresholds()
    published = regime_decision(ts=ts - timedelta(minutes=1))
    return classify_regime(
        state=published.state_out,
        observation=RegimeObservation(
            observation_ts=ts,
            return_4h=Decimal("-0.06"),
            return_1d=Decimal("-0.12"),
            atr_pct=Decimal("0.02"),
            volatility=Decimal("0.001"),
        ),
        reference=VolatilityReference(
            median=Decimal("0.001"), samples=600, distinct_days=25, window_days=30, usable=True
        ),
        breadth=Breadth(
            fraction=Decimal("0.7"),
            coverage=Decimal("1"),
            universe_size=10,
            usable_markets=10,
            advancing=7,
            usable=True,
        ),
        thresholds=thresholds,
    )


# --- the weight profile the arithmetic tests use ------------------------------
#
# A copy of the shipped v2 vector, pinned here so a scorer test states the
# arithmetic and not the profile. ``test_weights_contract.py`` compares it
# against ``infra/scripts/seed_reference.py``: if the release ever ships other
# numbers under this name, that contract test fails, not thirty arithmetic ones.

TEST_WEIGHTS: dict[str, object] = {
    "components": {
        "momentum": "0.20",
        "volume": "0.20",
        "order_flow": "0.15",
        "liquidity": "0.10",
        "derivatives": "0.10",
        "market_regime": "0.10",
        "anomalies": "0.05",
        "agent_consensus": "0.00",
        "external_intelligence": "0.00",
    },
    "early_movement": {"magnitude": "10", "values": [-1, 0, 1]},
    "status": {
        "watching_min": "40",
        "hot_min": "75",
        "entry_candidate_min": "80",
        "anomaly_severity_min": "60",
    },
    "expiry": {"score_floor": "40", "below_floor_minutes": 15},
    "precision": {
        "score_decimals": 2,
        "confidence_decimals": 4,
        "component_decimals": 4,
        "rounding": "ROUND_HALF_EVEN",
    },
}
