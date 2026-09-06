"""The global regime, resolved once a minute from BTC plus the breadth.

The classifier (T2.4) is a pure function of a ``RegimeObservation``, a
``VolatilityReference`` and a ``Breadth``; resolving those is this module's job,
and doing it *incrementally* is the whole point. The reference is the median of
the hourly samples of thirty days -- 43,200 one-minute candles. Recomputing that
every minute was measured as the obvious way to miss the p99 budget, so:

- the thirty days are read **once**, at startup, and turned into hourly samples;
- each closed hour appends exactly one sample and drops the one that fell out of
  the window, so the median is recomputed over 720 numbers, not 43,200 candles;
- the trailing window (the last 61 closes) rides along in a bounded deque fed by
  the same closed candles the consumer already receives.

``regime.changed`` is published **by the pair**, with ``label_changed`` beside
it: ``bull+high -> bear+high`` projects onto the same label, and publishing by
label would hide a trend flip from every directional consumer (notes-T2.4
section 8g). One ``market_regimes`` row therefore describes one pair.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.logging import get_logger
from hunter_indicators.features import Quality
from hunter_indicators.regime import (
    EMPTY_REGIME_STATE,
    Breadth,
    BreadthObservation,
    HourlySample,
    RegimeDecision,
    RegimeObservation,
    RegimeState,
    VolatilityReference,
    classify_regime,
    compute_breadth,
    hourly_samples,
    regime_for_display,
    return_over,
    trailing_volatility,
    volatility_reference,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_core.domain.market import NormalizedCandle
    from hunter_indicators.features import FeatureVector
    from hunter_indicators.regime import RegimeDisplay, RegimeThresholds

logger = get_logger(__name__)

REFERENCE_DAYS = 30
TRAILING_MINUTES = 1_500
"""Closed minutes kept in memory: 61 feed the trailing volatility, 1440 the
one-day return, and the extra rounds it to the same buffer the hot state uses."""

BTC_SYMBOL = "BTCUSDT"

__all__ = ["BTC_SYMBOL", "REFERENCE_DAYS", "RegimeEngine", "breadth_observation"]


def _value(vector: FeatureVector, key: str) -> Decimal | None:
    """A feature only when this reading can be believed.

    Same rule the scorer applies: ``degraded`` is evidence that an input was
    late, not a number to reason with. A breadth built on degraded returns would
    report a market as advancing on the strength of a stale candle.
    """
    entry = vector.values.get(key)
    if entry is None or entry.quality is not Quality.OK:
        return None
    return entry.value


def breadth_observation(symbol: str, vector: FeatureVector) -> BreadthObservation:
    """One market's contribution, ``None`` where the reading is not usable."""
    return BreadthObservation(
        market=symbol,
        return_4h=_value(vector, "return_4h"),
        relative_volume_1h=_value(vector, "relative_volume_1h"),
    )


@dataclass
class RegimeEngine:
    """The reference series, the hysteresis state and the row that holds it."""

    thresholds: RegimeThresholds
    state: RegimeState = EMPTY_REGIME_STATE
    row_id: UUID | None = None
    samples: list[HourlySample] = field(default_factory=list[HourlySample])
    reference: VolatilityReference | None = None
    candles: deque[NormalizedCandle] = field(
        # ``deque(maxlen=...)`` and not ``deque[NormalizedCandle](maxlen=...)``:
        # the subscript is evaluated at *runtime* inside the factory, and the
        # candle type is a TYPE_CHECKING-only import here. Caught by the
        # operational proof, not by the tests -- so there is now a test.
        default_factory=lambda: deque(maxlen=TRAILING_MINUTES)
    )
    last_sampled_hour: datetime | None = None
    last_decision: RegimeDecision | None = None
    warmed: bool = False

    # --- ingestion ---------------------------------------------------------

    def seed(self, candles: Sequence[NormalizedCandle], *, until: datetime) -> None:
        """Load the thirty-day history once. Everything after this is a delta."""
        self.samples = list(
            hourly_samples(candles, until=until, thresholds=self.thresholds, days=REFERENCE_DAYS)
        )
        self.reference = volatility_reference(self.samples, self.thresholds)
        self.candles.clear()
        for candle in candles[-TRAILING_MINUTES:]:
            self.candles.append(candle)
        self.last_sampled_hour = _floor_hour(until)
        self.warmed = True
        logger.info(
            "scanner_regime_seeded",
            samples=len(self.samples),
            reference=str(self.reference.median) if self.reference else None,
            usable=bool(self.reference and self.reference.usable),
        )

    def observe_candle(self, candle: NormalizedCandle) -> None:
        """Append one closed BTC minute. Out-of-order and duplicate are no-ops."""
        if not candle.is_final:
            return
        if self.candles and candle.open_time <= self.candles[-1].open_time:
            return
        self.candles.append(candle)

    def roll_hour(self, now: datetime) -> bool:
        """Sample the hour that just closed, if one did. Returns whether it did.

        Only the closed hour is recomputed -- the same rule the baselines follow,
        for the same reason: an append-only series recomputed whole every cycle
        is a series nobody can afford.
        """
        if not self.warmed:
            return False
        current = _floor_hour(now)
        if self.last_sampled_hour is not None and current <= self.last_sampled_hour:
            return False
        fresh = hourly_samples(list(self.candles), until=now, thresholds=self.thresholds, days=2)
        known = {sample.hour_start for sample in self.samples}
        added = [sample for sample in fresh if sample.hour_start not in known]
        if added:
            self.samples.extend(added)
            self.samples.sort(key=lambda sample: sample.hour_start)
            cutoff = now - timedelta(days=REFERENCE_DAYS)
            self.samples = [sample for sample in self.samples if sample.hour_start >= cutoff]
            self.reference = volatility_reference(self.samples, self.thresholds)
        self.last_sampled_hour = current
        return bool(added)

    # --- classification ----------------------------------------------------

    def observation(self, vector: FeatureVector | None, *, as_of: datetime) -> RegimeObservation:
        """The reference market's reading, from the vector and the series."""
        candles = list(self.candles)
        return RegimeObservation(
            observation_ts=as_of,
            return_4h=None if vector is None else _value(vector, "return_4h"),
            atr_pct=None if vector is None else _value(vector, "atr_14_pct"),
            return_1d=return_over(candles, minutes=1440, as_of=as_of),
            volatility=trailing_volatility(candles, as_of=as_of, thresholds=self.thresholds),
        )

    def classify(
        self,
        *,
        vector: FeatureVector | None,
        as_of: datetime,
        breadth_observations: Sequence[BreadthObservation],
        universe_size: int,
    ) -> RegimeDecision:
        """One minute's verdict, with the hysteresis carried in ``self.state``."""
        breadth: Breadth = compute_breadth(
            breadth_observations, universe_size=universe_size, thresholds=self.thresholds
        )
        decision = classify_regime(
            state=self.state,
            observation=self.observation(vector, as_of=as_of),
            reference=self.reference,
            breadth=breadth,
            thresholds=self.thresholds,
        )
        self.state = decision.state_out
        self.last_decision = decision
        return decision

    def display(self, *, as_of: datetime) -> RegimeDisplay:
        """What the Radar shows, stale-stamped when the state is old."""
        return regime_for_display(self.state, as_of=as_of, thresholds=self.thresholds)

    def stale(self, *, as_of: datetime) -> bool:
        """Whether the scorer must treat the regime as stale for this cut."""
        return self.display(as_of=as_of).stale


def _floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)
