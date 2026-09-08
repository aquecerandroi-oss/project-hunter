"""``mean_reversion_v1`` — recuo comprado dentro de uma tendência de 1 h (15 m).

Brief `.claude/state/brief-T3.33b-mean_reversion_v1.md`, experimento EXP-0009. O
Lab só sabia comprar força (``momentum_v1`` compra rompimento, ``volume_anomaly_v1``
compra pico de volume); esta versão compra **fraqueza dentro de força**, que é o
único jeito de separar "a regra erra" de "o mercado caiu".

LONG quando, num fechamento de 15 m: a última hora **completa** fecha acima da
média dos ``trend_sma_bars`` fechamentos horários anteriores (a hora em formação
nunca entra), o fechamento de 15 m está a pelo menos ``zscore_depth_min`` desvios
**abaixo** da média dos ``zscore_bars`` últimos fechamentos (barra atual incluída,
desvio populacional), a barra fecha acima do próprio meio, e o ATR%(Wilder 14 em
15 m) fica dentro de ``[atr_pct_min, atr_pct_max]``.

Três decisões que valem estar escritas aqui e não só no brief:

- **``invalidations = ()``, de propósito.** É o braço ``INV-B`` da KB-0006: stop,
  alvo e horizonte são a política de saída inteira. Uma entrada cuja tese é "o
  preço está *abaixo* do que deveria" não pode carregar uma regra que sai quando
  o preço cai mais.
- **A geometria é 1,0 ATR de stop e 1,5 ATR de alvo, não o contrário.** A
  geometria "natural" da reversão à média (alvo pequeno, stop largo) pede 86,7 %
  de acerto para empatar com o custo assumido do Lab; esta pede 53,4 % no piso de
  ATR% (notes-T3.33 §4).
- **O z-score mora aqui dentro.** ``version_code_ref`` congela cada versão com o
  fecho transitivo dos irmãos que ela importa; pôr o cálculo em ``indicators.py``
  re-congelaria ``momentum_v1`` e ``volume_anomaly_v1`` e o Lab inteiro
  emudeceria atrás de um ``/ready`` verde.

Ordem dos motivos, estável e parte do contrato: elegibilidade, janela de sinal,
janela de ATR, porta de tendência, esticamento, estabilização, piso de custo,
geometria. Indisponibilidade nunca é reportada como "condição falsa", para o
worker não re-armar um mercado numa barra que ele não conseguiu avaliar.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import align_open_time
from hunter_core.strategies.aggregate import aggregate
from hunter_core.strategies.base import (
    Decision,
    Evaluation,
    EvaluationState,
    StrategyContext,
    assumed_costs,
    canonical_number,
    param_decimal,
    param_int,
)
from hunter_core.strategies.envelope import AtrEvidence, FeatureEvidence, SupportingFeatures
from hunter_core.strategies.indicators import atr_percent, wilder_atr
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of

_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")
"""Duas casas, só para a frase humana — nunca para uma comparação ou um valor
persistido (o envelope guarda a precisão inteira)."""
_TWO: Final = Decimal(2)
_ZERO: Final = Decimal(0)


def _pct(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return f"{(value * _PERCENT).quantize(_DISPLAY):f}"


def _ratio(value: Decimal) -> str:
    with localcontext(CONTEXT):
        return f"{value.quantize(_DISPLAY):f}"


def _dispersion(closes: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    """Média e **desvio populacional** de ``closes``, sob :data:`CONTEXT`.

    Populacional (divisor ``n``, não ``n − 1``) porque a janela não é uma amostra
    de nada: é a janela declarada inteira. Vive neste módulo, e não em
    ``indicators.py``, pelo motivo do docstring do módulo.
    """
    with localcontext(CONTEXT):
        count = Decimal(len(closes))
        mean = sum(closes, start=_ZERO) / count
        variance = sum(((close - mean) ** 2 for close in closes), start=_ZERO) / count
        return mean, variance.sqrt()


class MeanReversionV1:
    """A estratégia v1 de reversão à média, congelada. Sem estado e pura."""

    key: str = "mean_reversion_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
        "trend_timeframe": Timeframe.H1.value,
        "trend_sma_bars": 20,
        "zscore_bars": 20,
        "zscore_depth_min": Decimal("1"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.006"),
        "atr_pct_max": Decimal("0.05"),
        "stop_atr": Decimal("1"),
        "target_atr": Decimal("1.5"),
        "target2_atr": Decimal("2.5"),
        "horizon_s": 14400,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "trend_timeframe": (TIMEFRAME_PARAM, "timeframe of the trend gate"),
            "trend_sma_bars": (INTEGER_PARAM, "bars in the trend SMA, current bar excluded"),
            "zscore_bars": (INTEGER_PARAM, "15m closes in the z-score, current bar included"),
            "zscore_depth_min": (
                DECIMAL_PARAM,
                "how many sd below the mean the close must be (z <= -this)",
            ),
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

    # Um return por ramo do contrato, na ordem documentada dos motivos.
    def explain(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Evaluation:
        if not ctx.eligible:
            return Evaluation(
                None,
                EvaluationState.INELIGIBLE,
                "ineligible",
                {"eligibility_reason": ctx.eligibility_reason or "unknown"},
            )

        zscore_bars = param_int(params, "zscore_bars")
        trend_sma_bars = param_int(params, "trend_sma_bars")
        trend_timeframe = Timeframe(params["trend_timeframe"])
        atr_period = param_int(params, "atr_period")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])

        # A janela de sinal tem exatamente o comprimento que o z-score pede (a
        # barra atual está dentro dele); a de ATR é pedida à parte, para que
        # alongar ``atr_bars`` não levante silenciosamente o aquecimento do sinal.
        window = aggregate(ctx.candles_1m, self.timeframe, ctx.source_bar_close, zscore_bars)
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

        # A hora em formação nunca entra: ``align_open_time`` corta no início da
        # hora corrente, e a última barra da janela é a última hora **completa**.
        trend_end = align_open_time(ctx.source_bar_close, trend_timeframe)
        trend_window = aggregate(ctx.candles_1m, trend_timeframe, trend_end, trend_sma_bars + 1)
        if not trend_window.available:
            return Evaluation(
                None,
                EvaluationState.UNAVAILABLE,
                f"trend_{trend_window.reason}",
                trend_window.detail,
            )
        trend_bars = trend_window.bars
        with localcontext(CONTEXT):
            trend_sma = sum((bar.close for bar in trend_bars[:-1]), start=_ZERO) / Decimal(
                trend_sma_bars
            )
        trend_close = trend_bars[-1].close
        if trend_close <= trend_sma:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "no_uptrend_1h",
                {
                    "close_1h": canonical_number(trend_close),
                    "sma_1h": canonical_number(trend_sma),
                },
            )

        bars = window.bars
        signal = bars[-1]
        closes = [bar.close for bar in bars[-zscore_bars:]]
        mean, sd = _dispersion(closes)
        if sd == 0:
            return Evaluation(
                None,
                EvaluationState.UNAVAILABLE,
                "zscore_degenerate",
                {"zscore_bars": str(zscore_bars), "sma_15m": canonical_number(mean)},
            )
        with localcontext(CONTEXT):
            zscore = (signal.close - mean) / sd
            depth = -param_decimal(params, "zscore_depth_min")
            bar_mid = (signal.high + signal.low) / _TWO
        if zscore > depth:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "not_stretched",
                {"zscore_15m": canonical_number(zscore)},
            )
        if signal.close < bar_mid:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "close_below_mid",
                {
                    "close_15m": canonical_number(signal.close),
                    "bar_mid_15m": canonical_number(bar_mid),
                },
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

        close = signal.close
        with localcontext(CONTEXT):
            stop = close - param_decimal(params, "stop_atr") * atr.value
            target1 = close + param_decimal(params, "target_atr") * atr.value
            informational = (close + param_decimal(params, "target2_atr") * atr.value,)
        if not _ZERO < stop < close < target1:
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
                # a barra de referência inteira: o meio dela é uma condição, e
                # nada disso pode depender de as velas de 1 min ainda existirem
                FeatureEvidence(name="open_15m", value=signal.open, source_ts=signal.open_time),
                FeatureEvidence(name="high_15m", value=signal.high),
                FeatureEvidence(name="low_15m", value=signal.low),
                FeatureEvidence(name="volume_15m", value=signal.volume),
                FeatureEvidence(name="close_15m", value=close, source_ts=signal.close_time),
                # média e desvio ao lado do z-score: um z sozinho não é auditável
                FeatureEvidence(name="sma_15m", value=mean, window=zscore_bars),
                FeatureEvidence(name="sd_15m", value=sd, window=zscore_bars),
                FeatureEvidence(name="zscore_15m", value=zscore, window=zscore_bars),
                FeatureEvidence(name="bar_mid_15m", value=bar_mid),
                FeatureEvidence(
                    name="close_1h", value=trend_close, source_ts=trend_bars[-1].close_time
                ),
                FeatureEvidence(name="sma_1h", value=trend_sma, window=trend_sma_bars),
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
            invalidations=(),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=(
                f"Mean reversion 15m: fechamento {canonical_number(close)} a "
                f"{_ratio(zscore)} desvios da média de {zscore_bars} fechamentos "
                f"({canonical_number(mean)}), dentro de tendência de alta de "
                f"{trend_timeframe.value} (fechamento {canonical_number(trend_close)} acima "
                f"da SMA de {trend_sma_bars} horas, {canonical_number(trend_sma)}), "
                f"fechamento acima do meio da barra ({canonical_number(bar_mid)}), "
                f"ATR% {_pct(atr_pct)}%"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


MEAN_REVERSION_V1: Final = MeanReversionV1()
"""A instância registrada; estratégias não têm estado, então uma basta."""
