"""``trendline_breakout_v1`` — the trend line, drawn by rule, traded at the close.

Brief T3.34b / EXP-0016. LONG only, ``research_only``. Two mutually exclusive
doors on the same 15-minute bar, breakout first:

- **breakout** — a close more than ``break_atr`` above a **descending resistance**
  touched by ``min_touches_signal`` pivots and violated by none, with
  ``relative_volume >= rvol_min``;
- **bounce** — a confirmed bounce on an **ascending support**: the low came within
  ``tolerance_atr`` of the line and the close moved ``bounce_atr`` away from it.
  No volume requirement, on purpose: a bounce is continuation, not expansion.

**What separates this from ``breakout_v1`` is the invalidation.** The level that
kills the thesis is the *line itself* — closing back below the resistance that was
just broken is the market saying the break was a lie — and a guard forces it to
sit strictly between the stop and the reference, so it is neither dead code
(below the stop) nor a stop wearing another name (above the reference).

**The stop is structural; the ATR term bounds its distance from the other side.**
``stop = min(last confirmed pivot low, reference - stop_atr_max * atr)``: the
pivot low is where the thesis is wrong, and ``stop_atr_max`` (2 ATR) is a ceiling
on the stop *price* — minimum breathing room, so a pivot printed two candles ago
cannot produce a stop the noise takes out. ``max_risk_atr`` (3 ATR) is the other
side of that pair: a pivot low further than that is refused as ``risk_too_wide``
rather than traded with a stop that makes any target a joke. Inverted, the pair
would refuse every bar, and ``constraints_table`` says so.

**The geometry is a port, and the port is the point.** ``tl_pivots``, ``tl_lines``,
``tl_events``, ``tl_scan`` and ``tl_setup`` are flat siblings, so ``code_ref``
closes over them; the research home is ``hunter_indicators.patterns``, and
``test_tl_parity.py`` keeps the two numerically identical. Importing the research
package would be a distribution cycle *and* would leave the geometry outside the
digest — the one direction a freeze may never fail in.

**Declared numeric assumptions, none of them measured.** Every geometry default
comes from the T3.34 brief and classical practice; ``target_r = 2.0`` is
convention; ``atr_pct_min = 0.005`` is the floor of ``breakout_v1`` (KB-0008).
``max_risk_atr = 3.0`` follows from the toll identity ``0.002 / (risk_atr *
atr_pct)`` R: at the ATR floor and the widest accepted risk the assumed 20 bps
round trip costs ``0.002 / (3 * 0.005) = 0.1333 R``, so **the declared cap is
0.1333 R** (0.3333 R in ``session_orb_v1``), rising to 0.2 R at the 2 ATR floor.
Every threshold lives in :data:`TrendlineBreakoutV1.default_parameters`; changing
one, or any comparison operator, is a new version, never an edit here.

**One correction to the brief, and it is not cosmetic.** T3.34b §5 proposed
``max_violations = 0`` for the breakout, and zero is impossible:
``TrendLine.violations`` counts closes through the line **up to the cut**, and a
line deliberately survives its own breakout so that the breakout can be reported
at all (``notes-T3.34.md`` §2.4), so 0 would answer ``line_weak`` to every break
this version ever saw. The default is **1** — *no violation before this bar* —
and the bounce keeps the briefed 2, because a bounce bar is not a violation.

Order of reasons, part of the contract: eligibility, availability (window, ATR,
geometry, volume), the entry conditions, then the three geometry guards. An
unavailable input is ``UNAVAILABLE`` and a refused geometry is ``REJECTED``,
never "condition false" — no market re-arms on a bar it could not evaluate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import align_open_time
from hunter_core.strategies.aggregate import Bar, aggregate
from hunter_core.strategies.base import (
    Decision,
    Evaluation,
    EvaluationState,
    Invalidation,
    StrategyContext,
    canonical_number,
    param_decimal,
    param_int,
)
from hunter_core.strategies.indicators import atr_percent, relative_volume, wilder_atr
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of
from hunter_core.strategies.tl_scan import tl_scan
from hunter_core.strategies.tl_setup import (
    MODE_BOTH,
    MODE_PARAM,
    AtrReading,
    TlSetup,
    channel_of,
    decision_envelope,
    decision_reason,
    find_trigger,
    last_pivot_low,
    pattern_params,
)

_EMPTY: Final[Mapping[str, str]] = {}


def _unavailable(reason: str, detail: Mapping[str, str] = _EMPTY) -> Evaluation:
    return Evaluation(None, EvaluationState.UNAVAILABLE, reason, detail)


def _not_triggered(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.NOT_TRIGGERED, reason, detail)


def _rejected(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.REJECTED, reason, detail)


class TrendlineBreakoutV1:
    """The frozen v1 trend-line breakout/bounce. Stateless and pure."""

    key: str = "trendline_breakout_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
        "mode": MODE_BOTH,
        "pattern_bars": 96,
        "pivot_k": 3,
        "min_swing_atr": Decimal("1.0"),
        "min_touches": 3,
        "min_touches_signal": 3,
        "tolerance_atr": Decimal("0.25"),
        "break_atr": Decimal("0.5"),
        "bounce_atr": Decimal("0.5"),
        "retest_bars": 10,
        "bounce_bars": 3,
        "max_violations_breakout": 1,
        "max_violations_bounce": 2,
        "retire_after_break": 1,
        "parallel_tol": Decimal("0.05"),
        "angle_bucket_atr": Decimal("0.10"),
        "level_bucket_atr": Decimal("0.50"),
        "max_anchors": 20,
        "max_lines": 6,
        "max_channels": 3,
        "rvol_window": 96,
        "rvol_min": Decimal("1.5"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.005"),
        "atr_pct_max": Decimal("0.05"),
        "stop_atr_max": Decimal("2.0"),
        "max_risk_atr": Decimal("3.0"),
        "target_r": Decimal("2.0"),
        "horizon_s": 28800,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "mode": (MODE_PARAM, "which doors are open: breakout, bounce or both"),
            "pattern_bars": (INTEGER_PARAM, "15m bars the geometry is searched in"),
            "pivot_k": (INTEGER_PARAM, "bars each side that confirm a pivot"),
            "min_swing_atr": (DECIMAL_PARAM, "minimum pivot prominence, in ATR"),
            "min_touches": (INTEGER_PARAM, "touches for a line to exist at all"),
            "min_touches_signal": (INTEGER_PARAM, "touches required of the triggering line"),
            "tolerance_atr": (DECIMAL_PARAM, "how close to the line counts as on it, in ATR"),
            "break_atr": (DECIMAL_PARAM, "close beyond the line that is a break, in ATR"),
            "bounce_atr": (DECIMAL_PARAM, "close away from the line that confirms a bounce"),
            "retest_bars": (INTEGER_PARAM, "retest window, also the retirement delay"),
            "bounce_bars": (INTEGER_PARAM, "bars a touch has to be confirmed in"),
            "max_violations_breakout": (
                INTEGER_PARAM,
                "violations tolerated, breakout bar included",
            ),
            "max_violations_bounce": (INTEGER_PARAM, "violations tolerated on a bouncing line"),
            "retire_after_break": (INTEGER_PARAM, "1 = a broken line stops being a trigger"),
            "parallel_tol": (DECIMAL_PARAM, "slope difference still parallel, ATR per bar"),
            "angle_bucket_atr": (DECIMAL_PARAM, "deduplication bucket for slope, ATR per bar"),
            "level_bucket_atr": (DECIMAL_PARAM, "deduplication bucket for level at the cut"),
            "max_anchors": (INTEGER_PARAM, "most recent pivots per side used as anchors"),
            "max_lines": (INTEGER_PARAM, "lines kept after deduplication"),
            "max_channels": (INTEGER_PARAM, "channels kept"),
            "rvol_window": (INTEGER_PARAM, "bars in the relative-volume median, current excluded"),
            "rvol_min": (DECIMAL_PARAM, "minimum relative volume of a breakout (inclusive)"),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
            "atr_bars": (INTEGER_PARAM, "bars the ATR is recomputed from (rolling_window_v1)"),
            "atr_pct_min": (DECIMAL_PARAM, "minimum ATR/close as a fraction (inclusive)"),
            "atr_pct_max": (DECIMAL_PARAM, "maximum ATR/close as a fraction (inclusive)"),
            "stop_atr_max": (DECIMAL_PARAM, "ceiling on the stop price: reference - this many ATR"),
            "max_risk_atr": (DECIMAL_PARAM, "widest accepted risk, in ATR"),
            "target_r": (DECIMAL_PARAM, "minimum target, in multiples of risk"),
            "horizon_s": (INTEGER_PARAM, "expected holding, seconds"),
            "base_confidence": (DECIMAL_PARAM, "uncalibrated constant confidence"),
            "assumed_spread_bps": (DECIMAL_PARAM, "assumed total spread, bps"),
            "slippage_bps": (DECIMAL_PARAM, "assumed slippage per side, bps"),
            "fee_bps": (DECIMAL_PARAM, "assumed fee per side, bps"),
            "max_entry_delay_s": (INTEGER_PARAM, "max seconds from reference close to entry open"),
        }
    )

    def evaluate(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Decision | None:
        return self.explain(ctx, params).decision

    # One return per branch of the contract, in the documented order of reasons.
    def explain(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Evaluation:
        if not ctx.eligible:
            why = {"eligibility_reason": ctx.eligibility_reason or "unknown"}
            return Evaluation(None, EvaluationState.INELIGIBLE, "ineligible", why)

        pattern_bars = param_int(params, "pattern_bars")
        rvol_window = param_int(params, "rvol_window")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])

        window = aggregate(
            ctx.candles_1m,
            self.timeframe,
            ctx.source_bar_close,
            max(pattern_bars, rvol_window + 1, atr_bars),
        )
        if not window.available:
            return _unavailable(window.reason or "", window.detail)

        atr_end = align_open_time(ctx.source_bar_close, atr_timeframe)
        atr_window = aggregate(ctx.candles_1m, atr_timeframe, atr_end, atr_bars)
        if not atr_window.available:
            return _unavailable(f"atr_{atr_window.reason}", atr_window.detail)
        atr = wilder_atr(atr_window.bars, param_int(params, "atr_period"))
        atr_pct = None if atr is None else atr_percent(atr, atr_window.bars[-1].close)
        if atr is None or atr_pct is None:
            return _unavailable("atr_warmup")

        # The geometry window is its own parameter: lengthening ``atr_bars`` must
        # not silently change how far back a line may be drawn.
        bars: Sequence[Bar] = window.bars[-pattern_bars:]
        scan = tl_scan(
            bars, timeframe=self.timeframe, params=pattern_params(params), as_of=len(bars) - 1
        )
        if not scan.lines:
            return _not_triggered("no_line", {"pivots": str(len(scan.pivots))})

        found = find_trigger(scan, str(params["mode"]))
        if found is None:
            return _not_triggered("no_event", {"lines": str(len(scan.lines))})
        event, line = found
        breakout = event.kind.value == "breakout"

        rvol = relative_volume(window.bars, rvol_window)
        if breakout:
            if rvol is None:
                return _unavailable("rvol_unavailable", {"rvol_window": str(rvol_window)})
            if rvol < param_decimal(params, "rvol_min"):
                return _not_triggered("rvol_low", {"relative_volume_15m": canonical_number(rvol)})

        tolerated = param_int(
            params, "max_violations_breakout" if breakout else "max_violations_bounce"
        )
        if line.touches < param_int(params, "min_touches_signal") or line.violations > tolerated:
            return _not_triggered(
                "line_weak",
                {"line_touches": str(line.touches), "line_violations": str(line.violations)},
            )
        if (
            not param_decimal(params, "atr_pct_min")
            <= atr_pct
            <= param_decimal(params, "atr_pct_max")
        ):
            return _not_triggered("atr_out_of_range", {"atr_pct_15m": canonical_number(atr_pct)})

        pivot_low = last_pivot_low(scan.pivots)
        if pivot_low is None:
            # A resistance is drawn on highs only, so a valid line does not imply a
            # confirmed low. Without one there is no structural stop, and inventing
            # a purely ATR one would be a different strategy: report, do not guess.
            return _unavailable("pivot_low_unavailable", {"pivots": str(len(scan.pivots))})

        setup = TlSetup(
            scan=scan,
            line=line,
            event=event,
            pivot_low=pivot_low,
            channel=channel_of(scan, line),
            level=line.projected(scan.as_of),
        )
        reading = AtrReading(atr, atr_pct, atr_timeframe, atr_end)
        return self._decide(ctx, params, bars, reading, rvol, setup)

    def _decide(
        self,
        ctx: StrategyContext,
        params: Mapping[str, Any],
        bars: Sequence[Bar],
        reading: AtrReading,
        rvol: Decimal | None,
        setup: TlSetup,
    ) -> Evaluation:
        """Levels, the three guards and the envelope — the second half of the rule."""
        close, atr = bars[-1].close, reading.value.value
        with localcontext(CONTEXT):
            stop = min(setup.pivot_low.price, close - param_decimal(params, "stop_atr_max") * atr)
            risk = close - stop
            floor = param_decimal(params, "target_r") * risk
            width = None if setup.channel is None else setup.channel.width_atr * atr
            target1 = close + (floor if width is None else max(width, floor))
            too_wide = risk <= 0 or risk > param_decimal(params, "max_risk_atr") * atr
        levels = {
            "stop": canonical_number(stop),
            "reference_price": canonical_number(close),
            "target1": canonical_number(target1),
            "line_price_at_decision": canonical_number(setup.level),
        }
        if not 0 < stop < close < target1:
            return _rejected("geometry", levels)
        # The invalidation must be reachable *before* the stop and *after* the
        # entry: below the stop it is dead code, above the reference it is a stop
        # wearing another name (notes-T3.33 §4).
        if not stop < setup.level < close:
            return _rejected("geometry_invalidation", levels)
        if too_wide:
            return _rejected("risk_too_wide", {**levels, "risk": canonical_number(risk)})

        decision = Decision(
            direction=TradeDirection.LONG,
            reference_price=close,
            stop=stop,
            target1=target1,
            invalidations=(
                Invalidation(kind="close_below", level=setup.level, timeframe=self.timeframe.value),
            ),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=decision_reason(
                setup, close, reading.percent, rvol, width is not None and width > floor
            ),
            supporting_features=decision_envelope(
                ctx,
                params,
                bars,
                reading,
                rvol,
                setup,
                key=self.key,
                version=self.version,
                timeframe=self.timeframe,
            ),
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


TRENDLINE_BREAKOUT_V1: Final = TrendlineBreakoutV1()
"""The registered instance; strategies are stateless, so one is enough."""
