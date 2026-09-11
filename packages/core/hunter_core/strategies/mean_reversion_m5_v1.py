"""``mean_reversion_m5_v1`` — a irmã de ``mean_reversion_v1`` que **decide em 5 m**.

Brief `.claude/state/brief-T3.84-lote-diario-5min.md`, pré-registro EXP-0028. É o
eixo que a T3.54 abriu para cima (``mean_reversion_h1_v1``, 1 h) percorrido para
**baixo**: o Everton pediu 5 m/10 m/1 h e a condição que ele pôs — atraso de
decisão < 5 s — foi atendida (p50 2,2 s).

**O prior é contrário, e está escrito no pré-registro antes de qualquer replay.**
A identidade de custo da [[KB-0076]] é ``custo_R = 0,0020 / (stop_atr × ATR%)``:
o ATR% de uma barra de 5 m é **menor** que o de 15 m, logo o pedágio por R aqui é
**maior** — a direção oposta ao ganho medido na irmã de 1 h (ATR%(1h)/ATR%(15m) =
2,208). A [[KB-0086]] mediu 460/460 células de custo negativas em 5 m no perp do
BTC mesmo com IC positivo, e a família de 15 m já é negativa em 90 d (EXP-0025).

**Por que um módulo e não um parâmetro**, idêntico ao motivo da irmã de 1 h:
``mean_reversion_v1.timeframe`` é atributo de classe e ``derive_variant.py`` não
o alcança; e herdar da mãe carimbaria uma barra de 5 m com evidências chamadas
``close_15m``/``zscore_15m``, mentindo no objeto que audita a decisão. Importar a
mãe também está fora: ``version_code_ref`` congela cada versão com o fecho
transitivo dos irmãos que ela importa, então o digest desta irmã andaria a cada
edição da mãe. O fecho aqui é o da mãe **mais este módulo**, e o digest da mãe
não se move — provado no teste irmão.

**Três parâmetros mudam, e só três** — os mesmos três nomes da irmã de 1 h,
porque o experimento tem um eixo só:

- ``atr_timeframe`` ``15m`` → ``5m``: as duas medem o ATR **na própria grade de
  decisão** (a mãe em 15 m decidindo em 15 m; a de 1 h, em 1 h);
- ``trend_timeframe`` ``1h`` → ``15m``: a mãe e a irmã de 1 h usam o timeframe
  **4×** o da decisão, e 4 × 5 m = 20 m **não existe** em
  ``hunter_core.domain.enums.Timeframe`` (1m, 5m, 15m, 1h, 4h, 1d). A regra que
  as duas realizam e que a grade suporta é "o degrau seguinte da grade", e para
  5 m ele é 15 m — 3×, não 4×. É declarado aqui porque é a única liberdade que
  esta derivação teve: a alternativa (1 h, 12×) poria a tendência a doze vezes o
  horizonte do z-score, onde a porta deixa de falar da janela da entrada;
- ``horizon_s`` ``14400`` → ``4800``: 16 barras da grade, como as duas irmãs.

Todo o resto — janelas, faixa de ATR%, geometria, confiança e custos — é **byte a
byte** o contrato da mãe, ``invalidations = ()`` (KB-0006, INV-B) junto.

**O custo operacional, declarado — e aqui ele é zero.** A janela de ATR pede
``97 × 5 = 485`` min e a de tendência ``21 × 15 + (15 − 5) = 325``; com a folga
de uma barra o requisito é **490** min, muito abaixo do piso de
``SHADOW_CONTEXT_MINUTES`` (1560) e do teto de ``SHADOW_CONTEXT_MAX_MINUTES``
(6000). Ao contrário da irmã de 1 h, que nasceu muda e precisou do botão subir
para 5880, esta decide desde a primeira barra sem encarecer ninguém: o
``min(max(requisito, piso), teto)`` devolve os mesmos 1560 da faixa viva. O
número é declarado em ``hunter_strategy_worker.context_budget.WINDOWS``, e o
teste espião o confere contra as chamadas reais de ``aggregate``.

Ordem dos motivos, parte do contrato, idêntica à da mãe: elegibilidade, janela de
sinal, janela de ATR, tendência, esticamento, estabilização, piso de custo,
geometria. Indisponibilidade nunca vira "condição falsa"."""

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
    """Média e **desvio populacional** (divisor ``n``: a janela não é amostra, é a
    janela declarada) sob :data:`CONTEXT`. Copiada da mãe, não importada dela."""
    with localcontext(CONTEXT):
        count = Decimal(len(closes))
        mean = sum(closes, start=_ZERO) / count
        variance = sum(((close - mean) ** 2 for close in closes), start=_ZERO) / count
        return mean, variance.sqrt()


class MeanReversionM5V1:
    """A reversão à média que decide em barras de 5 m. Sem estado e pura."""

    key: str = "mean_reversion_m5_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M5

    default_parameters: Mapping[str, Any] = {
        "trend_timeframe": Timeframe.M15.value,
        "trend_sma_bars": 20,
        "zscore_bars": 20,
        "zscore_depth_min": Decimal("1"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M5.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.006"),
        "atr_pct_max": Decimal("0.05"),
        "stop_atr": Decimal("1"),
        "target_atr": Decimal("1.5"),
        "target2_atr": Decimal("2.5"),
        "horizon_s": 4800,
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
            "zscore_bars": (INTEGER_PARAM, "5m closes in the z-score, current bar included"),
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

        # A barra de 15 m em formação nunca entra: ``align_open_time`` corta no
        # início dela, e a última barra da janela é a última **completa**.
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
                "no_uptrend_15m",
                {
                    "close_15m": canonical_number(trend_close),
                    "sma_15m": canonical_number(trend_sma),
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
                {"zscore_bars": str(zscore_bars), "sma_5m": canonical_number(mean)},
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
                {"zscore_5m": canonical_number(zscore)},
            )
        if signal.close < bar_mid:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "close_below_mid",
                {
                    "close_5m": canonical_number(signal.close),
                    "bar_mid_5m": canonical_number(bar_mid),
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
                {"atr_pct_5m": canonical_number(atr_pct)},
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
                FeatureEvidence(name="open_5m", value=signal.open, source_ts=signal.open_time),
                FeatureEvidence(name="high_5m", value=signal.high),
                FeatureEvidence(name="low_5m", value=signal.low),
                FeatureEvidence(name="volume_5m", value=signal.volume),
                FeatureEvidence(name="close_5m", value=close, source_ts=signal.close_time),
                # média e desvio ao lado do z-score: um z sozinho não é auditável
                FeatureEvidence(name="sma_5m", value=mean, window=zscore_bars),
                FeatureEvidence(name="sd_5m", value=sd, window=zscore_bars),
                FeatureEvidence(name="zscore_5m", value=zscore, window=zscore_bars),
                FeatureEvidence(name="bar_mid_5m", value=bar_mid),
                FeatureEvidence(
                    name="close_15m", value=trend_close, source_ts=trend_bars[-1].close_time
                ),
                FeatureEvidence(name="sma_15m", value=trend_sma, window=trend_sma_bars),
                FeatureEvidence(name="atr_pct_5m", value=atr_pct, window=atr_bars),
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
                f"Mean reversion 5m: fechamento {canonical_number(close)} a "
                f"{_ratio(zscore)} desvios da média de {zscore_bars} fechamentos "
                f"({canonical_number(mean)}), dentro de tendência de alta de "
                f"{trend_timeframe.value} (fechamento {canonical_number(trend_close)} acima "
                f"da SMA de {trend_sma_bars} barras, {canonical_number(trend_sma)}), "
                f"fechamento acima do meio da barra ({canonical_number(bar_mid)}), "
                f"ATR% {_pct(atr_pct)}%"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


MEAN_REVERSION_M5_V1: Final = MeanReversionM5V1()
"""A instância registrada; estratégias não têm estado, então uma basta."""
