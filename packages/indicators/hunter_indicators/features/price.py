"""Price features: returns and distance to the extremes of a window.

Every value is a **fraction** (0.05 = +5%), never a percentage:
``docs/plans/M2.md`` T1.1c froze that for ``spread_pct`` and the same rule
applies to the whole set — one unit, decided once, so a threshold written in a
weights row cannot mean two things.

The ``_live`` variants are the only ones that read the candle still forming, and
they say so in their key (``return_5m_live``) and in their inputs. A bar feature
and its live sibling are two different features with two different definitions,
never one feature with a flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import localcontext
from typing import Literal

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.context import INPUT_CANDLES, INPUT_FORMING, MarketContext
from hunter_indicators.features.definitions import FeatureCalculator, FeatureDefinition
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue, Reason
from hunter_indicators.features.windows import tail_minutes

_LABELS = {1: "1m", 5: "5m", 15: "15m", 60: "1h", 240: "4h", 1440: "24h"}


def label_for(minutes: int) -> str:
    """``60 -> "1h"``; anything unnamed keeps its minute count (``7 -> "7m"``)."""
    return _LABELS.get(minutes, f"{minutes}m")


@dataclass(frozen=True, slots=True)
class Return:
    """``close_t / close_{t-N} - 1`` over final minutes, as a fraction.

    ``live=True`` replaces the numerator with the close of the candle still
    printing, so the reading spans the last ``N-1`` closed minutes plus the
    minute in progress — deliberately *not* the same number as the bar feature,
    which is why it carries a different key.
    """

    minutes: int
    live: bool = False

    @property
    def definition(self) -> FeatureDefinition:
        suffix = "_live" if self.live else ""
        return FeatureDefinition(
            key=f"return_{label_for(self.minutes)}{suffix}",
            version=1,
            category=FeatureCategory.PRICE,
            inputs=(INPUT_CANDLES, INPUT_FORMING) if self.live else (INPUT_CANDLES,),
            params={"minutes": self.minutes},
            description=(
                "close over the close of the candle that closed "
                f"{self.minutes - 1 if self.live else self.minutes} minutes earlier, "
                "as a fraction" + (" (numerator is the candle in progress)" if self.live else "")
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        window = tail_minutes(
            ctx, self.minutes if self.live else self.minutes + 1, include_forming=self.live
        )
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.WARMUP, inputs=definition.inputs
            )
        reference = window.candles[0].close
        current = window.last_close
        if current is None:
            return FeatureValue.unavailable(
                definition.key, Reason.MISSING_INPUT, inputs=definition.inputs
            )
        if reference <= 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = current / reference - 1
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class DistanceFromExtreme:
    """Distance from the highest high / lowest low of a window, as a fraction.

    Built from **final candles only** (``docs/plans/M2.md``: the canonical source
    of the 24 h extremes is the candle series, not the ticker hash — the ticker's
    ``high_24h``/``low_24h`` come from a different stream with a different window
    and are not always written, so mixing them under one key would silently
    change the meaning of the number).
    """

    kind: Literal["high", "low"]
    window_minutes: int = 1440

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"distance_from_{label_for(self.window_minutes)}_{self.kind}",
            version=1,
            category=FeatureCategory.PRICE,
            inputs=(INPUT_CANDLES,),
            params={"window_minutes": self.window_minutes, "extreme": self.kind},
            description=(
                f"last close relative to the {self.kind} of the previous "
                f"{self.window_minutes} final minutes, as a fraction"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        window = tail_minutes(ctx, self.window_minutes)
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.WARMUP, inputs=definition.inputs
            )
        extreme = (
            max(c.high for c in window.candles)
            if self.kind == "high"
            else min(c.low for c in window.candles)
        )
        close = window.candles[-1].close
        if extreme <= 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = (close - extreme) / extreme
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def price_calculators() -> tuple[FeatureCalculator, ...]:
    """The frozen v1 price set, ordered by key."""
    calculators: list[FeatureCalculator] = [
        Return(minutes=1),
        Return(minutes=5),
        Return(minutes=15),
        Return(minutes=60),
        Return(minutes=240),
        Return(minutes=1, live=True),
        Return(minutes=5, live=True),
        Return(minutes=15, live=True),
        Return(minutes=60, live=True),
        DistanceFromExtreme(kind="high", window_minutes=1440),
        DistanceFromExtreme(kind="low", window_minutes=1440),
    ]
    return tuple(sorted(calculators, key=lambda c: c.definition.key))


__all__ = ["DistanceFromExtreme", "Return", "label_for", "price_calculators"]
