"""Volatility and momentum, measured in ATR units.

``atr_14_pct`` is the ATR of the anchored checkpoint (``atr.py``) divided by the
close of the bar that produced it — a fraction, matching ``docs/plans/M2.md``
("denominador = último fechamento").

``momentum_15m`` is deliberately **not** a second name for ``return_15m``: it is
that return divided by ``atr_14_pct``, i.e. how many ATRs the price travelled in
15 minutes. That is the quantity the stage classifier compares against 1.5 and 4
(``docs/plans/M2.md`` §Estágio) and what the Momentum component of the score
consumes; a duplicate of ``return_15m`` under another key would be two names for
one number.

``momentum_acceleration`` uses the **current** ATR as the scale of both terms —
the checkpoint cannot be rewound, and rescaling the older return with a
different denominator would compare two different units. It is therefore "the
change in momentum, measured in today's ATR".

``breakout_strength_20`` is the distance from the last 15-minute close to the
highest close of the previous 20 bars, in ATR (price) units: positive above the
range, negative inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from hunter_core.domain.enums import FeatureCategory, Timeframe
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.atr import ATR_METHOD, ATR_ORIGIN, ATR_PERIOD, atr_percent
from hunter_indicators.features.context import INPUT_ATR_STATE, INPUT_CANDLES, MarketContext
from hunter_indicators.features.definitions import FeatureCalculator, FeatureDefinition
from hunter_indicators.features.price import label_for
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue, Reason
from hunter_indicators.features.windows import bars_15m, tail_minutes


def _atr_pct_of(state: FeatureState) -> tuple[Decimal | None, Reason | None]:
    """``atr_14_pct``, or the one reason every feature built on it must repeat.

    One decision, three callers, so they never disagree about one checkpoint
    (cross review, nice-to-have d): no checkpoint, or one that has not passed
    the release gate, is ``warmup``; a checkpoint whose ``last_close`` is not
    positive is ``zero_divisor``. Calling the second one ``warmup`` would
    promise that waiting fixes it, and a close of zero never fills a window.
    """
    checkpoint = state.atr_15m
    if checkpoint is None or checkpoint.value is None:
        return None, Reason.WARMUP
    value = atr_percent(checkpoint)
    return (None, Reason.ZERO_DIVISOR) if value is None else (value, None)


def _scale_of(state: FeatureState) -> tuple[Decimal | None, Reason | None]:
    """The same reading, used as a **divisor**.

    ``atr_14_pct = 0`` is a legitimate reading — sixteen bars that never moved —
    so ``AtrPercent`` publishes it; dividing by it is undefined, so the features
    measured *in ATR units* refuse instead of exploding.
    """
    value, refusal = _atr_pct_of(state)
    if value is not None and value == 0:
        return None, Reason.ZERO_DIVISOR
    return value, refusal


@dataclass(frozen=True, slots=True)
class AtrPercent:
    """Wilder ATR(14) over complete 15-minute UTC bars, as a fraction of the close."""

    period: int = ATR_PERIOD

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"atr_{self.period}_pct",
            version=1,
            category=FeatureCategory.VOLATILITY,
            inputs=(INPUT_CANDLES, INPUT_ATR_STATE),
            params={
                "period": self.period,
                "timeframe": Timeframe.M15.value,
                "method": ATR_METHOD,
                "origin": ATR_ORIGIN,
            },
            description=(
                f"Wilder ATR({self.period}) over complete 15m UTC bars, divided by the close "
                "of the bar that produced it; anchored checkpoint, no reseed per window"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        value, refusal = _atr_pct_of(state)
        if value is None:
            return FeatureValue.unavailable(
                definition.key, refusal or Reason.WARMUP, inputs=definition.inputs
            )
        # Staleness of the checkpoint is judged once, in the provenance of
        # INPUT_ATR_STATE, and inherited by every feature that declares it
        # (engine._inherit) - not re-decided here for one of the four.
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def _return_between(ctx: MarketContext, minutes: int, offset: int) -> Decimal | None | Reason:
    """``close_{t-offset} / close_{t-offset-minutes} - 1`` over final candles."""
    window = tail_minutes(ctx, minutes + offset + 1)
    if not window.available:
        return window.reason or Reason.WARMUP
    candles = window.candles
    current = candles[len(candles) - 1 - offset]
    reference = candles[len(candles) - 1 - offset - minutes]
    if reference.close <= 0:
        return Reason.ZERO_DIVISOR
    with localcontext(CONTEXT):
        return current.close / reference.close - 1


@dataclass(frozen=True, slots=True)
class Momentum:
    """Return over ``minutes`` divided by ``atr_14_pct`` — a move in ATR units."""

    minutes: int = 15

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"momentum_{label_for(self.minutes)}",
            version=1,
            category=FeatureCategory.MOMENTUM,
            inputs=(INPUT_CANDLES, INPUT_ATR_STATE),
            params={"minutes": self.minutes, "scale": "atr_14_pct"},
            description=(
                f"return over {self.minutes} final minutes divided by atr_14_pct: "
                "how many ATRs the price travelled"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        scale, refusal = _scale_of(state)
        if scale is None:
            return FeatureValue.unavailable(
                definition.key, refusal or Reason.WARMUP, inputs=definition.inputs
            )
        change = _return_between(ctx, self.minutes, 0)
        if isinstance(change, Reason):
            return FeatureValue.unavailable(definition.key, change, inputs=definition.inputs)
        if change is None:
            return FeatureValue.unavailable(
                definition.key, Reason.MISSING_INPUT, inputs=definition.inputs
            )
        with localcontext(CONTEXT):
            value = change / scale
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class MomentumAcceleration:
    """``(return_now - return_previous) / atr_14_pct`` over two adjacent windows."""

    minutes: int = 15

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key="momentum_acceleration",
            version=1,
            category=FeatureCategory.MOMENTUM,
            inputs=(INPUT_CANDLES, INPUT_ATR_STATE),
            params={"minutes": self.minutes, "scale": "atr_14_pct"},
            description=(
                f"change between the last two {self.minutes}-minute returns, in current ATR units"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        scale, refusal = _scale_of(state)
        if scale is None:
            return FeatureValue.unavailable(
                definition.key, refusal or Reason.WARMUP, inputs=definition.inputs
            )
        now = _return_between(ctx, self.minutes, 0)
        before = _return_between(ctx, self.minutes, self.minutes)
        for candidate in (now, before):
            if isinstance(candidate, Reason):
                return FeatureValue.unavailable(definition.key, candidate, inputs=definition.inputs)
        assert isinstance(now, Decimal) and isinstance(before, Decimal)
        with localcontext(CONTEXT):
            value = (now - before) / scale
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


@dataclass(frozen=True, slots=True)
class BreakoutStrength:
    """Last 15m close against the highest close of the previous ``bars``, in ATR."""

    bars: int = 20

    @property
    def definition(self) -> FeatureDefinition:
        return FeatureDefinition(
            key=f"breakout_strength_{self.bars}",
            version=1,
            category=FeatureCategory.PRICE,
            inputs=(INPUT_CANDLES, INPUT_ATR_STATE),
            params={"bars": self.bars, "timeframe": Timeframe.M15.value, "scale": "atr"},
            description=(
                f"last 15m close minus the highest close of the previous {self.bars} "
                "complete 15m bars, divided by the ATR in price units"
            ),
        )

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue:
        definition = self.definition
        checkpoint = state.atr_15m
        if checkpoint is None or checkpoint.value is None:
            return FeatureValue.unavailable(definition.key, Reason.WARMUP, inputs=definition.inputs)
        if checkpoint.value == 0:
            return FeatureValue.unavailable(
                definition.key, Reason.ZERO_DIVISOR, inputs=definition.inputs
            )
        window = bars_15m(ctx)
        if not window.available:
            return FeatureValue.unavailable(
                definition.key, window.reason or Reason.WARMUP, inputs=definition.inputs
            )
        if len(window.bars) < self.bars + 1:
            return FeatureValue.unavailable(definition.key, Reason.WARMUP, inputs=definition.inputs)
        previous = window.bars[-self.bars - 1 : -1]
        highest = max(bar.close for bar in previous)
        with localcontext(CONTEXT):
            value = (window.bars[-1].close - highest) / checkpoint.value
        return FeatureValue.ok(definition.key, value, inputs=definition.inputs)


def trend_calculators() -> tuple[FeatureCalculator, ...]:
    """The frozen v1 volatility/momentum set, ordered by key."""
    calculators: list[FeatureCalculator] = [
        AtrPercent(period=ATR_PERIOD),
        Momentum(minutes=15),
        MomentumAcceleration(minutes=15),
        BreakoutStrength(bars=20),
    ]
    return tuple(sorted(calculators, key=lambda c: c.definition.key))


__all__ = [
    "AtrPercent",
    "BreakoutStrength",
    "Momentum",
    "MomentumAcceleration",
    "trend_calculators",
]
