"""``d = (x - median) / MAD`` and the versioned transformation into 0-100.

The joint decision (``docs/plans/M2.md`` §Score) fixes the shape and the source:
a **monotonic piecewise** map, flat up to one MAD, linear to 100 at six MADs,
saturated above, with the thresholds living in
``opportunity_weights.weights["normalization"]`` — read, never hardcoded. The
identity of the transformation therefore includes the weight version: the same
``mad_piecewise_v1`` under another profile can produce another severity, and a
severity that cannot say which profile produced it cannot be replayed.

Three deliberate refusals:

- **no 1.4826.** The MAD is used raw. Scaling it to a normal-consistent sigma
  would claim a probability about a crypto volume distribution that nobody
  established;
- **direction is separate from magnitude.** The severity answers "how unusual",
  the direction answers "which way", and a one-sided detector uses the direction
  *before* deciding to fire: a volume collapse of six MADs is not a
  ``VOLUME_SPIKE`` (Astra, T2.3 design review, item 2);
- **MAD zero is not a free pass.** If the reading equals the median the deviation
  is genuinely zero; if it differs there is no scale to express the distance in
  and the component is unavailable with ``mad_zero``. No ``min_scale`` is
  declared for any feature in v1 — an invented floor would be a fabricated
  number, and the one candidate (the exchange's base funding rate) is neither a
  dispersion nor universal across symbols.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Any

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.baselines.revision import BaselineRevision

NORMALIZATION_METHOD = "mad_piecewise_v1"
"""The only transformation this build implements. A change is a new string."""

SEVERITY_QUANTUM = Decimal("0.01")
"""``NUMERIC(5,2)`` — ``anomalies.severity``."""

CONFIDENCE_QUANTUM = Decimal("0.0001")
"""``NUMERIC(5,4)`` — ``anomalies.confidence``."""

BASELINE_DAYS = 7
"""The window the maturity of a baseline is measured against (seven days)."""

REASON_MAD_ZERO = "mad_zero"
"""The baseline has no dispersion and the reading is not on the median."""


class AnomalyDirection(StrEnum):
    """Which way the reading departed from its baseline."""

    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class DetectorSide(StrEnum):
    """Which tail a detector is about — decided before it fires, not after."""

    UP = "up"
    DOWN = "down"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class NormalizationConfig:
    """The versioned MAD -> severity transformation, read from the weight vector."""

    method: str
    deadband_mad: Decimal
    saturation_mad: Decimal
    saturation_score: Decimal
    weights_version: str

    def __post_init__(self) -> None:
        if self.method != NORMALIZATION_METHOD:
            raise ValueError(
                f"this build implements {NORMALIZATION_METHOD}, not {self.method!r}: a new "
                "transformation is a new implementation, never a config switch"
            )
        if self.saturation_mad <= self.deadband_mad:
            raise ValueError("the saturation must sit above the deadband")

    @classmethod
    def from_weights(cls, weights: Mapping[str, Any], *, version: str) -> NormalizationConfig:
        block: Mapping[str, Any] = weights["normalization"]
        return cls(
            method=str(block["method"]),
            deadband_mad=Decimal(str(block["deadband_mad"])),
            saturation_mad=Decimal(str(block["saturation_mad"])),
            saturation_score=Decimal(str(block["saturation_score"])),
            weights_version=version,
        )

    @property
    def identity(self) -> str:
        """What a stored severity names so it can be reproduced."""
        return f"{self.method}@{self.weights_version}"


def deviation_in_mads(
    current: Decimal, median: Decimal, mad: Decimal
) -> tuple[Decimal | None, str | None]:
    """``(x - median) / MAD``, or ``None`` with the reason there is no scale."""
    with localcontext(CONTEXT):
        difference = current - median
        if mad == 0:
            return (Decimal(0), None) if difference == 0 else (None, REASON_MAD_ZERO)
        return difference / mad, None


def severity_of(deviation: Decimal, config: NormalizationConfig, side: DetectorSide) -> Decimal:
    """The 0-100 severity of ``deviation`` on the tail ``side`` cares about."""
    with localcontext(CONTEXT):
        if side is DetectorSide.BOTH:
            magnitude = abs(deviation)
        elif side is DetectorSide.UP:
            magnitude = max(deviation, Decimal(0))
        else:
            magnitude = max(-deviation, Decimal(0))
        if magnitude <= config.deadband_mad:
            return Decimal(0).quantize(SEVERITY_QUANTUM)
        if magnitude >= config.saturation_mad:
            return config.saturation_score.quantize(SEVERITY_QUANTUM)
        span = config.saturation_mad - config.deadband_mad
        raw = (magnitude - config.deadband_mad) / span * config.saturation_score
        return raw.quantize(SEVERITY_QUANTUM)


def direction_of(deviation: Decimal) -> AnomalyDirection:
    if deviation > 0:
        return AnomalyDirection.UP
    if deviation < 0:
        return AnomalyDirection.DOWN
    return AnomalyDirection.FLAT


def confidence_of(revision: BaselineRevision, *, days_window: int = BASELINE_DAYS) -> Decimal:
    """How mature the population is — **not** how fresh the reading is.

    ``min(coverage, distinct_days / 7)``. With per-minute sampling the coverage
    term already dominates (``sample_size <= 60 * distinct_days`` makes
    ``coverage <= distinct_days / 7``), so the minimum is the coverage in every
    well-formed bucket; it is written as a minimum anyway because
    ``expected_size`` is a versioned parameter and a future profile could break
    that inequality without anyone noticing (Astra, T2.3 design review, item 5).

    Freshness of the current reading lives in ``anomalies.evaluation_state``, a
    deliberately separate axis.
    """
    with localcontext(CONTEXT):
        days = Decimal(revision.distinct_days) / Decimal(days_window)
        return min(revision.coverage, days, Decimal(1)).quantize(CONFIDENCE_QUANTUM)


@dataclass(frozen=True, slots=True)
class Deviation:
    """The full verdict about one reading against one baseline."""

    current_value: Decimal
    baseline: Decimal
    scale: Decimal
    value: Decimal | None
    severity: Decimal | None
    direction: AnomalyDirection
    confidence: Decimal | None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.value is not None and self.severity is not None


def evaluate_deviation(
    current: Decimal,
    revision: BaselineRevision,
    config: NormalizationConfig,
    side: DetectorSide,
) -> Deviation:
    """``current`` against ``revision``: deviation, severity, direction, confidence."""
    value, reason = deviation_in_mads(current, revision.median, revision.mad)
    if value is None:
        return Deviation(
            current_value=current,
            baseline=revision.median,
            scale=revision.mad,
            value=None,
            severity=None,
            direction=AnomalyDirection.FLAT,
            confidence=None,
            reason=reason,
        )
    return Deviation(
        current_value=current,
        baseline=revision.median,
        scale=revision.mad,
        value=value,
        severity=severity_of(value, config, side),
        direction=direction_of(value),
        confidence=confidence_of(revision),
    )


__all__ = [
    "BASELINE_DAYS",
    "CONFIDENCE_QUANTUM",
    "NORMALIZATION_METHOD",
    "REASON_MAD_ZERO",
    "SEVERITY_QUANTUM",
    "AnomalyDirection",
    "DetectorSide",
    "Deviation",
    "NormalizationConfig",
    "confidence_of",
    "deviation_in_mads",
    "direction_of",
    "evaluate_deviation",
    "severity_of",
]
