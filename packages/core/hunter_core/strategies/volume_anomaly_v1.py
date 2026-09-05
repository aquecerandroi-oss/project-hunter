"""``volume_anomaly_v1`` — 5-minute volume spike closing strong, sized by the 15m ATR.

SHADOW-LAB.md "Desenho": LONG when the 5m bar's volume is at least
``volume_mult`` times the median of the previous ``volume_window`` bars, the
close is above the bar's own midpoint, and the 5m return sits between
``return_min`` and ``return_max_atr`` times ATR% — where the ATR is **Wilder(14)
on 15m**, the same calculator the momentum strategy uses.

Two windows, requested separately and failing separately: the 5m signal window
ends at ``source_bar_close``; the 15m ATR window ends at the last *completed* 15m
close at or before it. Rounding the cut up to the next 15m boundary would be
look-ahead, and passing an unaligned cut to a 15m aggregation would make two
evaluations out of three unavailable (Astra, S1 design review, must-fix 2).

The stop is the low of the signal bar, so it is not derived from the ATR; the
target is ``target_atr`` ATR above the reference close. Every threshold lives in
:data:`VolumeAnomalyV1.default_parameters`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import align_open_time
from hunter_core.strategies.aggregate import aggregate
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
from hunter_core.strategies.indicators import atr_percent, median, return_n, wilder_atr
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of

_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")
"""Two decimals, for the human sentence only — never for a comparison."""
_TWO: Final = Decimal(2)


def _pct(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return f"{(value * _PERCENT).quantize(_DISPLAY):f}"


def _ratio(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return f"{value.quantize(_DISPLAY):f}"


class VolumeAnomalyV1:
    """The frozen v1 volume-anomaly strategy. Stateless and pure."""

    key: str = "volume_anomaly_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M5

    default_parameters: Mapping[str, Any] = {
        "volume_window": 288,
        "volume_mult": Decimal("4"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "return_min": Decimal("0"),
        "return_max_atr": Decimal("2"),
        "target_atr": Decimal("1.5"),
        "horizon_s": 7200,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "volume_window": (INTEGER_PARAM, "bars in the volume median, current excluded"),
            "volume_mult": (DECIMAL_PARAM, "volume / median floor (inclusive)"),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
            "atr_bars": (INTEGER_PARAM, "bars the ATR is recomputed from (rolling_window_v1)"),
            "return_min": (DECIMAL_PARAM, "5m return floor, inclusive"),
            "return_max_atr": (DECIMAL_PARAM, "5m return ceiling in ATR%, inclusive"),
            "target_atr": (DECIMAL_PARAM, "target1 distance from the reference, in ATR"),
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
            return Evaluation(
                None,
                EvaluationState.INELIGIBLE,
                "ineligible",
                {"eligibility_reason": ctx.eligibility_reason or "unknown"},
            )

        volume_window = param_int(params, "volume_window")
        atr_period = param_int(params, "atr_period")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])

        window = aggregate(ctx.candles_1m, self.timeframe, ctx.source_bar_close, volume_window + 1)
        if not window.available:
            return Evaluation(None, EvaluationState.UNAVAILABLE, window.reason or "", window.detail)

        atr_end = align_open_time(ctx.source_bar_close, atr_timeframe)
        atr_window = aggregate(ctx.candles_1m, atr_timeframe, atr_end, atr_bars)
        if not atr_window.available:
            return Evaluation(
                None, EvaluationState.UNAVAILABLE, f"atr_{atr_window.reason}", atr_window.detail
            )
        atr = wilder_atr(atr_window.bars, atr_period)
        atr_pct = None if atr is None else atr_percent(atr, atr_window.bars[-1].close)
        if atr is None or atr_pct is None:
            return Evaluation(None, EvaluationState.UNAVAILABLE, "atr_warmup", {})

        bars = window.bars
        signal = bars[-1]
        baseline = median([bar.volume for bar in bars[-volume_window - 1 : -1]])
        change = return_n(bars, 1)
        if change is None:
            return Evaluation(None, EvaluationState.UNAVAILABLE, "warmup", {})
        if baseline is None or baseline == 0:
            return Evaluation(
                None,
                EvaluationState.UNAVAILABLE,
                "volume_baseline_unavailable",
                {"volume_window": str(volume_window)},
            )
        with localcontext(CONTEXT):
            ratio = signal.volume / baseline
            bar_mid = (signal.high + signal.low) / _TWO
            return_max = param_decimal(params, "return_max_atr") * atr_pct

        if ratio < param_decimal(params, "volume_mult"):
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "volume_below_threshold",
                {"volume_ratio_5m": canonical_number(ratio)},
            )
        if signal.close <= bar_mid:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "close_below_mid",
                {
                    "close_5m": canonical_number(signal.close),
                    "bar_mid_5m": canonical_number(bar_mid),
                },
            )
        if not param_decimal(params, "return_min") <= change <= return_max:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "return_out_of_range",
                {
                    "return_5m": canonical_number(change),
                    "return_max_5m": canonical_number(return_max),
                },
            )

        stop = signal.low
        with localcontext(CONTEXT):
            target1 = signal.close + param_decimal(params, "target_atr") * atr.value
        if not 0 < stop < signal.close < target1:
            return Evaluation(
                None,
                EvaluationState.REJECTED,
                "geometry",
                {
                    "stop": canonical_number(stop),
                    "reference_price": canonical_number(signal.close),
                    "target1": canonical_number(target1),
                },
            )

        envelope = SupportingFeatures(
            observation_ts=ctx.source_bar_close,
            timeframe=self.timeframe.value,
            strategy_key=self.key,
            strategy_version=self.version,
            features=(
                # the reference bar itself: the stop *is* its low, and the midpoint
                # must stay checkable after the 1m candles are gone
                FeatureEvidence(name="open_5m", value=signal.open, source_ts=signal.open_time),
                FeatureEvidence(name="high_5m", value=signal.high),
                FeatureEvidence(name="low_5m", value=signal.low),
                FeatureEvidence(name="close_5m", value=signal.close, source_ts=signal.close_time),
                FeatureEvidence(name="volume_5m", value=signal.volume),
                FeatureEvidence(name="volume_median_5m", value=baseline, window=volume_window),
                FeatureEvidence(name="volume_ratio_5m", value=ratio, window=volume_window),
                FeatureEvidence(name="bar_mid_5m", value=bar_mid),
                FeatureEvidence(name="return_5m", value=change, window=1),
                FeatureEvidence(name="return_max_5m", value=return_max),
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
            reference_price=signal.close,
            stop=stop,
            target1=target1,
            invalidations=(
                Invalidation(kind="close_below", level=bar_mid, timeframe=self.timeframe.value),
            ),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=(
                f"Volume anomaly 5m: volume {canonical_number(signal.volume)} é "
                f"{_ratio(ratio)}x a mediana das {volume_window} barras anteriores, "
                f"fechamento {canonical_number(signal.close)} acima do meio da barra "
                f"({canonical_number(bar_mid)}), retorno 5m {_pct(change)}% dentro do "
                f"teto de {_pct(return_max)}% "
                f"({canonical_number(param_decimal(params, 'return_max_atr'))}x ATR% de "
                f"{atr_timeframe.value})"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


VOLUME_ANOMALY_V1: Final = VolumeAnomalyV1()
"""The registered instance; strategies are stateless, so one is enough."""
