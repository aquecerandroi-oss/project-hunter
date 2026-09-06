"""Volatility and momentum — everything measured in ATR units, hand-computed.

The fixture builds 15-minute bars out of 1-minute candles: the first minute of
each bar carries the extremes, the other fourteen are flat at the close. Bars
0..14 print ``high=101, low=99, close=100`` (TR = 2), bar 15 prints
``high=110, low=100, close=105`` (TR = 10), so the ATR released on bar 15 is
``(2*13 + 10)/14 = 18/7`` and ``atr_14_pct = (18/7)/105 = 6/245``.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.features.atr import AtrAdvance, advance_from_context
from hunter_indicators.features.context import INPUT_ATR_STATE, build_context
from hunter_indicators.features.quality import provenance_for
from hunter_indicators.features.state import EMPTY_STATE, FeatureState
from hunter_indicators.features.trend import (
    AtrPercent,
    BreakoutStrength,
    Momentum,
    MomentumAcceleration,
    trend_calculators,
)
from hunter_indicators.features.vector import Quality, Reason
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle


def _bar_minutes(index: int, high: str, low: str, close: str) -> list[NormalizedCandle]:
    start = ORIGIN + index * 15 * MINUTE
    minutes = [
        candle(
            start, close=Decimal(close), high=Decimal(high), low=Decimal(low), open=Decimal(close)
        )
    ]
    minutes += [
        candle(start + i * MINUTE, close=Decimal(close), high=Decimal(close), low=Decimal(close))
        for i in range(1, 15)
    ]
    return minutes


def _ctx(specs: list[tuple[str, str, str]]):
    candles: list[NormalizedCandle] = []
    for index, (high, low, close) in enumerate(specs):
        candles += _bar_minutes(index, high, low, close)
    return build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=ORIGIN + len(specs) * 15 * MINUTE,
        candles=candles,
    )


def _warm(specs: list[tuple[str, str, str]]):
    ctx = _ctx(specs)
    state = FeatureState(atr_15m=advance_from_context(ctx, None).checkpoint)
    return ctx, state


SIXTEEN = [("101", "99", "100")] * 15 + [("110", "100", "105")]


class TestAtrPercent:
    def test_atr_as_a_fraction_of_the_matching_close(self) -> None:
        ctx, state = _warm(SIXTEEN)
        value = AtrPercent().compute(ctx, state)
        assert value.key == "atr_14_pct"
        assert value.value is not None
        assert value.value.quantize(Decimal("1E-12")) == Decimal("0.024489795918")
        assert value.quality is Quality.OK

    def test_warmup_before_the_gate(self) -> None:
        ctx, state = _warm([("101", "99", "100")] * 14)
        value = AtrPercent().compute(ctx, state)
        assert value.value is None
        assert value.reason is Reason.WARMUP

    def test_without_a_checkpoint_it_is_unavailable(self) -> None:
        ctx = _ctx(SIXTEEN)
        assert AtrPercent().compute(ctx, EMPTY_STATE).reason is Reason.WARMUP

    def test_a_checkpoint_left_behind_by_the_bars_is_degraded(self) -> None:
        """The calculator publishes the number it has; the staleness is decided
        once, in the provenance of INPUT_ATR_STATE, and inherited by the four
        features that declare it (engine._inherit)."""
        _, state = _warm(SIXTEEN)
        wider, _ = _warm(SIXTEEN + [("106", "104", "105")] * 3)
        value = AtrPercent().compute(wider, state)  # state stopped three bars ago
        assert value.value is not None
        entry = provenance_for(wider, None, AtrAdvance(checkpoint=state.atr_15m))[INPUT_ATR_STATE]
        assert entry.quality is Quality.DEGRADED
        assert entry.reason is Reason.STALE_INPUT


class TestMomentum:
    def test_momentum_is_the_return_in_atr_units(self) -> None:
        ctx, state = _warm(SIXTEEN)
        value = Momentum(minutes=15).compute(ctx, state)
        assert value.key == "momentum_15m"
        # return_15m = 105/100 - 1 = 0.05; 0.05 / (6/245) = 12.25/6
        assert value.value is not None
        assert value.value.quantize(Decimal("1E-15")) == Decimal("2.041666666666667")

    def test_a_flat_market_has_zero_momentum(self) -> None:
        ctx, state = _warm([("101", "99", "100")] * 20)
        value = Momentum(minutes=15).compute(ctx, state)
        assert value.value == Decimal("0")

    def test_without_volatility_there_is_no_scale(self) -> None:
        ctx, state = _warm([("100", "100", "100")] * 20)  # every true range is zero
        assert Momentum(minutes=15).compute(ctx, state).reason is Reason.ZERO_DIVISOR


class TestMomentumAcceleration:
    def test_difference_of_two_consecutive_returns_in_atr_units(self) -> None:
        specs = [("101", "99", "100")] * 15 + [("110", "100", "105")]
        ctx, state = _warm(specs)
        value = MomentumAcceleration(minutes=15).compute(ctx, state)
        assert value.key == "momentum_acceleration"
        # return now = 0.05, return of the previous 15 minutes = 0
        assert value.value is not None
        assert value.value.quantize(Decimal("1E-15")) == Decimal("2.041666666666667")

    def test_a_decelerating_move_is_negative(self) -> None:
        specs = (
            [("101", "99", "100")] * 14
            + [("110", "100", "110")]  # +10% in the previous window
            + [("111", "109", "110")]  # flat in the current one
        )
        ctx, state = _warm(specs)
        value = MomentumAcceleration(minutes=15).compute(ctx, state)
        assert value.value is not None
        assert value.value < 0


class TestBreakoutStrength:
    def test_distance_above_the_previous_highs_in_atr_units(self) -> None:
        specs = [("101", "99", "100")] * 20 + [("110", "100", "110")]
        ctx, state = _warm(specs)
        value = BreakoutStrength(bars=20).compute(ctx, state)
        assert value.key == "breakout_strength_20"
        assert value.value is not None
        # ATR after the 21st bar: TRs are 2 x19 then 10 -> seed 2, then two
        # smoothing steps; the reading is positive and the breakout is 10 points
        assert value.value > 0

    def test_inside_the_range_it_is_negative(self) -> None:
        specs = [("110", "90", "100")] * 21 + [("96", "94", "95")]
        ctx, state = _warm(specs)
        value = BreakoutStrength(bars=20).compute(ctx, state)
        assert value.value is not None
        assert value.value < 0

    def test_warmup_without_the_lookback(self) -> None:
        ctx, state = _warm(SIXTEEN)
        assert BreakoutStrength(bars=20).compute(ctx, state).reason is Reason.WARMUP


def test_the_registered_v1_set_is_frozen() -> None:
    assert [calc.definition.key for calc in trend_calculators()] == [
        "atr_14_pct",
        "breakout_strength_20",
        "momentum_15m",
        "momentum_acceleration",
    ]


class TestNonPositiveCloseIsOneReason:
    """Cross-review nice-to-have (d): a checkpoint whose ``last_close`` is not
    positive is a **zero divisor**, not a warm-up, and the two features that
    divide by it must say the same thing.

    ``warmup`` means "wait, the window is still filling"; a close of zero never
    fills. T2.5 restores checkpoints from storage, so this is reachable without
    a candle ever carrying a zero price.
    """

    def _broken(self):
        ctx, state = _warm(SIXTEEN)
        checkpoint = state.atr_15m
        assert checkpoint is not None
        return ctx, FeatureState(atr_15m=replace(checkpoint, last_close=Decimal("0")))

    def test_atr_percent_says_zero_divisor(self) -> None:
        ctx, state = self._broken()
        assert AtrPercent().compute(ctx, state).reason is Reason.ZERO_DIVISOR

    def test_momentum_says_the_same(self) -> None:
        ctx, state = self._broken()
        assert Momentum(minutes=15).compute(ctx, state).reason is Reason.ZERO_DIVISOR

    def test_momentum_acceleration_says_the_same(self) -> None:
        ctx, state = self._broken()
        value = MomentumAcceleration(minutes=15).compute(ctx, state)
        assert value.reason is Reason.ZERO_DIVISOR

    def test_an_absent_checkpoint_is_still_warmup(self) -> None:
        ctx = _ctx(SIXTEEN)
        assert Momentum(minutes=15).compute(ctx, EMPTY_STATE).reason is Reason.WARMUP


class TestAFlatMarketHasAZeroAtr:
    """A zero ATR is a **reading** (16 bars that never moved), not a failure —
    but it is not a scale either: the features that divide by it refuse."""

    FLAT = [("100", "100", "100")] * 16

    def test_atr_percent_publishes_the_zero(self) -> None:
        ctx, state = _warm(self.FLAT)
        value = AtrPercent().compute(ctx, state)
        assert value.value == Decimal("0")
        assert value.quality is Quality.OK

    def test_momentum_refuses_to_divide_by_it(self) -> None:
        ctx, state = _warm(self.FLAT)
        assert Momentum(minutes=15).compute(ctx, state).reason is Reason.ZERO_DIVISOR
