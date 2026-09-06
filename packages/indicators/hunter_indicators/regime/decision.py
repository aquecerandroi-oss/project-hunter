"""What the classifier publishes: one reading, the state it moves, the verdict.

Split from ``model.py`` for the 350-line budget
(``infra/scripts/check_file_size.py``), along the natural seam: ``model.py`` holds
what is *configured* (thresholds, the projection table, the shapes of the
evidence) and this module what is *decided* (a reading, the hysteresis state, the
decision and the stale stamp for display). The import path
``from hunter_indicators.regime import RegimeDecision`` is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import MarketRegime
from hunter_core.domain.types import ensure_utc
from hunter_indicators.regime.model import (
    EMPTY_BREADTH,
    NO_VALUES,
    REGIME_PROJECTION,
    Breadth,
    RegimeThresholds,
    RegimeTrend,
    RegimeVolatility,
    VolatilityReference,
)


@dataclass(frozen=True, slots=True)
class RegimeReading:
    """One evaluation of the reference market, **before** the hysteresis."""

    observation_ts: datetime
    trend: RegimeTrend
    volatility: RegimeVolatility
    reason: str | None = None
    values: Mapping[str, Decimal | None] = NO_VALUES
    breadth: Breadth = EMPTY_BREADTH
    volatility_reference: VolatilityReference | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))

    @property
    def known(self) -> bool:
        return (
            self.trend is not RegimeTrend.UNKNOWN
            and self.volatility is not RegimeVolatility.UNKNOWN
        )

    @property
    def pair(self) -> tuple[RegimeTrend, RegimeVolatility]:
        return (self.trend, self.volatility)

    @property
    def regime(self) -> MarketRegime:
        return REGIME_PROJECTION.get(self.pair, MarketRegime.UNKNOWN)


@dataclass(frozen=True, slots=True)
class RegimeState:
    """What survives between readings: the published pair and the candidate.

    The hysteresis follows the **pair**, not the projected label: two different
    pairs project onto ``HIGH_VOLATILITY``, and letting the trend flip underneath
    an unchanged label would move every direction-sensitive consumer without the
    three readings the pipeline requires (Astra, T2.4 design review, 9e).
    """

    trend: RegimeTrend = RegimeTrend.UNKNOWN
    volatility: RegimeVolatility = RegimeVolatility.UNKNOWN
    candidate_trend: RegimeTrend = RegimeTrend.UNKNOWN
    candidate_volatility: RegimeVolatility = RegimeVolatility.UNKNOWN
    confirmations: int = 0
    last_observation_ts: datetime | None = None
    published_at: datetime | None = None
    """``observation_ts`` of the reading that published the current pair."""

    def __post_init__(self) -> None:
        # A state rehydrated from JSON with a naive timestamp would compare
        # against an aware ``observation_ts`` and raise inside the hysteresis
        # (Astra, T2.4 diff review, nice-to-have).
        if self.last_observation_ts is not None:
            object.__setattr__(self, "last_observation_ts", ensure_utc(self.last_observation_ts))
        if self.published_at is not None:
            object.__setattr__(self, "published_at", ensure_utc(self.published_at))

    @property
    def pair(self) -> tuple[RegimeTrend, RegimeVolatility]:
        return (self.trend, self.volatility)

    @property
    def regime(self) -> MarketRegime:
        return REGIME_PROJECTION.get(self.pair, MarketRegime.UNKNOWN)

    def as_wire(self) -> dict[str, Any]:
        return {
            "trend": self.trend.value,
            "volatility": self.volatility.value,
            "regime": self.regime.value,
            "candidate_trend": self.candidate_trend.value,
            "candidate_volatility": self.candidate_volatility.value,
            "confirmations": self.confirmations,
            "last_observation_ts": self.last_observation_ts,
            "published_at": self.published_at,
        }


EMPTY_REGIME_STATE = RegimeState()


@dataclass(frozen=True, slots=True)
class RegimeDecision:
    """One classification: what is published, on what evidence, under which version."""

    regime: MarketRegime
    trend: RegimeTrend
    volatility: RegimeVolatility
    observation_ts: datetime
    state_in: RegimeState
    state_out: RegimeState
    classifier_version: str
    confidence: Decimal | None = None
    changed: bool = False
    reason: str | None = None
    reading: RegimeReading | None = None
    thresholds: RegimeThresholds = RegimeThresholds()

    @property
    def label_changed(self) -> bool:
        """Whether the **projected label** moved, which ``changed`` does not say.

        ``changed`` follows the pair, because that is what the hysteresis
        protects; two pairs project onto ``HIGH_VOLATILITY``, so a confirmed
        ``bull+high -> bear+high`` is a real transition with an unchanged label
        (cross review, nice-to-have 3). Derived, never stored: the two states are
        already in the decision, and a third field could disagree with them.

        **Handoff to T2.5:** the scanner publishes ``regime.changed`` on
        ``changed`` — the pair — because every direction-sensitive consumer
        (``PIPELINE.md`` §10: strategy, execution, api) reads the trend and would
        otherwise miss the flip; ``market_regimes`` closes the previous row and
        opens a new one on the same event, so a row always describes one pair.
        ``label_changed`` travels in the event and in ``supporting_features`` so a
        consumer that only cares about the label can filter on it. Publishing on
        the label instead would hide the flip; publishing a row per label would
        make one row describe two different markets.
        """
        return self.state_in.regime is not self.state_out.regime

    def supporting_features(self) -> dict[str, Any]:
        """``market_regimes.supporting_features`` — the whole evidence, sorted."""
        reading = self.reading
        return {
            "classifier_version": self.classifier_version,
            "trend": self.trend.value,
            "volatility": self.volatility.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "changed": self.changed,
            "label_changed": self.label_changed,
            "observation_ts": self.observation_ts,
            "reading": None
            if reading is None
            else {
                "trend": reading.trend.value,
                "volatility": reading.volatility.value,
                "reason": reading.reason,
                "values": dict(sorted(reading.values.items())),
                "breadth": reading.breadth.as_wire(),
                "volatility_reference": (
                    None
                    if reading.volatility_reference is None
                    else reading.volatility_reference.as_wire()
                ),
            },
            "thresholds": self.thresholds.as_wire(),
            "state_in": self.state_in.as_wire(),
            "state_out": self.state_out.as_wire(),
        }


@dataclass(frozen=True, slots=True)
class RegimeDisplay:
    """The last regime, for a screen — with the stamp that says how old it is."""

    regime: MarketRegime
    observation_ts: datetime | None
    age_s: Decimal | None
    stale: bool

    def as_wire(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "observation_ts": self.observation_ts,
            "age_s": self.age_s,
            "stale": self.stale,
        }


__all__ = [
    "EMPTY_REGIME_STATE",
    "RegimeDecision",
    "RegimeDisplay",
    "RegimeReading",
    "RegimeState",
]
