"""``trendline_breakout_v1`` on a series whose geometry is written down, not read off.

The wave is deterministic and every expected number below is derived from its two
formulas, never from a run of the detector:

- ``low(i) = 1000 - 0.5 i + offset(i)``, ``high = low + 20``, ``close = low + 10``,
  with ``offset`` the triangular wave of amplitude 3 over a period of 10 bars
  (troughs at ``i = 5, 15, …``, peaks at ``i = 10, 20, …``);
- so the peaks sit **exactly** on ``resistance(i) = 1035 - 0.5 i`` and the troughs
  on ``support(i) = 1000 - 0.5 i``: two parallel lines 35 apart, descending at
  half a point per bar;
- every true range is ``high - low = 20`` (the wave never moves more than that
  between closes), so the Wilder ATR is **exactly 20** until a bar breaks the
  pattern. The breakout bar has a range of 37.5, so the ATR at the decision is
  ``(20 * 13 + 37.5) / 14 = 21.25`` — by hand, and the test asserts it.

From those three facts every level of the breakout case follows:

```
reference = resistance(119) + 12          = 987.5
line      = resistance(119)               = 975.5
pivot low = support(115)                  = 942.5      (last confirmed trough)
stop      = min(942.5, 987.5 - 2*21.25)   = 942.5      (the structure wins)
risk                                      = 45         = 2.1176 ATR
target1   = 987.5 + max(35, 2*45)         = 1077.5     (2 R beats the channel)
```

The bounce case is the mirror image (``slope +0.5``) and is deliberately the one
where the **other** side of the stop rule binds: the last trough is only 1 ATR
below the close, so ``close - 2 ATR`` is the lower of the two and becomes the
stop. One series proves the structural stop, the other the ATR floor.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.base import EvaluationState, StrategyContext, build_context
from hunter_core.strategies.tl_pivots import Pivot, PivotKind
from hunter_core.strategies.tl_scan import TlParams, tl_scan
from hunter_core.strategies.tl_setup import last_pivot_low
from hunter_core.strategies.trendline_breakout_v1 import TRENDLINE_BREAKOUT_V1

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, explode, flat, series

pytestmark = pytest.mark.unit

PARAMS = TRENDLINE_BREAKOUT_V1.default_parameters

BASE = D("1000")
AMP = D("3")
HEIGHT = D("20")
PERIOD = 10
TROUGH_PHASE = 5
STEP = timedelta(minutes=15)
BARS = 120
"""120 bars of 15 minutes: the declared window is 97, the geometry window 96."""
BREAK_MARGIN = D("12")
"""How far above the line the breakout bar closes. 12 > ``0.5 * 21.25 = 10.625``,
so it is a break; and 12 < ``2 * 21.25``, so the ATR floor does not reach the
line and the invalidation guard has something to guard."""

CUT = ORIGIN + timedelta(minutes=15 * BARS)
BOUNCE_BARS = 116
"""The bounce series ends **on a trough** (``115 = 5 mod 10``), which is what puts
the confirmation on the decision bar itself."""
BOUNCE_CUT = ORIGIN + timedelta(minutes=15 * BOUNCE_BARS)
DOWN = D("-0.5")
UP = D("0.5")
QUIET_VOLUME = D("10")
BREAK_VOLUME = D("20")


def offset(index: int) -> Decimal:
    phase = (index - TROUGH_PHASE) % PERIOD
    half = PERIOD // 2
    return AMP * D(phase if phase <= half else PERIOD - phase)


def low_of(index: int, slope: Decimal) -> Decimal:
    return BASE + slope * D(index) + offset(index)


def resistance(index: int, slope: Decimal) -> Decimal:
    """The line through the peaks — a peak high, projected to any bar."""
    return BASE + slope * D(index) + AMP * D(PERIOD // 2) + HEIGHT


def support(index: int, slope: Decimal) -> Decimal:
    """The line through the troughs — a trough low, projected to any bar."""
    return BASE + slope * D(index)


def _spec(low: Decimal, high: Decimal, close: Decimal, previous: Decimal | None, volume: Decimal):
    # ``open`` is clamped into the bar instead of carrying the previous close
    # verbatim: on the falling leg of the wave the previous close sits above the
    # next bar's high, which is not a candle. Nothing reads ``open`` — the true
    # range uses the previous *close* — so the clamp changes no number under test.
    open_ = close if previous is None else min(max(previous, low), high)
    return BarSpec(open_, high, low, close, volume)


def build_series(
    *,
    slope: Decimal = DOWN,
    bars: int = BARS,
    breakout: bool = True,
    last_volume: Decimal = BREAK_VOLUME,
    volume: Decimal = QUIET_VOLUME,
) -> list[NormalizedCandle]:
    """The descending wave, with an optional breakout on the very last bar."""
    specs: list[BarSpec] = []
    previous: Decimal | None = None
    for index in range(bars):
        low = low_of(index, slope)
        high, close = low + HEIGHT, low + HEIGHT / 2
        if breakout and index == bars - 1:
            close = resistance(index, slope) + BREAK_MARGIN
            high = close + D("2.5")
        specs.append(
            _spec(low, high, close, previous, last_volume if index == bars - 1 else volume)
        )
        previous = close
    return series(specs, timeframe=Timeframe.M15)


def build_bounce_series(*, bars: int = BOUNCE_BARS) -> list[NormalizedCandle]:
    """The mirror wave (ascending support), ending on a confirmed bounce.

    The last bar is a trough: its low is **on** the line (a touch) and it closes
    ``15 = 0.75 ATR`` above it, past the ``0.5 ATR`` the confirmation asks for.
    """
    slope = D("0.5")
    specs: list[BarSpec] = []
    previous: Decimal | None = None
    for index in range(bars):
        low = low_of(index, slope)
        high, close = low + HEIGHT, low + HEIGHT / 2
        if index == bars - 1:
            close = low + D("15")
        specs.append(_spec(low, high, close, previous, D("10")))
        previous = close
    return series(specs, timeframe=Timeframe.M15)


def build_consolidation_series() -> list[NormalizedCandle]:
    """The wave, then eight bars that hug the line from below, then a violent break.

    Why it exists: it is the only shape in which the **invalidation guard** can
    fire. The stop is ``min(pivot low, close - 2 ATR)``, and on an ordinary
    breakout the last trough sits more than 2 ATR under the line, so the stop is
    always below it. Here the market consolidated in a narrow band while the line
    kept descending, so the last confirmed low (977) ends up **above** the line at
    the decision (975.5), and a break of nearly 3 ATR lifts ``close - 2 ATR``
    above it too. The refusal is then correct and structural, not a contrivance:
    an invalidation at or below the stop would be dead code.
    """
    slope = D("-0.5")
    specs: list[BarSpec] = []
    previous: Decimal | None = None
    for index in range(112):
        low = low_of(index, slope)
        specs.append(_spec(low, low + HEIGHT, low + HEIGHT / 2, previous, D("10")))
        previous = low + HEIGHT / 2
    for step in range(8):  # bars 112..119
        index = 112 + step
        if index == 119:
            low, high, close, volume = D("979"), D("1040"), D("1035"), D("20")
        else:
            # rising highs so none of these bars is a swing high; one dip at 115
            low = D("977") if index == 115 else D("979")
            high, close, volume = D("1000") + D(step), D("980"), D("10")
        specs.append(_spec(low, high, close, previous, volume))
        previous = close
    return series(specs, timeframe=Timeframe.M15)


def ctx_of(
    candles: list[NormalizedCandle], cut: Any = CUT, *, eligible: bool = True
) -> StrategyContext:
    return build_context(
        candles,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        source_bar_close=cut,
        eligible=eligible,
        eligibility_reason=None if eligible else "not_monitored",
    )


def context() -> StrategyContext:
    """The triggering context, for the shared registry round-trip test."""
    return ctx_of(build_series())


def explain(candles: list[NormalizedCandle], cut: Any = CUT, **overrides: Any):
    params: Mapping[str, Any] = {**PARAMS, **overrides}
    return TRENDLINE_BREAKOUT_V1.explain(ctx_of(candles, cut), params)


def envelope_of(decision: Any) -> dict[str, Any]:
    return {f.name: f.value for f in decision.supporting_features.features}


class TestIdentity:
    def test_the_frozen_identity(self) -> None:
        assert TRENDLINE_BREAKOUT_V1.key == "trendline_breakout_v1"
        assert TRENDLINE_BREAKOUT_V1.version == "v1"
        assert TRENDLINE_BREAKOUT_V1.timeframe is Timeframe.M15

    def test_every_parameter_the_schema_declares_has_a_default_and_vice_versa(self) -> None:
        schema = TRENDLINE_BREAKOUT_V1.parameters_schema
        assert set(schema["required"]) == set(PARAMS)
        assert schema["additionalProperties"] is False

    def test_the_window_budget_fits_the_shadow_context(self) -> None:
        """``SHADOW_CONTEXT_MINUTES`` is 1560 and is a knob of the *worker*, shared
        by every version: a strategy that needed it raised would make every other
        version more expensive. 97 bars of 15 minutes is 1455 minutes."""
        needed = max(PARAMS["pattern_bars"], PARAMS["rvol_window"] + 1, PARAMS["atr_bars"])
        assert needed == 97
        assert needed * 15 == 1455
        assert needed * 15 <= 1560


class TestTheBreakout:
    def test_it_fires_on_the_break_with_the_levels_the_geometry_dictates(self) -> None:
        result = explain(build_series())

        assert (result.state, result.reason) == (EvaluationState.TRIGGERED, "signal")
        decision = result.decision
        assert decision is not None
        assert decision.direction is TradeDirection.LONG
        assert decision.reference_price == resistance(119, D("-0.5")) + BREAK_MARGIN == D("987.5")
        assert decision.stop == support(115, D("-0.5")) == D("942.5")
        assert decision.target1 == D("1077.5")
        assert decision.horizon_s == 28800
        assert decision.confidence == D("0.5")

    def test_the_invalidation_is_the_line_and_it_sits_between_stop_and_reference(self) -> None:
        """The whole point of the version: the level that kills the thesis is the
        broken line, at the projection of the decision bar."""
        decision = explain(build_series()).decision

        assert decision is not None
        assert len(decision.invalidations) == 1
        invalidation = decision.invalidations[0]
        assert invalidation.kind == "close_below"
        assert invalidation.level == resistance(119, D("-0.5")) == D("975.5")
        assert invalidation.timeframe == "15m"
        assert decision.stop < invalidation.level < decision.reference_price

    def test_the_envelope_carries_the_whole_drawing(self) -> None:
        decision = explain(build_series()).decision

        assert decision is not None
        features = envelope_of(decision)
        assert features["close_15m"] == D("987.5")
        assert features["relative_volume_15m"] == D("2")  # 20 against a median of 10
        assert features["volume_median_15m"] == D("10")
        assert features["line_kind"] == "resistance"
        assert features["line_slope_per_bar"] == D("-0.5")
        # eight peaks: the first two of the 96-bar window fall inside the ATR
        # warm-up, and a bar without a scale is not a pivot (T3.34 decision 2)
        assert features["line_touches"] == 8
        assert features["line_first_idx"] == 16
        assert features["line_last_idx"] == 86
        assert features["line_valid_from_idx"] == 39
        assert features["line_violations"] == 1  # the breaking bar itself, and only it
        assert features["line_price_at_decision"] == D("975.5")
        assert features["event_kind"] == "breakout"
        assert features["pivot_low_price"] == D("942.5")
        assert features["pivot_low_idx"] == 91  # global bar 115, local to the 96-bar window
        assert features["pattern_bars"] == 96
        assert features["pattern_pivots"] == 16
        assert features["pattern_lines"] == 2  # the resistance and its parallel support
        assert features["pattern_retired_lines"] == 0
        assert isinstance(features["line_id"], str)
        assert len(features["line_id"]) == 16

    def test_the_atr_is_the_one_the_series_defines(self) -> None:
        """Every true range of the wave is 20; the breakout bar prints 37.5, so
        one Wilder step gives ``(20 * 13 + 37.5) / 14 = 21.25``."""
        decision = explain(build_series()).decision

        assert decision is not None
        atr = decision.supporting_features.atr
        assert atr is not None
        assert atr.value == D("21.25")
        assert atr.percent == D("21.25") / D("987.5")
        assert (atr.method, atr.origin, atr.period, atr.bars_used) == (
            "wilder_v1",
            "rolling_window_v1",
            14,
            97,
        )

    def test_the_channel_is_reported_but_two_r_is_the_bigger_target(self) -> None:
        """The two lines are parallel and 35 apart — 1.647 ATR — while 2 R is 90.
        ``max(channel_width, target_r * risk)`` therefore takes the R, and the
        channel travels in the envelope so a later reading can tell which won."""
        decision = explain(build_series()).decision

        assert decision is not None
        features = envelope_of(decision)
        assert features["channel_width_atr"] == D("35") / D("21.25")
        assert decision.target1 - decision.reference_price == D("90")

    def test_the_reason_names_the_line_the_event_and_the_numbers(self) -> None:
        decision = explain(build_series()).decision

        assert decision is not None
        assert "breakout de uma resistance" in decision.reason
        assert "8 toques" in decision.reason
        assert "linha em 975.5" in decision.reason
        assert "volume relativo 2.00x" in decision.reason
        assert "ATR% 2.15%" in decision.reason


class TestTheBounce:
    def test_it_fires_on_an_ascending_support_with_the_atr_floor_as_the_stop(self) -> None:
        """Mirror series: the last trough (1052.5) is closer than 2 ATR to the
        close (1072.5), so ``close - 2 * 20 = 1032.5`` is the lower of the two and
        becomes the stop. Risk is exactly 2 ATR, the floor working as declared."""
        result = explain(build_bounce_series(), BOUNCE_CUT)

        assert (result.state, result.reason) == (EvaluationState.TRIGGERED, "signal")
        decision = result.decision
        assert decision is not None
        atr = decision.supporting_features.atr
        assert atr is not None and atr.value == D("20")
        assert decision.reference_price == support(115, D("0.5")) + D("15") == D("1072.5")
        assert decision.stop == D("1072.5") - 2 * D("20") == D("1032.5")
        assert decision.target1 == D("1072.5") + 2 * D("40") == D("1152.5")
        assert decision.invalidations[0].level == support(115, D("0.5")) == D("1057.5")

    def test_the_bounce_asks_for_no_volume_and_says_so_in_the_envelope(self) -> None:
        """A bounce is continuation, not expansion. Relative volume is 1.0 here —
        below ``rvol_min`` — and the decision stands, with the number recorded."""
        decision = explain(build_bounce_series(), BOUNCE_CUT).decision

        assert decision is not None
        features = envelope_of(decision)
        assert features["event_kind"] == "bounce"
        assert features["line_kind"] == "support"
        assert features["line_slope_per_bar"] == D("0.5")
        assert features["relative_volume_15m"] == D("1") < PARAMS["rvol_min"]

    def test_mode_can_close_either_door(self) -> None:
        breakout_only = explain(build_bounce_series(), BOUNCE_CUT, mode="breakout")
        bounce_only = explain(build_series(), mode="bounce")

        assert (breakout_only.state, breakout_only.reason) == (
            EvaluationState.NOT_TRIGGERED,
            "no_event",
        )
        assert (bounce_only.state, bounce_only.reason) == (
            EvaluationState.NOT_TRIGGERED,
            "no_event",
        )


class TestItDoesNotFire:
    def test_ineligible_market(self) -> None:
        params: Mapping[str, Any] = PARAMS
        result = TRENDLINE_BREAKOUT_V1.explain(ctx_of(build_series(), eligible=False), dict(params))

        assert (result.state, result.reason) == (EvaluationState.INELIGIBLE, "ineligible")
        assert result.detail == {"eligibility_reason": "not_monitored"}

    def test_no_line_when_the_tape_has_no_geometry(self) -> None:
        """A flat market has no swing with a prominence of one ATR, so it has no
        pivots, so it has no lines. Not a failure: an honest "nothing to see"."""
        flat_market = series([flat(D("1000"), D("10"), D("10"))] * BARS, timeframe=Timeframe.M15)

        result = explain(flat_market)

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "no_line")
        assert result.detail == {"pivots": "0"}

    def test_no_event_when_the_line_is_there_and_the_bar_does_nothing(self) -> None:
        result = explain(build_series(breakout=False))

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "no_event")
        assert result.detail == {"lines": "2"}

    def test_rvol_low_kills_a_quiet_break(self) -> None:
        """ "It broke, quietly" is exactly the break that fails (KB-0053)."""
        result = explain(build_series(last_volume=QUIET_VOLUME))

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "rvol_low")
        assert result.detail == {"relative_volume_15m": "1"}

    def test_line_weak_when_the_line_has_not_earned_the_signal(self) -> None:
        result = explain(build_series(), min_touches_signal=9)

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "line_weak")
        assert result.detail == {"line_touches": "8", "line_violations": "1"}

    def test_max_violations_zero_would_refuse_every_breakout_there_is(self) -> None:
        """The correction to brief §5, proved rather than argued: ``violations``
        counts closes through the line **up to the cut**, and the breaking bar is
        one of them, so a tolerance of 0 makes the version answer ``line_weak`` to
        every break it will ever see. The frozen default is 1."""
        with_zero = explain(build_series(), max_violations_breakout=0)

        assert (with_zero.state, with_zero.reason) == (EvaluationState.NOT_TRIGGERED, "line_weak")
        assert PARAMS["max_violations_breakout"] == 1

    def test_atr_out_of_range_below_the_cost_floor(self) -> None:
        result = explain(build_series(), atr_pct_min=D("0.03"))

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "atr_out_of_range")
        assert result.detail == {"atr_pct_15m": str(D("21.25") / D("987.5"))}


class TestItCannotEvaluate:
    def test_warmup_when_the_history_is_short(self) -> None:
        result = explain(build_series(bars=40), ORIGIN + timedelta(minutes=15 * 40))

        assert result.state is EvaluationState.UNAVAILABLE
        assert result.reason == "warmup"

    def test_a_single_missing_minute_makes_the_whole_window_a_gap(self) -> None:
        """A 15-minute bar built from 14 of its minutes is a different bar with the
        same name, so the window is refused rather than shortened."""
        candles = build_series()
        holed = [c for c in candles if c.open_time != candles[900].open_time]

        result = explain(holed)

        assert result.state is EvaluationState.UNAVAILABLE
        assert result.reason == "gap"

    def test_atr_warmup_when_the_period_outgrows_the_window(self) -> None:
        result = explain(build_series(), atr_period=200)

        assert (result.state, result.reason) == (EvaluationState.UNAVAILABLE, "atr_warmup")

    def test_rvol_unavailable_when_the_baseline_is_zero(self) -> None:
        """A market that did not trade has no baseline, and 0 is not a divisor.
        ``UNAVAILABLE``, never ``NOT_TRIGGERED``: the worker must not re-arm on a
        bar whose volume condition was never observed to be false."""
        result = explain(build_series(volume=D("0")))

        assert (result.state, result.reason) == (EvaluationState.UNAVAILABLE, "rvol_unavailable")
        assert result.detail == {"rvol_window": "96"}

    def test_a_pivot_set_without_a_low_has_no_structural_stop(self) -> None:
        """The branch behind ``pivot_low_unavailable``: a resistance is drawn on
        highs only, so a valid line does not imply a confirmed low."""
        highs = (
            Pivot(index=5, kind=PivotKind.HIGH, price=D("10"), confirmed_at=8, prominence_atr=D(2)),
        )

        assert last_pivot_low(highs) is None
        assert last_pivot_low(()) is None


class TestItRefuses:
    def test_geometry_when_the_target_is_not_above_the_reference(self) -> None:
        """``target_r = 0`` with no channel leaves ``target1 == reference``. The
        parameter is refused by ``constraints.check_ranges`` too; this is the
        second line of defence, and it is ``REJECTED`` — the condition held, the
        decision did not — so the market does not re-arm."""
        result = explain(build_series(), target_r=D("0"), max_channels=0)

        assert (result.state, result.reason) == (EvaluationState.REJECTED, "geometry")
        assert result.detail["target1"] == result.detail["reference_price"] == "987.5"

    def test_risk_too_wide_when_the_structural_stop_is_far(self) -> None:
        """Risk here is 45 = 2.1176 ATR. A ceiling of 2.1 ATR (44.625) refuses it,
        and the refusal reports the number so the first replay can publish the
        fraction of bars that die this way."""
        result = explain(build_series(), max_risk_atr=D("2.1"))

        assert (result.state, result.reason) == (EvaluationState.REJECTED, "risk_too_wide")
        assert result.detail["risk"] == "45"
        assert result.detail["stop"] == "942.5"

    def test_geometry_invalidation_when_the_line_ends_up_under_the_stop(self) -> None:
        """The consolidation series: the line kept descending while price hugged
        it, so the last confirmed low (977) and ``close - 2 ATR`` both end up
        **above** the line (975.5). An invalidation under the stop is dead code,
        so the decision is refused instead of published with a level nobody can
        reach."""
        result = explain(build_consolidation_series())

        assert (result.state, result.reason) == (
            EvaluationState.REJECTED,
            "geometry_invalidation",
        )
        assert result.detail["line_price_at_decision"] == "975.5"
        assert D(result.detail["stop"]) > D("975.5")
        assert D(result.detail["stop"]) < D(result.detail["reference_price"])


def broken_line_bars(*, break_at: int = 100, count: int = BARS) -> tuple[Bar, ...]:
    """The wave, a break at ``break_at``, then a market that leaves the line behind.

    After the break the series drops 40 points, so no later pivot touches the old
    line and the geometry stays valid — which is exactly the situation KB-0077
    complained about: a resistance broken 19 bars ago, still drawn, still eligible
    to be a trigger.
    """
    out: list[Bar] = []
    previous: Decimal | None = None
    slope = D("-0.5")
    for index in range(count):
        low = low_of(index, slope) - (D("40") if index > break_at else D("0"))
        high, close = low + HEIGHT, low + HEIGHT / 2
        if index == break_at:
            close = resistance(index, slope) + BREAK_MARGIN
            high = close + D("2.5")
        open_ = close if previous is None else min(max(previous, low), high)
        out.append(
            Bar(
                open_time=ORIGIN + index * STEP,
                close_time=ORIGIN + (index + 1) * STEP,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=D("10"),
            )
        )
        previous = close
    return tuple(out)


class TestRetirement:
    def test_a_line_broken_long_ago_stops_being_drawn(self) -> None:
        """Correction 1 of KB-0077, and the only rule this port adds to T3.34.

        The break happens 19 bars before the cut, past the 10-bar retest window.
        With retirement off — which is how ``hunter_indicators.patterns`` behaves,
        and how the published figures were drawn — the broken resistance and
        support are still there, still carrying their breakouts. With it on they
        are gone: not a trigger, not a channel side, not a number in the envelope.
        """
        bars = broken_line_bars()[-96:]
        geometry = TlParams(rvol_min=None, retire_after_break=True)

        retired = tl_scan(bars, timeframe=Timeframe.M15, params=geometry, as_of=95)
        kept = tl_scan(
            bars,
            timeframe=Timeframe.M15,
            params=TlParams(rvol_min=None, retire_after_break=False),
            as_of=95,
        )

        broken = {event.line_id for event in kept.events if event.kind.value == "breakout"}
        assert len(broken) == 2  # one resistance and one support were left behind
        assert set(retired.retired) == broken
        assert broken & {line.line_id for line in kept.lines} == broken
        assert broken & {line.line_id for line in retired.lines} == set()
        assert len(retired.lines) == len(kept.lines) - 2
        assert len(retired.channels) < len(kept.channels)
        assert retired.events == ()  # every remaining line is quiet

    def test_the_retirement_waits_for_the_retest_window(self) -> None:
        """A line broken *inside* ``retest_bars`` is still drawn: the retest is the
        continuation of the same event, and dropping the line at the break would
        hide it."""
        bars = broken_line_bars()[-96:]  # the break lands on local bar 76
        geometry = TlParams(rvol_min=None, retire_after_break=True)

        last_kept = tl_scan(bars, timeframe=Timeframe.M15, params=geometry, as_of=86)
        first_dropped = tl_scan(bars, timeframe=Timeframe.M15, params=geometry, as_of=87)

        assert last_kept.retired == ()  # 76 + 10 == 86: the window is still open
        assert first_dropped.retired != ()


class TestPurity:
    def test_the_same_context_twice_gives_the_same_decision(self) -> None:
        ctx = ctx_of(build_series())

        first = TRENDLINE_BREAKOUT_V1.evaluate(ctx, PARAMS)
        second = TRENDLINE_BREAKOUT_V1.evaluate(ctx, PARAMS)

        assert first is not None
        assert first == second

    def test_the_module_reads_no_clock_and_no_database(self) -> None:
        """``Strategy.evaluate`` is a pure function (ARCHITECTURE.md §6). The whole
        closure is checked, not only the entry module: geometry that read a clock
        would be just as fatal."""
        from pathlib import Path

        import hunter_core.strategies as package

        directory = Path(package.__file__).parent
        forbidden = ("datetime.now", "time.time", "import redis", "sqlalchemy", "utcnow")
        for name in (
            "trendline_breakout_v1",
            "tl_setup",
            "tl_scan",
            "tl_events",
            "tl_lines",
            "tl_pivots",
        ):
            source = (directory / f"{name}.py").read_text(encoding="utf-8")
            for needle in forbidden:
                assert needle not in source, f"{name}.py mentions {needle}"


class TestNoLookAhead:
    def test_a_bar_after_the_cut_cannot_change_the_decision(self) -> None:
        clean = build_series()
        absurd = explode(BarSpec(D("1000"), D("9999"), D("0.01"), D("5000"), D("999999")), CUT, 15)

        baseline = TRENDLINE_BREAKOUT_V1.evaluate(ctx_of(clean), PARAMS)
        polluted = TRENDLINE_BREAKOUT_V1.evaluate(ctx_of([*clean, *absurd]), PARAMS)

        assert baseline is not None
        assert polluted == baseline
