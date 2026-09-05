"""``momentum_v1`` — 15-minute continuation breakout with volume and volatility gates.

SHADOW-LAB.md "Desenho": LONG when the 15m close clears the highest of the
previous ``lookback_closes`` closes, the 15m return is positive, relative volume
is at least ``rvol_min`` against the median of the previous ``rvol_window`` bars,
and ATR%(Wilder 14 on 15m) sits inside ``[atr_pct_min, atr_pct_max]``. Stop and
target are both ``1.5 ATR`` from the reference close — **1 R nominal at the
reference**, which is not 1 R at the entry (the entry is a later 1m open).

Every threshold lives in :data:`MomentumV1.default_parameters`; there is no
number in the code path. Changing any of them, or any comparison operator, is a
new strategy version — never an edit here (SHADOW-LAB.md §1).

Order of reasons, stable and part of the contract: eligibility, then data
availability (window, ATR window, indicators), then the entry conditions in the
order above, then geometry. Availability is reported as ``UNAVAILABLE`` and never
as "condition false", so the worker cannot re-arm a market on a bar it could not
evaluate.
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
from hunter_core.strategies.indicators import (
    atr_percent,
    max_previous_close,
    median,
    relative_volume,
    return_n,
    wilder_atr,
)
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of

_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")
"""Two decimals, for the human sentence only — never for a comparison or a
persisted value (the envelope keeps the full precision)."""


def _pct(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return f"{(value * _PERCENT).quantize(_DISPLAY):f}"


def _ratio(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return f"{value.quantize(_DISPLAY):f}"


class MomentumV1:
    """The frozen v1 momentum strategy. Stateless and pure."""

    key: str = "momentum_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
        "lookback_closes": 20,
        "rvol_window": 96,
        "rvol_min": Decimal("1.5"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.003"),
        "atr_pct_max": Decimal("0.05"),
        "return_min": Decimal("0"),
        "stop_atr": Decimal("1.5"),
        "target_atr": Decimal("1.5"),
        "target2_atr": Decimal("3"),
        "target3_atr": Decimal("4.5"),
        "horizon_s": 14400,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "lookback_closes": (INTEGER_PARAM, "closes the breakout must clear, current excluded"),
            "rvol_window": (INTEGER_PARAM, "bars in the relative-volume median, current excluded"),
            "rvol_min": (DECIMAL_PARAM, "minimum relative volume (inclusive)"),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
            "atr_bars": (INTEGER_PARAM, "bars the ATR is recomputed from (rolling_window_v1)"),
            "atr_pct_min": (DECIMAL_PARAM, "minimum ATR/close as a fraction (inclusive)"),
            "atr_pct_max": (DECIMAL_PARAM, "maximum ATR/close as a fraction (inclusive)"),
            "return_min": (DECIMAL_PARAM, "15m return floor, exclusive: return > return_min"),
            "stop_atr": (DECIMAL_PARAM, "stop distance from the reference, in ATR"),
            "target_atr": (DECIMAL_PARAM, "target1 distance from the reference, in ATR"),
            "target2_atr": (DECIMAL_PARAM, "informational target 2, in ATR"),
            "target3_atr": (DECIMAL_PARAM, "informational target 3, in ATR"),
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

        lookback = param_int(params, "lookback_closes")
        rvol_window = param_int(params, "rvol_window")
        atr_period = param_int(params, "atr_period")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])

        # The signal window and the ATR window are requested independently: the
        # signal window is only as long as the entry conditions need, and lengthening
        # ``atr_bars`` must not silently raise the warm-up of the breakout.
        window = aggregate(
            ctx.candles_1m,
            self.timeframe,
            ctx.source_bar_close,
            max(lookback + 1, rvol_window + 1),
        )
        if not window.available:
            return Evaluation(None, EvaluationState.UNAVAILABLE, window.reason or "", window.detail)

        atr_end = align_open_time(ctx.source_bar_close, atr_timeframe)
        atr_window = aggregate(ctx.candles_1m, atr_timeframe, atr_end, atr_bars)
        if not atr_window.available:
            return Evaluation(
                None, EvaluationState.UNAVAILABLE, f"atr_{atr_window.reason}", atr_window.detail
            )
        atr = wilder_atr(atr_window.bars, atr_period)
        atr_close = atr_window.bars[-1].close
        atr_pct = None if atr is None else atr_percent(atr, atr_close)
        if atr is None or atr_pct is None:
            return Evaluation(None, EvaluationState.UNAVAILABLE, "atr_warmup", {})

        bars = window.bars
        close = bars[-1].close
        prior_max = max_previous_close(bars, lookback)
        change = return_n(bars, 1)
        rvol = relative_volume(bars, rvol_window)
        if prior_max is None or change is None:
            return Evaluation(None, EvaluationState.UNAVAILABLE, "warmup", {})
        if rvol is None:
            return Evaluation(
                None,
                EvaluationState.UNAVAILABLE,
                "rvol_unavailable",
                {"rvol_window": str(rvol_window)},
            )

        if close <= prior_max:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "no_breakout",
                {
                    "close_15m": canonical_number(close),
                    "max_previous_close_15m": canonical_number(prior_max),
                },
            )
        if change <= param_decimal(params, "return_min"):
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "return_not_positive",
                {"return_15m": canonical_number(change)},
            )
        if rvol < param_decimal(params, "rvol_min"):
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "rvol_low",
                {"relative_volume_15m": canonical_number(rvol)},
            )
        if (
            not param_decimal(params, "atr_pct_min")
            <= atr_pct
            <= param_decimal(params, "atr_pct_max")
        ):
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "atr_out_of_range",
                {"atr_pct_15m": canonical_number(atr_pct)},
            )

        with localcontext(CONTEXT):
            stop = close - param_decimal(params, "stop_atr") * atr.value
            target1 = close + param_decimal(params, "target_atr") * atr.value
            informational = (
                close + param_decimal(params, "target2_atr") * atr.value,
                close + param_decimal(params, "target3_atr") * atr.value,
            )
        if not 0 < stop < close < target1:
            return Evaluation(
                None,
                EvaluationState.REJECTED,
                "geometry",
                {
                    "stop": canonical_number(stop),
                    "reference_price": canonical_number(close),
                    "target1": canonical_number(target1),
                },
            )

        envelope = SupportingFeatures(
            observation_ts=ctx.source_bar_close,
            timeframe=self.timeframe.value,
            strategy_key=self.key,
            strategy_version=self.version,
            features=(
                # the reference bar itself, so the levels can be re-checked even
                # after the 1m candles have left the retention window
                FeatureEvidence(name="open_15m", value=bars[-1].open, source_ts=bars[-1].open_time),
                FeatureEvidence(name="high_15m", value=bars[-1].high),
                FeatureEvidence(name="low_15m", value=bars[-1].low),
                FeatureEvidence(name="volume_15m", value=bars[-1].volume),
                FeatureEvidence(name="close_15m", value=close, source_ts=bars[-1].close_time),
                FeatureEvidence(name="max_previous_close_15m", value=prior_max, window=lookback),
                FeatureEvidence(name="return_15m", value=change, window=1),
                FeatureEvidence(name="relative_volume_15m", value=rvol, window=rvol_window),
                FeatureEvidence(
                    name="volume_median_15m",
                    value=median([bar.volume for bar in bars[-rvol_window - 1 : -1]]),
                    window=rvol_window,
                ),
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
                Invalidation(kind="close_below", level=prior_max, timeframe=self.timeframe.value),
            ),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=(
                f"Momentum 15m: fechamento {canonical_number(close)} acima da máxima dos "
                f"{lookback} fechamentos anteriores ({canonical_number(prior_max)}), "
                f"retorno 15m {_pct(change)}%, volume relativo {_ratio(rvol)}x da mediana de "
                f"{rvol_window} barras, ATR% {_pct(atr_pct)}%"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


MOMENTUM_V1: Final = MomentumV1()
"""The registered instance; strategies are stateless, so one is enough."""
