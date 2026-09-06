"""The contract of the regime classifier: thresholds, readings, state, decision.

Data only, so ``series.py`` (the statistics), ``breadth.py`` (the confirmation)
and ``classifier.py`` (the verdict) depend on the same shapes without depending
on each other.

**Why the thresholds live here and not in ``opportunity_weights``.** The joint M2
decision makes the stage and the status thresholds part of the weight profile
because they decide a *score*; the regime is a different engine with its own
column for its own version (``market_regimes.classifier_version``). The precedent
is ``anomalies/detectors.py``: a policy the shipped weight vector has no block
for is declared in code, versioned, and echoed in full into the row it produced —
never invented at read time. :attr:`RegimeThresholds.identity` therefore folds an
override into the version string, the same way ``FreshnessPolicy`` does: a
classification made under other numbers must not travel under the name of the
shipped ones (Astra, T2.4 design review, 9a).

The pair ``{trend, volatility}`` is the state; ``regime`` is a **projection** of
that pair onto the single ``market_regime`` column, and the projection is
declared (:data:`REGIME_PROJECTION`) rather than implied. Everything the
projection hides stays in ``supporting_features``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from hunter_core.domain.enums import MarketRegime
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.canonical import canonical_json

REGIME_CLASSIFIER_VERSION = "regime_v0"
"""``market_regimes.classifier_version``. A threshold change is a new string."""

VOLATILITY_QUANTUM = Decimal("0.0000000001")
"""Ten decimals, the resolution ``NUMERIC(28,10)`` holds — a statistic a replay
reads back from Postgres must take the same branch it took live."""

RATIO_QUANTUM = Decimal("0.000001")
CONFIDENCE_QUANTUM = Decimal("0.0001")
"""``market_regimes.confidence`` is ``NUMERIC(5,4)``."""

REASON_VOLATILITY_WARMUP = "volatility_warmup"
"""Fewer hourly samples (or distinct days) than the reference needs."""

REASON_NO_DISPERSION = "no_dispersion"
"""The reference median is zero: there is no scale to express a ratio in."""

REASON_NO_VOLATILITY = "volatility_unavailable"
"""The current window could not be estimated (short, gapped, or a zero price)."""

REASON_NO_TREND_INPUT = "trend_input_unavailable"
"""``return_4h``, ``return_1d`` or the ATR is missing for the reference market."""

REASON_ATR_WARMUP = "atr_warmup"
"""The ATR is absent or zero: ``|return| / atr`` has no denominator."""

REASON_STALE_OBSERVATION = "stale_observation"
"""A redelivery or an out-of-order reading: confirms nothing, undoes nothing."""

REASON_BREADTH_COVERAGE = "insufficient_coverage"

NO_EXCLUSIONS: Mapping[str, str] = MappingProxyType({})
NO_VALUES: Mapping[str, Decimal | None] = MappingProxyType({})
"""Fewer usable markets than the breadth needs — *not* a bearish market."""


class RegimeTrend(StrEnum):
    """The trend dimension of the pair. Local to this engine, not a DB enum."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


class RegimeVolatility(StrEnum):
    """The volatility dimension of the pair."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    UNKNOWN = "unknown"


REGIME_PROJECTION: Mapping[tuple[RegimeTrend, RegimeVolatility], MarketRegime] = MappingProxyType(
    {
        (RegimeTrend.BULL, RegimeVolatility.HIGH): MarketRegime.HIGH_VOLATILITY,
        (RegimeTrend.BEAR, RegimeVolatility.HIGH): MarketRegime.HIGH_VOLATILITY,
        (RegimeTrend.SIDEWAYS, RegimeVolatility.HIGH): MarketRegime.HIGH_VOLATILITY,
        (RegimeTrend.BULL, RegimeVolatility.NORMAL): MarketRegime.BTC_BULL,
        (RegimeTrend.BEAR, RegimeVolatility.NORMAL): MarketRegime.BTC_BEAR,
        (RegimeTrend.SIDEWAYS, RegimeVolatility.NORMAL): MarketRegime.SIDEWAYS,
        (RegimeTrend.BULL, RegimeVolatility.LOW): MarketRegime.BTC_BULL,
        (RegimeTrend.BEAR, RegimeVolatility.LOW): MarketRegime.BTC_BEAR,
        (RegimeTrend.SIDEWAYS, RegimeVolatility.LOW): MarketRegime.LOW_VOLATILITY,
    }
)
"""``{trend, volatility}`` -> the single ``market_regimes.regime`` label.

Declared as a table because it is a **lossy projection**, not a derivation: high
volatility wins over the trend, so a bearish, violent market is stored as
``HIGH_VOLATILITY`` and the ``bear`` half of the pair only survives in
``supporting_features``. Recorded consequence for whoever consumes it (Astra,
T2.4 design review, 9d): ``RISK_ENGINE.md`` §2 applies exactly one multiplier and
looks up ``<REGIME>_<DIRECTION>`` before ``<REGIME>``, so a long in that market
gets ``HIGH_VOLATILITY`` (0.7) instead of ``BTC_BEAR_LONG`` (0.5). Reading the
pair instead of the projected label is a change to the risk contract and belongs
to whoever owns it, not here.
"""


@dataclass(frozen=True, slots=True)
class RegimeThresholds:
    """The versioned parameters of the v0 classifier. Declared, not calibrated.

    No historical study backs any of these numbers; the identity exists so that a
    study can replace them without rewriting what past rows meant.
    """

    trend_4h_atr_multiple: Decimal = Decimal("2")
    """``|return_4h| / atr_14_pct`` above which four hours count as a move."""
    trend_1d_atr_multiple: Decimal = Decimal("4")
    """The same ratio over a day. Larger because a day holds more ATRs."""
    volatility_high_multiple: Decimal = Decimal("2")
    volatility_low_multiple: Decimal = Decimal("0.5")
    volatility_window_days: int = 30
    volatility_min_samples: int = 480
    """Twenty full days of hourly samples out of the thirty the window spans."""
    volatility_min_distinct_days: int = 20
    volatility_hour_min_minutes: int = 60
    """A sampled hour is a *complete* hour: sixty contiguous final candles."""
    volatility_window_minutes: int = 60
    breadth_min_coverage: Decimal = Decimal("0.8")
    breadth_relative_volume_min: Decimal = Decimal("1.5")
    breadth_agreement_min: Decimal = Decimal("0.5")
    confirmations: int = 3
    """``docs/PIPELINE.md`` §4: no regime change without three readings."""
    confidence_full: Decimal = Decimal("1")
    confidence_without_breadth: Decimal = Decimal("0.75")
    confidence_breadth_disagrees: Decimal = Decimal("0.6")
    display_max_age: timedelta = timedelta(minutes=5)
    """Older than this, the last regime is shown with a ``stale`` stamp."""

    @property
    def identity(self) -> str:
        """``regime_v0``, or a suffixed variant when a threshold was overridden."""
        if self == RegimeThresholds():
            return REGIME_CLASSIFIER_VERSION
        digest = hashlib.sha256(canonical_json(self.as_wire())).hexdigest()[:12]
        return f"{REGIME_CLASSIFIER_VERSION}+{digest}"

    def as_wire(self) -> dict[str, Any]:
        """Every parameter, for ``market_regimes.supporting_features``."""
        wire: dict[str, Any] = dict(asdict(self))
        wire["display_max_age_s"] = int(self.display_max_age.total_seconds())
        del wire["display_max_age"]
        return wire


@dataclass(frozen=True, slots=True)
class HourlySample:
    """One complete UTC hour of realised volatility."""

    hour_start: datetime
    value: Decimal
    minutes_used: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "hour_start", ensure_utc(self.hour_start))


@dataclass(frozen=True, slots=True)
class VolatilityReference:
    """The 30-day median the current window is judged against, with its maturity."""

    median: Decimal | None
    samples: int
    distinct_days: int
    window_days: int
    usable: bool
    reason: str | None = None
    window_end: datetime | None = None

    def as_wire(self) -> dict[str, Any]:
        return {
            "median": self.median,
            "samples": self.samples,
            "distinct_days": self.distinct_days,
            "window_days": self.window_days,
            "usable": self.usable,
            "reason": self.reason,
            "window_end": self.window_end,
        }


@dataclass(frozen=True, slots=True)
class MarketTrendReading:
    """The trend of **one** market — breadth material, never a persisted row.

    ``market_regimes`` only holds ``global``/``btc`` scopes (``RegimeScope``), so a
    per-market verdict is deliberately a different type: it feeds the breadth and
    the explanation, and nothing invites a caller to store 200 of them (Astra,
    T2.4 design review, 9g).
    """

    market: str
    trend: RegimeTrend
    reason: str | None = None
    r_4h: Decimal | None = None
    r_1d: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Breadth:
    """How much of the universe is advancing, and who was counted.

    ``fraction`` is ``None`` whenever the coverage is below the gate: fewer than
    four markets in five with a usable reading means the *confirmation* is
    unavailable, which is not the same statement as "the market is not
    advancing".
    """

    fraction: Decimal | None
    coverage: Decimal
    universe_size: int
    usable_markets: int
    advancing: int
    members: tuple[str, ...] = ()
    """Sorted keys of the markets counted as advancing — the composition the joint
    decision requires to be recorded."""
    excluded: Mapping[str, str] = NO_EXCLUSIONS
    """Every market that was not usable, with the reason it was not."""
    usable: bool = False
    reason: str | None = None

    def as_wire(self) -> dict[str, Any]:
        return {
            "fraction": self.fraction,
            "coverage": self.coverage,
            "universe_size": self.universe_size,
            "usable_markets": self.usable_markets,
            "advancing": self.advancing,
            "members": list(self.members),
            "excluded": dict(sorted(self.excluded.items())),
            "usable": self.usable,
            "reason": self.reason,
        }


EMPTY_BREADTH = Breadth(
    fraction=None,
    coverage=Decimal(0),
    universe_size=0,
    usable_markets=0,
    advancing=0,
    reason=REASON_BREADTH_COVERAGE,
)


@dataclass(frozen=True, slots=True)
class BreadthObservation:
    """One market's contribution to the breadth, as the caller resolved it.

    ``None`` means "no usable reading" — a degraded or absent feature, decided by
    the caller against the same rule the scorer uses. It is never a zero: a market
    whose 4-hour return we could not read is excluded from the coverage, not
    counted as flat.
    """

    market: str
    return_4h: Decimal | None = None
    relative_volume_1h: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RegimeObservation:
    """What the classifier reads about the reference market at one instant.

    Resolved by the caller from the BTC feature vector (``return_4h``,
    ``atr_14_pct``) and from ``series.py`` (``return_1d``, ``volatility``), so the
    classifier stays a pure function of data it was given.
    """

    observation_ts: datetime
    return_4h: Decimal | None = None
    return_1d: Decimal | None = None
    atr_pct: Decimal | None = None
    volatility: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))


__all__ = [
    "CONFIDENCE_QUANTUM",
    "EMPTY_BREADTH",
    "NO_EXCLUSIONS",
    "NO_VALUES",
    "RATIO_QUANTUM",
    "REASON_ATR_WARMUP",
    "REASON_BREADTH_COVERAGE",
    "REASON_NO_DISPERSION",
    "REASON_NO_TREND_INPUT",
    "REASON_NO_VOLATILITY",
    "REASON_STALE_OBSERVATION",
    "REASON_VOLATILITY_WARMUP",
    "REGIME_CLASSIFIER_VERSION",
    "REGIME_PROJECTION",
    "VOLATILITY_QUANTUM",
    "Breadth",
    "BreadthObservation",
    "HourlySample",
    "MarketTrendReading",
    "RegimeObservation",
    "RegimeThresholds",
    "RegimeTrend",
    "RegimeVolatility",
    "VolatilityReference",
]
