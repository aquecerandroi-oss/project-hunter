"""``trendline_bounce_v1`` — the hypothesis the data actually supported.

Brief T3.57 / EXP-0022. LONG only, ``research_only``, 15-minute grid. The second
version of the trend-line family; it exists because the first measured something
other than what its name claimed (``notes-T3.34c.md``):

- **89.4 % of ``trendline_breakout v1``'s decisions were bounces**, not breakouts;
  the door that named the version decided five times in 31 days and lost all five
  (0 targets, 4 invalidations, −0.5075 R each). One door survives here — not as a
  parameter but as an identity: no ``mode``, because "which door" is no longer a
  knob a variant may turn;
- **the structural invalidation only anticipated the loss.** Paired over the same
  47 episodes, removing it was worth **Δ +0.0922 R** per decision and flipped the
  sign of the expectancy (−0.038 → +0.054) — the fifth population here to repeat
  KB-0006/EXP-0007, and why C8 of EXP-0016 was demoted to ``REVISE``. **This
  version has no invalidation at all**: stop, target or horizon. ``v1``'s guard
  keeping the line between stop and reference goes with it — a guard on a level
  nobody reads is dead code;
- **``line_slope_per_bar`` is not an independent regime proxy** (C4 of EXP-0016,
  refuted): decile 1 of slope/ATR was *exactly* the five breakouts, by
  construction. No slope threshold is added; "ascending support" already belongs
  to the geometry, in ``tl_setup.find_trigger``.

**What is genuinely new is one thing: volume.** ``v1``'s bounce asked for none on
purpose ("a bounce is continuation, not expansion"). Here the bounce bar must
have traded **at least the median of the last 96 bars** (``rvol_min = 1.0``) —
the minimum reading of "with RVOL", deliberately not the 1.5 of the breakout,
which demands *expansion*. Declared assumption, fixed before the population was
looked at; all that was measured beforehand is that the survivors still clear K1
(26 decisions over the same 31 d x 4 markets, ``notes-T3.57.md``).

**Everything else is inherited verbatim from the frozen ``v1`` contract** — levels,
guards, order of reasons (so two ledgers pair bar by bar), and ``horizon_s`` still
8 h although T3.34c found the ``expired`` exits *positive* (+0.6074 R): that says
the horizon is short, and lengthening it is a fourth change and a fourth version.
Toll identity unchanged, ``0.002 / (risk_atr * atr_pct)`` R — **0.20 R** at the
ATR floor and the 2 ATR minimum risk (EXP-0016's "0.1333 R" was a best case 59.6 %
of decisions never saw). The geometry is the same port (``tl_pivots``,
``tl_lines``, ``tl_events``, ``tl_scan``, ``tl_setup``: flat siblings inside the
``code_ref`` closure) and this module **does not import**
``trendline_breakout_v1``, which would put another experiment's code inside this
freeze and make an edit here re-freeze a version already activated on the VPS.
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
    MODE_BOUNCE,
    AtrReading,
    TlSetup,
    channel_of,
    decision_envelope,
    find_trigger,
    last_pivot_low,
    pattern_params,
)

_EMPTY: Final[Mapping[str, str]] = {}
_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")


def _display(value: Decimal, scale: Decimal = Decimal(1)) -> str:
    """Two decimals under the declared context, for the human sentence only —
    ``scale`` applied **inside** it, so a narrow ambient precision cannot turn
    2.1518 % into 2.20 % and make one frozen version read differently twice."""
    with localcontext(CONTEXT):
        return f"{(value * scale).quantize(_DISPLAY):f}"


def _unavailable(reason: str, detail: Mapping[str, str] = _EMPTY) -> Evaluation:
    return Evaluation(None, EvaluationState.UNAVAILABLE, reason, detail)


def _not_triggered(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.NOT_TRIGGERED, reason, detail)


def _rejected(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.REJECTED, reason, detail)


def _reason(
    setup: TlSetup, close: Decimal, atr_pct: Decimal, rvol: Decimal, channel_target: bool
) -> str:
    """The human sentence, in Portuguese, naming every number that decided.

    Not ``tl_setup.decision_reason``: that one mentions volume only for a
    *breakout*, and here volume is a gate of the bounce. Two decimals here and
    only here; the envelope keeps full precision."""
    line, event = setup.line, setup.event
    width = (
        f", alvo pela largura do canal ({_display(setup.channel.width_atr)} ATR)"
        if channel_target and setup.channel is not None
        else ""
    )
    return (
        f"Linha de tendencia 15m: repique de um {line.kind.value} ascendente com "
        f"{line.touches} toques e {line.violations} violacoes (inclinacao "
        f"{canonical_number(line.slope_per_bar)}/barra, linha em "
        f"{canonical_number(setup.level)}); fechamento {canonical_number(close)} a "
        f"{_display(event.distance_atr)} ATR da linha, volume relativo "
        f"{_display(rvol)}x{width}, ATR% {_display(atr_pct, _PERCENT)}%"
    )


class TrendlineBounceV1:
    """The frozen v1 trend-line bounce. Stateless and pure."""

    key: str = "trendline_bounce_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
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
        "max_violations_bounce": 2,
        "retire_after_break": 1,
        "parallel_tol": Decimal("0.05"),
        "angle_bucket_atr": Decimal("0.10"),
        "level_bucket_atr": Decimal("0.50"),
        "max_anchors": 20,
        "max_lines": 6,
        "max_channels": 3,
        "rvol_window": 96,
        "rvol_min": Decimal("1.0"),
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
            "max_violations_bounce": (INTEGER_PARAM, "violations tolerated on a bouncing line"),
            "retire_after_break": (INTEGER_PARAM, "1 = a broken line stops being a trigger"),
            "parallel_tol": (DECIMAL_PARAM, "slope difference still parallel, ATR per bar"),
            "angle_bucket_atr": (DECIMAL_PARAM, "deduplication bucket for slope, ATR per bar"),
            "level_bucket_atr": (DECIMAL_PARAM, "deduplication bucket for level at the cut"),
            "max_anchors": (INTEGER_PARAM, "most recent pivots per side used as anchors"),
            "max_lines": (INTEGER_PARAM, "lines kept after deduplication"),
            "max_channels": (INTEGER_PARAM, "channels kept"),
            "rvol_window": (INTEGER_PARAM, "bars in the relative-volume median, current excluded"),
            "rvol_min": (DECIMAL_PARAM, "minimum relative volume of the bounce bar (inclusive)"),
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
        # not change how far back a line may be drawn.
        bars: Sequence[Bar] = window.bars[-pattern_bars:]
        scan = tl_scan(
            bars, timeframe=self.timeframe, params=pattern_params(params), as_of=len(bars) - 1
        )
        if not scan.lines:
            return _not_triggered("no_line", {"pivots": str(len(scan.pivots))})

        # ``MODE_BOUNCE`` is a constant, never a parameter: the two doors are two
        # hypotheses (T3.34c), and this version is one of them.
        found = find_trigger(scan, MODE_BOUNCE)
        if found is None:
            return _not_triggered("no_event", {"lines": str(len(scan.lines))})
        event, line = found

        rvol = relative_volume(window.bars, rvol_window)
        if rvol is None:
            return _unavailable("rvol_unavailable", {"rvol_window": str(rvol_window)})
        if rvol < param_decimal(params, "rvol_min"):
            return _not_triggered("rvol_low", {"relative_volume_15m": canonical_number(rvol)})

        tolerated = param_int(params, "max_violations_bounce")
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
            # Without a confirmed low there is no structural stop, and inventing a
            # purely ATR one would be a different strategy: report, do not guess.
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
        rvol: Decimal,
        setup: TlSetup,
    ) -> Evaluation:
        """Levels, the two guards and the envelope — the second half of the rule."""
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
        # No third guard: ``v1``'s ``geometry_invalidation`` protected a level
        # this version does not read.
        if too_wide:
            return _rejected("risk_too_wide", {**levels, "risk": canonical_number(risk)})

        decision = Decision(
            direction=TradeDirection.LONG,
            reference_price=close,
            stop=stop,
            target1=target1,
            invalidations=(),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=_reason(setup, close, reading.percent, rvol, bool(width and width > floor)),
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


TRENDLINE_BOUNCE_V1: Final = TrendlineBounceV1()
"""The registered instance; strategies are stateless, so one is enough."""
