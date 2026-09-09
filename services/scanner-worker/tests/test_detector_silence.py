"""T3.46b: no detector may be armed and mute without saying so in the heartbeat.

The T3.46 study found three detectors (``ORDERBOOK_IMBALANCE``,
``OPEN_INTEREST_SPIKE``, ``TRADE_VELOCITY_SPIKE``) with zero rows in the whole
series and no entry in ``detectors_disarmed``, plus two types
(``SOCIAL_SPIKE``, ``WHALE_ACTIVITY``) that were not even in the roster. These
tests reproduce the *shapes* the VPS measured — an immature live baseline, a
book snapshot stamped after the coverage cut — and assert the heartbeat now
carries a reason for every one of them.

No IO: the whole path from a feature vector to the ``detectors_disarmed`` string
is pure plus one fake Redis hash, which is exactly what makes it worth asserting
character by character.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import (
    AnomalyType,
    BaselineSampling,
    BaselineSource,
    MarketType,
)
from hunter_indicators.anomalies import (
    DEFAULT_DETECTORS,
    evaluate_detectors,
    silence_reasons,
)
from hunter_indicators.baselines import (
    BaselineCut,
    BaselineKey,
    BaselineProjection,
    BaselineRevision,
    StoredBaseline,
)
from hunter_indicators.features import DEFAULT_REGISTRY, FeatureValue, FeatureVector, Reason
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.consumers import ConsumerHealth
from hunter_scanner_worker.health import CycleHealth, write_heartbeat
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .policies import build_policy

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-0000000000f1")
OBSERVED_AT = datetime(2026, 9, 8, 21, 0, tzinfo=UTC)
CUT = BaselineCut(as_of=OBSERVED_AT + timedelta(seconds=15), observation_ts=OBSERVED_AT)


class FakeHeartbeat:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        del key
        self.mapping = mapping

    async def expire(self, key: str, seconds: int) -> None:
        del key, seconds


class FakeRuntime:
    instance = "t346b"
    error_count = 0


def _revision(feature: str, *, sample_size: int, distinct_days: int) -> BaselineRevision:
    window_end = OBSERVED_AT - timedelta(hours=1)
    return BaselineRevision(
        key=BaselineKey(market_id=MARKET, feature=feature, hour_of_day=OBSERVED_AT.hour),
        feature_version=1,
        algo_version="median_mad_v1",
        sampling=BaselineSampling.PER_MINUTE,
        source=BaselineSource.LIVE,
        window_start=window_end - timedelta(days=7),
        window_end=window_end,
        available_at=window_end,
        median=Decimal("1.5"),
        mad=Decimal("0.5"),
        sample_size=sample_size,
        expected_size=420,
        distinct_days=distinct_days,
        coverage=(Decimal(sample_size) / Decimal(420)).quantize(Decimal("0.000001")),
        input_fingerprint=f"fp-{feature}",
    )


def _vector() -> FeatureVector:
    """The VPS shape, minute by minute: the tape and OI features are computed
    and the book is refused because the Redis snapshot carries the exchange's
    clock while the scanner cuts at ``covered_until`` (97,7 % of the readings on
    2026-09-08)."""
    return FeatureVector(
        exchange="binance",
        symbol="BTCUSDT",
        ts=OBSERVED_AT,
        feature_set_version=DEFAULT_REGISTRY.feature_set_version,
        values={
            "trade_velocity_1m": FeatureValue.ok("trade_velocity_1m", Decimal("9")),
            "open_interest_change_1h": FeatureValue.ok("open_interest_change_1h", Decimal("0.04")),
            "orderbook_imbalance_20": FeatureValue.unavailable(
                "orderbook_imbalance_20", Reason.AFTER_CUT
            ),
        },
    )


def _evaluations() -> tuple[tuple[str, str], ...]:
    projection = BaselineProjection(
        [
            StoredBaseline(
                baseline_id=uuid.UUID(int=MARKET.int + index),
                revision=_revision(feature, sample_size=61, distinct_days=2),
            )
            for index, feature in enumerate(("trade_velocity_1m", "open_interest_change_1h"))
        ],
        cut=CUT,
        gate=build_policy().gate,
    )
    return silence_reasons(
        evaluate_detectors(
            market_id=MARKET,
            vector=_vector(),
            projection=projection,
            config=build_policy().normalization,
            detectors=DEFAULT_DETECTORS,
        )
    )


def test_the_three_mute_detectors_of_t346_now_declare_their_reason() -> None:
    reasons = dict(_evaluations())
    assert reasons[AnomalyType.TRADE_VELOCITY_SPIKE.value] == "baselines_under_construction"
    assert reasons[AnomalyType.OPEN_INTEREST_SPIKE.value] == "baselines_under_construction"
    assert reasons[AnomalyType.ORDERBOOK_IMBALANCE.value] == "feature_after_cut"


def test_no_type_in_the_enum_is_left_silent_without_a_reason() -> None:
    """The Radar coverage strip's two classes: after this task the "silencioso
    sem motivo" class must be empty for a market that fired nothing."""
    reasons = dict(_evaluations())
    assert set(reasons) == {kind.value for kind in AnomalyType}


async def test_the_heartbeat_string_carries_every_reason_with_its_count() -> None:
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(),
        policy=policy,
        registry=MarketRegistry(exchange="binance"),
        state=ScannerState(),
    )
    scanner.cache = BaselineCache(gate=policy.gate)
    market = scanner.state.ensure(
        MarketRef(
            market_id=MARKET,
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
        )
    )
    market.disarmed = _evaluations()

    redis = FakeHeartbeat()
    await write_heartbeat(
        redis,  # type: ignore[arg-type]
        FakeRuntime(),  # type: ignore[arg-type]
        scanner,
        CycleHealth(),
        ConsumerHealth(started_at=OBSERVED_AT),
    )

    published = redis.mapping["detectors_disarmed"]
    entries = dict(entry.rsplit("=", 1)[0].split(":", 1) for entry in published.split(",") if entry)
    assert entries["TRADE_VELOCITY_SPIKE"] == "baselines_under_construction"
    assert entries["ORDERBOOK_IMBALANCE"] == "feature_after_cut"
    assert entries["SOCIAL_SPIKE"] == "feature_not_implemented"
    assert entries["WHALE_ACTIVITY"] == "feature_not_implemented"
    assert entries["LIQUIDATION_CLUSTER"] == "feature_not_implemented"
    assert entries["CROSS_EXCHANGE_DIVERGENCE"] == "single_exchange_until_m1b"
    assert set(entries) == {kind.value for kind in AnomalyType}
    assert published == ",".join(sorted(published.split(",")))
