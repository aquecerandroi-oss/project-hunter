"""The ten v1 detectors: what each reads, which tail it watches, its thresholds.

A detector is a **declaration**, not a class hierarchy: one feature, one side,
four thresholds and a version. Everything that decides whether an anomaly exists
is in the declaration, so the anomaly can name the exact policy that produced it
(``detector_version``) and a replay can reproduce it. Changing a threshold is a
new ``version`` string, never an edit of the old one — the same rule
``FeatureDefinition`` follows.

Thresholds are declared here rather than read from ``opportunity_weights``
because v2 of that vector has no block for detectors (``infra/scripts/
seed_reference.py``), and inventing one would mean editing the seed from inside
this task. What v2 *does* own — the MAD normalisation — is read from it, and the
evaluation records both versions: the severity depends on the pair, not on the
detector alone (Astra, T2.3 design review, item 3).

**Two detectors are registered and disarmed**, with the reason machine-readable:

- ``CROSS_EXCHANGE_DIVERGENCE`` needs a second exchange (M1b);
- ``LIQUIDATION_CLUSTER`` needs a ``liquidation_pressure_1h`` feature that the
  T2.2 set does not contain — liquidations are not in ``MarketContext`` v1
  (``.claude/state/notes-T2.2.md`` §11). Registering it silently pointed at some
  other feature would be a fake detector; leaving it out would hide the gap.

Value choices worth stating, because the joint decision does not fix them: the
severity floor to fire is 40 (= 3 MADs) and to keep holding 20 (= 2 MADs); the
resolution window is the five minutes of ``docs/PIPELINE.md`` §3 — proven by five
distinct readings, not by a clock alone — and the absolute expiry its four hours. They are policy, not calibration — no historical study
backs the 3 MADs, and the version string exists so a study can replace them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import AnomalyType
from hunter_indicators.anomalies.severity import DetectorSide
from hunter_indicators.features.definitions import FeatureRegistry
from hunter_indicators.features.engine import DEFAULT_REGISTRY

DETECTOR_VERSION = "v1"
"""The version of this whole policy set. Any threshold change is a new one."""

FIRE_MIN_SEVERITY = Decimal("40")
"""3 MADs under ``mad_piecewise_v1`` — declared policy, not a fitted number."""

HOLD_MIN_SEVERITY = Decimal("20")
"""2 MADs: the anomaly stays open while the market is still unusual, so a reading
oscillating around the firing line does not flap the row open and shut."""

RESOLVE_AFTER = timedelta(minutes=5)
EXPIRE_AFTER = timedelta(hours=4)

RESOLVE_MIN_READINGS = 5
"""How many readings under the holding line *prove* those five minutes.

The scanner samples once a minute (``BaselineSampling.PER_MINUTE``), so five
minutes of calm is five distinct readings that were actually below the line.
Elapsed time alone would let two readings seven minutes apart close an anomaly
nobody watched — the same hole the ``no_data``/``stale`` zeroing already closes
for the readings we know are missing (cross review, nice-to-have d)."""

REASON_DISABLED = "detector_disabled"
REASON_NO_FEATURE = "feature_not_in_vector"


@dataclass(frozen=True, slots=True)
class DetectorDefinition:
    """One detector, fully described by data."""

    type: AnomalyType
    version: str
    feature: str
    feature_version: int
    side: DetectorSide
    unit: str
    description: str
    fire_min_severity: Decimal = FIRE_MIN_SEVERITY
    hold_min_severity: Decimal = HOLD_MIN_SEVERITY
    resolve_after: timedelta = RESOLVE_AFTER
    resolve_min_readings: int = RESOLVE_MIN_READINGS
    expire_after: timedelta = EXPIRE_AFTER
    enabled: bool = True
    disabled_reason: str | None = None

    def __post_init__(self) -> None:
        if self.enabled and self.disabled_reason is not None:
            raise ValueError(f"{self.type}: an armed detector carries no disabled reason")
        if not self.enabled and not self.disabled_reason:
            raise ValueError(f"{self.type}: a disarmed detector must say why")
        if self.hold_min_severity > self.fire_min_severity:
            raise ValueError(f"{self.type}: holding must not be stricter than firing")
        if self.resolve_min_readings < 1:
            raise ValueError(f"{self.type}: resolving needs at least one proven reading")

    @property
    def identity(self) -> str:
        """What the anomaly stores in ``detector_version``."""
        return f"{self.type.value}@{self.version}"

    def as_wire(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "version": self.version,
            "feature": self.feature,
            "feature_version": self.feature_version,
            "side": self.side.value,
            "unit": self.unit,
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "thresholds": {
                "fire_min_severity": self.fire_min_severity,
                "hold_min_severity": self.hold_min_severity,
                "resolve_after_s": int(self.resolve_after.total_seconds()),
                "resolve_min_readings": self.resolve_min_readings,
                "expire_after_s": int(self.expire_after.total_seconds()),
            },
        }


_SPECS: tuple[tuple[AnomalyType, str, DetectorSide, str, str], ...] = (
    (
        AnomalyType.VOLUME_SPIKE,
        "relative_volume_5m",
        DetectorSide.UP,
        "ratio",
        "Volume of the last five minutes far above what this market usually trades at this hour.",
    ),
    (
        AnomalyType.PRICE_ACCELERATION,
        "momentum_acceleration",
        DetectorSide.BOTH,
        "atr",
        "The change in return between two windows, in ATRs: the move is speeding "
        "up or braking hard.",
    ),
    (
        AnomalyType.MOMENTUM_SHIFT,
        "momentum_15m",
        DetectorSide.BOTH,
        "atr",
        "Fifteen-minute momentum, in ATRs, far from its usual value for this hour.",
    ),
    (
        AnomalyType.VOLATILITY_EXPANSION,
        "atr_14_pct",
        DetectorSide.UP,
        "fraction",
        "Wilder ATR as a fraction of price, well above the usual range.",
    ),
    (
        AnomalyType.ORDERBOOK_IMBALANCE,
        "orderbook_imbalance_20",
        DetectorSide.BOTH,
        "fraction",
        "Top-20 book leaning to one side much harder than it usually does.",
    ),
    (
        AnomalyType.TRADE_VELOCITY_SPIKE,
        "trade_velocity_1m",
        DetectorSide.UP,
        "trades_per_second",
        "Trades per second far above the usual pace for this hour.",
    ),
    (
        AnomalyType.OPEN_INTEREST_SPIKE,
        "open_interest_change_1h",
        DetectorSide.UP,
        "fraction",
        "Open interest building up much faster than usual over an hour.",
    ),
    (
        AnomalyType.FUNDING_ANOMALY,
        "funding_rate",
        DetectorSide.BOTH,
        "fraction",
        "Funding far from its usual level for this market and hour, either sign.",
    ),
)

_DISARMED: tuple[tuple[AnomalyType, str, DetectorSide, str, str, str], ...] = (
    (
        AnomalyType.LIQUIDATION_CLUSTER,
        "liquidation_pressure_1h",
        DetectorSide.UP,
        "usd",
        "Liquidations clustering on one side. Registered and disarmed: the "
        "feature does not exist in the v1 set (liquidations are not in "
        "MarketContext).",
        "feature_not_implemented",
    ),
    (
        AnomalyType.CROSS_EXCHANGE_DIVERGENCE,
        "price_divergence_vs_bybit",
        DetectorSide.BOTH,
        "fraction",
        "The same symbol pricing apart on two exchanges. Registered and "
        "disarmed until a second exchange exists (M1b).",
        "single_exchange_until_m1b",
    ),
)


def _feature_version(registry: FeatureRegistry, feature: str) -> int:
    return registry.get(feature).definition.version


def default_detectors(
    registry: FeatureRegistry = DEFAULT_REGISTRY,
) -> tuple[DetectorDefinition, ...]:
    """The frozen v1 roster, ordered by type, bound to *this* build's features."""
    armed = [
        DetectorDefinition(
            type=anomaly_type,
            version=DETECTOR_VERSION,
            feature=feature,
            feature_version=_feature_version(registry, feature),
            side=side,
            unit=unit,
            description=description,
        )
        for anomaly_type, feature, side, unit, description in _SPECS
    ]
    disarmed = [
        DetectorDefinition(
            type=anomaly_type,
            version=DETECTOR_VERSION,
            feature=feature,
            feature_version=0,
            side=side,
            unit=unit,
            description=description,
            enabled=False,
            disabled_reason=reason,
        )
        for anomaly_type, feature, side, unit, description, reason in _DISARMED
    ]
    return tuple(sorted(armed + disarmed, key=lambda detector: detector.type.value))


DEFAULT_DETECTORS = default_detectors()


def detector_for(
    anomaly_type: AnomalyType, detectors: Sequence[DetectorDefinition] = DEFAULT_DETECTORS
) -> DetectorDefinition:
    for detector in detectors:
        if detector.type is anomaly_type:
            return detector
    raise KeyError(f"no detector registered for {anomaly_type}")


__all__ = [
    "DEFAULT_DETECTORS",
    "DETECTOR_VERSION",
    "EXPIRE_AFTER",
    "FIRE_MIN_SEVERITY",
    "HOLD_MIN_SEVERITY",
    "REASON_DISABLED",
    "REASON_NO_FEATURE",
    "RESOLVE_AFTER",
    "DetectorDefinition",
    "default_detectors",
    "detector_for",
]
