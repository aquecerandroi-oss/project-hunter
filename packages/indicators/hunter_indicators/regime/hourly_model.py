"""The contract of the **hourly** regime snapshot — ``regime_hourly_v1``.

Data only: :mod:`hunter_indicators.regime.hourly` measures,
:mod:`hunter_indicators.regime.hourly_score` weighs, and
:mod:`hunter_indicators.regime.hourly_snapshot` holds the shapes they produce.
This module declares the vocabulary and the numbers all three obey.

**Why a second regime engine and not an edit of ``regime_v0``.** ``regime_v0``
(T2.4) is a *live* classifier: it runs every minute, carries hysteresis, and
writes one open-ended interval per transition. That is the right shape for the
Radar and the wrong shape for research — thirty-one days of it are a handful of
rows, so no cohort can be cut by context (Astra C4, T3.32, T3.33e/g). This engine
answers a different question: *what was the market like during the hour that
started at ``ts``*, once per hour, for every hour, whether or not anything
changed. Two questions, two versions, two rows; the formulas of ``regime_v0`` are
untouched, as the versioning rule requires.

**Where ``ts`` sits, and why there is no look-ahead.** ``ts`` is the **cut**:
every input closed at or before it (the last hourly close used is the bar
``[ts - 1h, ts)``), and the row it produces is in force over ``[ts, ts + 1h)``.
So a signal emitted at 12:34 joins the row whose ``ts`` is 12:00, and that row
was decided from candles that were all final before 12:00. Labelling the hour
that *follows* the data is what makes the join honest; labelling the hour the
data came from would put the hour's own moves inside its own label.

**Why the thresholds live in code.** Same precedent as ``model.py`` and
``anomalies/detectors.py``: ``opportunity_weights`` versions the *score*, and a
regime has its own column for its own version
(``market_regimes.classifier_version``). :attr:`HourlyThresholds.identity` folds
an override into the version string, so a snapshot produced under other numbers
never travels under the name of the shipped ones.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from hunter_core.domain.enums import MarketRegime
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.regime.model import REGIME_PROJECTION, RegimeTrend, RegimeVolatility

REGIME_HOURLY_VERSION = "regime_hourly_v1"
"""``market_regimes.classifier_version`` for every row this engine writes.

Never the same string as ``regime_v0``: the two engines share a table and a
reader has to be able to tell which question a row answers.
"""

HOUR = timedelta(hours=1)

SCORE_QUANTUM = Decimal("0.01")
RATIO_QUANTUM = Decimal("0.000001")
FUNDING_QUANTUM = Decimal("0.00000001")
CONFIDENCE_QUANTUM = Decimal("0.0001")
"""``market_regimes.confidence`` is ``NUMERIC(5,4)``."""

REASON_TREND_WARMUP = "trend_warmup"
"""Fewer contiguous hourly closes than the slow average plus its slope needs."""
REASON_VOL_WARMUP = "vol_warmup"
"""Not enough rolling readings to say where the current one sits."""
REASON_DRAWDOWN_WARMUP = "drawdown_warmup"
REASON_BREADTH_COVERAGE = "insufficient_coverage"
"""Fewer usable markets than the gate — *not* a market that is not advancing."""
REASON_FUNDING_UNAVAILABLE = "funding_unavailable"
REASON_SCORE_UNAVAILABLE = "insufficient_components"
"""Too little of the weight was available for a score to mean anything."""


class HourlyTrend(StrEnum):
    """The trend dimension of the snapshot.

    ``unknown`` is a classification and not a missing value, the same way
    ``MarketRegime.UNKNOWN`` is: during the two hundred hours the slow average
    needs, the honest answer is that the trend is not established yet, and
    ``flat`` would be a fabricated one.
    """

    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


class VolRegime(StrEnum):
    """The volatility dimension of the snapshot."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    UNKNOWN = "unknown"


_TREND_TO_V0 = {
    HourlyTrend.UP: RegimeTrend.BULL,
    HourlyTrend.DOWN: RegimeTrend.BEAR,
    HourlyTrend.FLAT: RegimeTrend.SIDEWAYS,
}
_VOL_TO_V0 = {
    VolRegime.HIGH: RegimeVolatility.HIGH,
    VolRegime.NORMAL: RegimeVolatility.NORMAL,
    VolRegime.LOW: RegimeVolatility.LOW,
}


def project_regime(trend: HourlyTrend, vol: VolRegime) -> MarketRegime:
    """``{trend, vol}`` -> the single ``market_regimes.regime`` label.

    Reuses ``REGIME_PROJECTION`` rather than restating it: two tables mapping the
    same pair onto the same column would drift, and the lossy-projection contract
    (high volatility wins over the trend) is already declared there. Either
    dimension unknown projects onto ``UNKNOWN`` — a pair that is half a pair is
    not a regime, and the surviving half stays in ``supporting_features``.
    """
    if trend is HourlyTrend.UNKNOWN or vol is VolRegime.UNKNOWN:
        return MarketRegime.UNKNOWN
    return REGIME_PROJECTION[(_TREND_TO_V0[trend], _VOL_TO_V0[vol])]


@dataclass(frozen=True, slots=True)
class ComponentWeights:
    """The weight of each component of ``score_0_100``. They sum to 1.

    A separate frozen dataclass and not a mapping so that every weight is typed,
    named and serialisable, and so that adding a component is a diff somebody has
    to read rather than a key appearing in a dict.
    """

    trend: Decimal = Decimal("0.35")
    breadth: Decimal = Decimal("0.25")
    volatility: Decimal = Decimal("0.20")
    drawdown: Decimal = Decimal("0.10")
    funding: Decimal = Decimal("0.10")

    @property
    def total(self) -> Decimal:
        return self.trend + self.breadth + self.volatility + self.drawdown + self.funding

    def of(self, component: str) -> Decimal:
        return Decimal(str(getattr(self, component)))


@dataclass(frozen=True, slots=True)
class HourlyThresholds:
    """The versioned parameters of ``regime_hourly_v1``. Declared, not calibrated.

    No historical study backs any of these numbers — the identity exists so that
    one can replace them without rewriting what past rows meant. Every one of
    them is commented, because a number without a sentence is a magic number.
    """

    sma_fast_hours: int = 50
    """The fast structural average, in closed hours (~2 days)."""
    sma_slow_hours: int = 200
    """The slow one (~8 days). Trend needs both, so it needs 200 closes."""
    slope_lookback_hours: int = 24
    """The slope of the fast average is measured over a day, not over an hour:
    an hour of the fast average is a rounding error on a 50-hour mean."""
    trend_slope_min: Decimal = Decimal("0.002")
    """0.2 % of the fast average over that day. Below it, the structure may be
    stacked but nothing is moving, which is what ``flat`` means here."""
    vol_window_hours: int = 24
    """The realised-volatility reading is a day of hourly returns."""
    vol_reference_hours: int = 720
    """Thirty days of rolling readings form the distribution the current one is
    ranked against."""
    vol_min_samples: int = 168
    """Seven days of readings before a percentile is allowed to be quoted."""
    vol_high_percentile: Decimal = Decimal("80")
    vol_low_percentile: Decimal = Decimal("20")
    """The top and bottom fifth of the last thirty days."""
    drawdown_window_hours: int = 720
    """The 30-day high the drawdown is measured from."""
    drawdown_min_hours: int = 168
    """A "30-day high" built from six hours is not one."""
    drawdown_zero_pct: Decimal = Decimal("20")
    """The drawdown at which that component scores 0. Linear in between."""
    funding_scale: Decimal = Decimal("0.0005")
    """The average 8-hour funding rate (0.05 %) at which the funding component
    saturates. Typical baseline funding is 0.01 %, so this is five times a calm
    tape — crowded, not merely positive."""
    breadth_min_coverage: Decimal = Decimal("0.5")
    """Half the universe must have a usable reading before breadth is quoted."""
    min_weight_for_score: Decimal = Decimal("0.5")
    """Below half the weight, ``score_0_100`` is ``None`` with a reason instead of
    a number renormalised out of almost nothing."""
    weights: ComponentWeights = ComponentWeights()

    @property
    def identity(self) -> str:
        """``regime_hourly_v1``, or a suffixed variant when one was overridden."""
        if self == HourlyThresholds():
            return REGIME_HOURLY_VERSION
        digest = hashlib.sha256(canonical_json(self.as_wire())).hexdigest()[:12]
        return f"{REGIME_HOURLY_VERSION}+{digest}"

    def as_wire(self) -> dict[str, Any]:
        """Every parameter, for ``market_regimes.supporting_features``."""
        wire: dict[str, Any] = dict(asdict(self))
        wire["weights"] = dict(asdict(self.weights))
        return wire


DEFAULT_HOURLY_THRESHOLDS = HourlyThresholds()


__all__ = [
    "CONFIDENCE_QUANTUM",
    "DEFAULT_HOURLY_THRESHOLDS",
    "FUNDING_QUANTUM",
    "HOUR",
    "RATIO_QUANTUM",
    "REASON_BREADTH_COVERAGE",
    "REASON_DRAWDOWN_WARMUP",
    "REASON_FUNDING_UNAVAILABLE",
    "REASON_SCORE_UNAVAILABLE",
    "REASON_TREND_WARMUP",
    "REASON_VOL_WARMUP",
    "REGIME_HOURLY_VERSION",
    "SCORE_QUANTUM",
    "ComponentWeights",
    "HourlyThresholds",
    "HourlyTrend",
    "VolRegime",
    "project_regime",
]
