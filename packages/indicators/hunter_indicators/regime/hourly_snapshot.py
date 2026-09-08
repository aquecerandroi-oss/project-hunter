"""What one hour of context *is*, once ``regime_hourly_v1`` has decided it.

Split out of :mod:`hunter_indicators.regime.hourly_model` — which declares the
vocabulary and the thresholds — so that the shapes a persisted row is built from
live next to each other and neither file has to be read to understand the other.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import MarketRegime
from hunter_core.domain.types import ensure_utc
from hunter_indicators.regime.hourly_model import (
    HOUR,
    REGIME_HOURLY_VERSION,
    HourlyTrend,
    VolRegime,
    project_regime,
)


@dataclass(frozen=True, slots=True)
class BreadthCount:
    """How much of the universe was advancing at the cut, and how much was read.

    ``advancing`` counts the markets that are **both** above their 24-hour
    average and up over 24 hours; ``usable`` counts the ones whose 25 hourly
    closes existed at all. A market we could not read is excluded from the
    denominator, never counted as flat.
    """

    universe: int = 0
    usable: int = 0
    advancing: int = 0


@dataclass(frozen=True, slots=True)
class FundingAverage:
    """The mean of the last settled funding rate of each market of the universe.

    One value per market (its latest settlement inside the window), then the mean
    across markets — not the mean of every settlement, which would weight a
    market that settled twice in the window twice.
    """

    value: Decimal | None = None
    markets: int = 0


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """One line of the decomposition, persisted whole.

    ``raw`` is the statistic that drove the component in its own unit,
    ``normalized`` is it on 0-100, ``weight`` is what the version gave it and
    ``contribution`` is ``weight x normalized`` **before** renormalisation — so
    the persisted lines always sum to ``score x available_weight`` and a reader
    can see what was missing rather than infer it.
    """

    name: str
    raw: Decimal | None
    normalized: Decimal | None
    weight: Decimal
    contribution: Decimal | None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.normalized is not None

    def as_wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw": self.raw,
            "normalized": self.normalized,
            "weight": self.weight,
            "contribution": self.contribution,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SnapshotInputs:
    """The statistics behind the verdict, so a row explains itself.

    Everything here is what the classifier *read*; nothing here is a decision.
    """

    closes: int = 0
    """Contiguous hourly closes available at the cut."""
    last_close: Decimal | None = None
    sma_fast: Decimal | None = None
    sma_slow: Decimal | None = None
    slope: Decimal | None = None
    vol_current: Decimal | None = None
    vol_percentile: Decimal | None = None
    vol_samples: int = 0
    high_30d: Decimal | None = None
    breadth: BreadthCount = BreadthCount()
    funding_markets: int = 0

    def as_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = dict(asdict(self))
        wire["breadth"] = dict(asdict(self.breadth))
        return wire


@dataclass(frozen=True, slots=True)
class RegimeSnapshot:
    """One hour of context, decided from data that was final before ``ts``."""

    ts: datetime
    trend: HourlyTrend
    vol_regime: VolRegime
    breadth_pct: Decimal | None
    funding_avg: Decimal | None
    drawdown_pct: Decimal | None
    score_0_100: Decimal | None
    confidence: Decimal
    """The fraction of the total weight that had a usable component."""
    components: tuple[ScoreComponent, ...] = ()
    inputs: SnapshotInputs = SnapshotInputs()
    reasons: tuple[str, ...] = ()
    version: str = REGIME_HOURLY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "ts", ensure_utc(self.ts))

    @property
    def regime(self) -> MarketRegime:
        """The single label ``market_regimes.regime`` holds for this pair."""
        return project_regime(self.trend, self.vol_regime)

    @property
    def valid_until(self) -> datetime:
        """The row is in force over ``[ts, ts + 1h)``."""
        return self.ts + HOUR

    def as_wire(self) -> dict[str, Any]:
        """``market_regimes.supporting_features``: the whole decomposition."""
        return {
            "engine": "regime_hourly",
            "version": self.version,
            "ts": self.ts,
            "trend": self.trend.value,
            "vol_regime": self.vol_regime.value,
            "breadth_pct": self.breadth_pct,
            "funding_avg": self.funding_avg,
            "drawdown_pct": self.drawdown_pct,
            "score_0_100": self.score_0_100,
            "confidence": self.confidence,
            "regime": self.regime.value,
            "components": [component.as_wire() for component in self.components],
            "inputs": self.inputs.as_wire(),
            "reasons": list(self.reasons),
        }


__all__ = [
    "BreadthCount",
    "FundingAverage",
    "RegimeSnapshot",
    "ScoreComponent",
    "SnapshotInputs",
]
