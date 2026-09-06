"""Volume features: relative volume and acceleration over disjoint windows.

**What ``relative_volume_*`` is, exactly** (and what it is not): the volume of
the last ``window_minutes`` divided by the **median of the ``lookback_windows``
previous, disjoint, equal-length windows** taken from the same 1-minute series.
It is *not* the "median of the last 7 days at the same hour" of PIPELINE.md §2 —
that comparison is a **baseline** and belongs to T2.3, which computes it from
these very readings and can then say "this relative volume is 4 MADs above its
own 7-day median for this hour". Naming both the same would make one key mean
two different ratios in the bootstrap and in the scanner (Astra, T2.2 design
review, 3c), so this one states its denominator in its parameters and the
baseline keeps its own identity.

``lookback_windows = 23`` for the whole family: 24 windows of 60 minutes fit in
the 1500-minute hot-state buffer (1440 ≤ 1500) with room for the buffer to be
one candle short, which a 24-window lookback (1500 exactly) would not have.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from hunter_core.domain.enums import FeatureCategory
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.indicators import median
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.context import INPUT_CANDLES, MarketContext
from hunter_indicators.features.definitions import FeatureCalculator, FeatureDefinition
from hunter_indicators.features.price import label_for
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue, Reason
from hunter_indicators.features.windows import tail_minutes

DEFAULT_LOOKBACK_WINDOWS = 23


def _sum_volume(candles: Sequence[NormalizedCandle]) -> Decimal:
    with localcontext(CONTEXT):
        return sum((c.volume for c in candles), start=Decimal(0))


@dataclass(frozen=True, slots=True)
class RelativeVolume:
    """Last window's volume over the median of the previous disjoint windows."""

    window_minutes: int
    lookback_windows: int = DEFAULT_LOOKBACK_WINDOWS

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"relative_volume_{label_for(self.window_minutes)}",
            version=1,
            category=FeatureCategory.VOLUME,
            inputs=(INPUT_CANDLES,),
            params={
                "window_minutes": self.window_minutes,
                "lookback_windows": self.lookback_windows,
                "statistic": "median",
            },
            description=(
                f"volume of the last {self.window_minutes} final minutes over the median "
                f"of the {self.lookback_windows} previous disjoint windows of the same length"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        needed = self.window_minutes * (self.lookback_windows + 1)
        window = tail_minutes(ctx, needed)
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.WARMUP, inputs=definition.inputs
            )
        candles = window.candles
        size = self.window_minutes
        current = _sum_volume(candles[-size:])
        previous = [
            _sum_volume(candles[start : start + size])
            for start in range(0, len(candles) - size, size)
        ]
        baseline = median(previous)
        if baseline is None or baseline == 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = current / baseline
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class VolumeAcceleration:
    """Relative change between the last window and the one before it.

    ``(v_now - v_previous) / v_previous`` — the normalised ``dv/dt`` of
    PIPELINE.md §2, as a fraction. A silent previous window is ``zero_divisor``,
    not "infinite acceleration".
    """

    window_minutes: int = 5

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key="volume_acceleration",
            version=1,
            category=FeatureCategory.VOLUME,
            inputs=(INPUT_CANDLES,),
            params={"window_minutes": self.window_minutes},
            description=(
                f"change of the last {self.window_minutes}-minute volume against the "
                "previous window of the same length, as a fraction"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        size = self.window_minutes
        window = tail_minutes(ctx, size * 2)
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.WARMUP, inputs=definition.inputs
            )
        previous = _sum_volume(window.candles[:size])
        current = _sum_volume(window.candles[size:])
        if previous == 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = (current - previous) / previous
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def volume_calculators() -> tuple[FeatureCalculator, ...]:
    """The frozen v1 volume set, ordered by key."""
    calculators: list[FeatureCalculator] = [
        RelativeVolume(window_minutes=5),
        RelativeVolume(window_minutes=15),
        RelativeVolume(window_minutes=60),
        VolumeAcceleration(window_minutes=5),
    ]
    return tuple(sorted(calculators, key=lambda c: c.definition.key))


__all__ = [
    "DEFAULT_LOOKBACK_WINDOWS",
    "RelativeVolume",
    "VolumeAcceleration",
    "volume_calculators",
]
