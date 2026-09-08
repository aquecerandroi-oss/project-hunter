"""``breakout_v1`` — 15-minute breakout of the previous highs after a true-range contraction.

Brief T3.33a / EXP-0008. LONG only, ``research_only``: nothing here reaches a
wallet. The one piece of the Weinstein / O'Neil / Minervini family that survives
translation to a 15-minute crypto perpetual is that **before the breakout that
matters, volatility contracts** (KB-0053) — so this version buys a close above
the previous ``breakout_highs`` **highs** only when the recent true range is
compressed against the market's own baseline, with volume and a cost floor.

It is deliberately **not** ``momentum_v1``: the level is the maximum of the
previous *highs* (not closes); the volatility gate is an absolute floor **plus**
a relative compression ratio; the geometry is asymmetric (1.25 ATR of risk
against 2.5 ATR of target, so the break-even hit rate at the floor is 44.0 %
instead of 72.2 %); and the invalidation is the **base low** — a structural level
a guard forces to sit strictly between the stop and the reference, so it can
neither be dead code (below the stop) nor a disguised stop (above the reference).

**The estimator is named, not implied:** ``median_true_range_v1`` — Wilder's true
range, median over ``squeeze_window_bars`` against the median over
``squeeze_baseline_bars``, **both windows ending at ``t-1``**. The breakout bar is
excluded from both (KB-0053, instrument decision 3): measuring the contraction
with the expansion inside it would invert the selection. It is a *median
true-range contraction ratio*, not "VCP" — keeping a method's name while reducing
it to one indicator would import evidence this rule does not have.

**Declared numeric assumptions, none of them measured:** ``squeeze_max = 0.75``
and the ``8 / 32`` window pair are KB-0053's proposed shape with an exploratory
threshold; ``atr_pct_min = 0.005`` is a compromise between ``momentum_v1``'s
0.003 and KB-0008's 0.0089, chosen from the break-even arithmetic and not from a
fit. Every threshold lives in :data:`BreakoutV1.default_parameters`; changing one,
or any comparison operator, is a new version — never an edit here.

Order of reasons, part of the contract: eligibility, availability (signal window,
ATR window, compression baseline), the entry conditions (compression, breakout,
volume, cost floor), then the two geometry guards. An unavailable input is
``UNAVAILABLE`` and a refused geometry is ``REJECTED``, never "condition false",
so no market re-arms on a bar whose condition was never observed to be false.
Every helper lives **in this module** on purpose: ``code_ref`` freezes a version
over its own module plus the closure of the siblings it imports, so a new line in
``indicators.py`` would re-freeze the two live versions and silence the Lab.
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
    assumed_costs,
    canonical_number,
    param_decimal,
    param_int,
)
from hunter_core.strategies.envelope import AtrEvidence, FeatureEvidence, SupportingFeatures
from hunter_core.strategies.indicators import atr_percent, median, relative_volume, wilder_atr
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of

SQUEEZE_ESTIMATOR: Final = "median_true_range_v1"
"""Versioned name of the contraction estimator below; a new formula is a new name."""

_ONE: Final = Decimal("1")
_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")
"""Two decimals, for the human sentence only — never for a comparison or a
persisted value (the envelope keeps the full precision)."""
_EMPTY: Final[Mapping[str, str]] = {}


def _display(value: Decimal, scale: Decimal = _ONE) -> str:
    with localcontext(CONTEXT):
        return f"{(value * scale).quantize(_DISPLAY):f}"


def _unavailable(reason: str, detail: Mapping[str, str] = _EMPTY) -> Evaluation:
    return Evaluation(None, EvaluationState.UNAVAILABLE, reason, detail)


def _not_triggered(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.NOT_TRIGGERED, reason, detail)


def _rejected(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.REJECTED, reason, detail)


def _true_ranges(bars: Sequence[Bar]) -> list[Decimal]:
    """Wilder's true range for every bar **except the first**, which only supplies
    the previous close. Same formula as ``indicators.wilder_atr``, written again
    here because that module is inside the frozen closure of the live versions."""
    with localcontext(CONTEXT):
        return [
            max(bar.high - bar.low, abs(bar.high - before.close), abs(bar.low - before.close))
            for before, bar in zip(bars, bars[1:], strict=False)
        ]


def _max_previous_high(bars: Sequence[Bar], count: int) -> Decimal | None:
    """Highest **high** of the ``count`` bars before the last one (current excluded)."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return None if len(bars) < count + 1 else max(bar.high for bar in bars[-count - 1 : -1])


def _min_previous_low(bars: Sequence[Bar], count: int) -> Decimal | None:
    """Lowest low of the ``count`` bars before the last one — the base of the squeeze."""
    if count < 1:
        raise ValueError("count must be >= 1")
    return None if len(bars) < count + 1 else min(bar.low for bar in bars[-count - 1 : -1])


class BreakoutV1:
    """The frozen v1 volatility-compression breakout. Stateless and pure."""

    key: str = "breakout_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
        "squeeze_window_bars": 8,
        "squeeze_baseline_bars": 32,
        "squeeze_max": Decimal("0.75"),
        "breakout_highs": 20,
        "rvol_window": 96,
        "rvol_min": Decimal("1.5"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.005"),
        "atr_pct_max": Decimal("0.05"),
        "stop_atr": Decimal("1.25"),
        "target_atr": Decimal("2.5"),
        "target2_atr": Decimal("4"),
        "horizon_s": 21600,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "squeeze_window_bars": (INTEGER_PARAM, "bars in the short median true range, to t-1"),
            "squeeze_baseline_bars": (INTEGER_PARAM, "bars in the baseline median true range"),
            "squeeze_max": (DECIMAL_PARAM, "maximum mtr_short / mtr_long (inclusive)"),
            "breakout_highs": (INTEGER_PARAM, "previous highs the close must clear"),
            "rvol_window": (INTEGER_PARAM, "bars in the relative-volume median, current excluded"),
            "rvol_min": (DECIMAL_PARAM, "minimum relative volume (inclusive)"),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
            "atr_bars": (INTEGER_PARAM, "bars the ATR is recomputed from (rolling_window_v1)"),
            "atr_pct_min": (DECIMAL_PARAM, "minimum ATR/close as a fraction (inclusive)"),
            "atr_pct_max": (DECIMAL_PARAM, "maximum ATR/close as a fraction (inclusive)"),
            "stop_atr": (DECIMAL_PARAM, "stop distance from the reference, in ATR"),
            "target_atr": (DECIMAL_PARAM, "target1 distance from the reference, in ATR"),
            "target2_atr": (DECIMAL_PARAM, "informational target 2, in ATR"),
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

    # One return per contract branch, in the documented order of reasons.
    def explain(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Evaluation:
        if not ctx.eligible:
            why = {"eligibility_reason": ctx.eligibility_reason or "unknown"}
            return Evaluation(None, EvaluationState.INELIGIBLE, "ineligible", why)

        squeeze_window = param_int(params, "squeeze_window_bars")
        squeeze_baseline = param_int(params, "squeeze_baseline_bars")
        breakout_highs = param_int(params, "breakout_highs")
        rvol_window = param_int(params, "rvol_window")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])

        # ``+ 2``: the breakout bar t plus the extra prior close the first true range
        # of the baseline needs. The ATR window is requested separately, so that
        # lengthening ``atr_bars`` cannot silently raise the entry warm-up.
        window = aggregate(
            ctx.candles_1m,
            self.timeframe,
            ctx.source_bar_close,
            max(breakout_highs + 1, rvol_window + 1, squeeze_baseline + 2),
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

        bars = window.bars
        close = bars[-1].close
        # Both medians end at t-1: the breakout bar is excluded from the measure
        # of the contraction that is supposed to precede it (KB-0053, decision 3).
        true_ranges = _true_ranges(bars[:-1])
        if len(true_ranges) < squeeze_baseline:
            return _unavailable("warmup")
        mtr_short = median(true_ranges[-squeeze_window:])
        mtr_long = median(true_ranges[-squeeze_baseline:])
        if mtr_short is None or mtr_long is None or mtr_long <= 0:
            return _unavailable(
                "squeeze_baseline_unavailable", {"squeeze_baseline_bars": str(squeeze_baseline)}
            )
        with localcontext(CONTEXT):
            squeeze_ratio = mtr_short / mtr_long
        squeeze_max = param_decimal(params, "squeeze_max")
        if squeeze_ratio > squeeze_max:
            return _not_triggered(
                "not_compressed",
                {
                    "squeeze_ratio": canonical_number(squeeze_ratio),
                    "squeeze_max": canonical_number(squeeze_max),
                },
            )

        prior_high = _max_previous_high(bars, breakout_highs)
        base_low = _min_previous_low(bars, squeeze_window)
        if prior_high is None or base_low is None:
            return _unavailable("warmup")
        if close <= prior_high:
            return _not_triggered(
                "no_breakout",
                {
                    "close_15m": canonical_number(close),
                    "max_previous_high_15m": canonical_number(prior_high),
                },
            )

        rvol = relative_volume(bars, rvol_window)
        if rvol is None:
            return _unavailable("rvol_unavailable", {"rvol_window": str(rvol_window)})
        if rvol < param_decimal(params, "rvol_min"):
            return _not_triggered("rvol_low", {"relative_volume_15m": canonical_number(rvol)})
        if (
            not param_decimal(params, "atr_pct_min")
            <= atr_pct
            <= param_decimal(params, "atr_pct_max")
        ):
            return _not_triggered("atr_out_of_range", {"atr_pct_15m": canonical_number(atr_pct)})

        volume_median = median([bar.volume for bar in bars[-rvol_window - 1 : -1]])
        with localcontext(CONTEXT):
            stop = close - param_decimal(params, "stop_atr") * atr.value
            target1 = close + param_decimal(params, "target_atr") * atr.value
            informational = (close + param_decimal(params, "target2_atr") * atr.value,)
        levels = {
            "stop": canonical_number(stop),
            "reference_price": canonical_number(close),
            "target1": canonical_number(target1),
        }
        if not 0 < stop < close < target1:
            return _rejected("geometry", levels)
        # The invalidation must be a level the market can reach *before* the stop
        # and *after* the entry: below the stop it is dead code, above the
        # reference it is a stop wearing another name (notes-T3.33 §4).
        if not stop < base_low < close:
            return _rejected(
                "geometry_invalidation", {**levels, "base_low_15m": canonical_number(base_low)}
            )

        envelope = SupportingFeatures(
            observation_ts=ctx.source_bar_close,
            timeframe=self.timeframe.value,
            strategy_key=self.key,
            strategy_version=self.version,
            features=(
                # the reference bar itself, so the levels stay re-checkable after
                # the 1m candles have left the retention window
                FeatureEvidence(name="open_15m", value=bars[-1].open, source_ts=bars[-1].open_time),
                FeatureEvidence(name="high_15m", value=bars[-1].high),
                FeatureEvidence(name="low_15m", value=bars[-1].low),
                FeatureEvidence(name="volume_15m", value=bars[-1].volume),
                FeatureEvidence(name="close_15m", value=close, source_ts=bars[-1].close_time),
                FeatureEvidence(
                    name="max_previous_high_15m", value=prior_high, window=breakout_highs
                ),
                FeatureEvidence(name="relative_volume_15m", value=rvol, window=rvol_window),
                FeatureEvidence(name="volume_median_15m", value=volume_median, window=rvol_window),
                FeatureEvidence(name="mtr_short", value=mtr_short, window=squeeze_window),
                FeatureEvidence(name="mtr_long", value=mtr_long, window=squeeze_baseline),
                FeatureEvidence(name="squeeze_ratio", value=squeeze_ratio),
                FeatureEvidence(name="squeeze_estimator", value=SQUEEZE_ESTIMATOR),
                FeatureEvidence(name="base_low_15m", value=base_low, window=squeeze_window),
                FeatureEvidence(name="atr_pct_15m", value=atr_pct, window=atr_bars),
            ),
            atr=AtrEvidence(
                method=atr.method,
                origin=atr.origin,
                timeframe=atr_timeframe.value,
                period=atr.period,
                value=atr.value,
                percent=atr_pct,
                seed=atr.seed,
                seed_anchor=atr.seed_anchor,
                bars_used=atr.bars_used,
                window_start=atr.window_start,
                window_end=atr_end,
            ),
            assumed_costs=assumed_costs(params),
            eligible=ctx.eligible,
            eligibility_reason=ctx.eligibility_reason,
        )
        decision = Decision(
            direction=TradeDirection.LONG,
            reference_price=close,
            stop=stop,
            target1=target1,
            targets_informational=informational,
            invalidations=(
                Invalidation(kind="close_below", level=base_low, timeframe=self.timeframe.value),
            ),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=(
                f"Breakout 15m: fechamento {canonical_number(close)} acima da máxima das "
                f"{breakout_highs} máximas anteriores ({canonical_number(prior_high)}), "
                f"após compressão do true range (mediana de {squeeze_window} barras / "
                f"mediana de {squeeze_baseline} barras = {_display(squeeze_ratio)}), "
                f"volume relativo {_display(rvol)}x da mediana de {rvol_window} barras, "
                f"ATR% {_display(atr_pct, _PERCENT)}%"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


BREAKOUT_V1: Final = BreakoutV1()
"""The registered instance; strategies are stateless, so one is enough."""
