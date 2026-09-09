"""``mean_reversion_h1_v1`` — a irmã de ``mean_reversion_v1`` que **decide em 1 h**.

Brief `.claude/state/brief-T3.54-eixo-de-timeframe.md`, EXP-0021, medições em
`.claude/state/notes-T3.54.md`. A tese é a identidade de custo da [[KB-0076]]
(``custo_R = 0,0020 / (stop_atr × ATR%)``) no eixo que ninguém tinha mexido:
medido em 16 mercados × 31 dias, ATR%(15m) p50 = 0,5585 % e ATR%(1h) = 1,2331 %
— razão **2,208** (2,128 a 2,486 por mercado), logo 2,2× menos pedágio por R.

**Por que um módulo e não um parâmetro.** ``mean_reversion_v1.timeframe`` é
atributo de classe: ``derive_variant.py`` não o alcança. E uma subclasse não
serviria — as evidências do envelope da mãe se chamam ``close_15m``/
``zscore_15m``, e herdá-las carimbaria uma barra de 1 h com o nome ``_15m``. O
envelope é o que audita a decisão; mentir nele é pior do que copiar o corpo.
**E não importa a mãe:** ``version_code_ref`` congela cada versão com o fecho
transitivo dos irmãos que ela importa, então importá-la moveria o digest desta
irmã a cada edição da mãe e amarraria dois experimentos que precisam poder
divergir. O fecho aqui é o da mãe **mais este módulo**, e o digest da mãe não se
move — provado no teste irmão.

**Três parâmetros mudam, e só três**, porque a grade inteira é escalada por 4 e o
experimento tem um eixo só: ``trend_timeframe`` ``1h`` → ``4h`` (a mãe mede
tendência no timeframe 4× o da decisão dela; esta também), ``atr_timeframe``
``15m`` → ``1h`` e ``horizon_s`` ``14400`` → ``57600`` (16 barras da grade, como a
mãe). Todo o resto — janelas, faixa de ATR%, geometria, confiança e custos — é
**byte a byte** o contrato da mãe, ``invalidations = ()`` (KB-0006, INV-B) junto.

**O custo operacional, declarado.** A janela de ATR pede ``97 × 60 = 5820`` min de
velas de 1 min e a de tendência até ``3 × 60 + 21 × 240 = 5220``; o worker corta o
contexto em ``SHADOW_CONTEXT_MINUTES``, hoje **1560** (26 h, dimensionado para os
1455 min da mãe). Logo **esta versão não decide nada hoje**: responde
``atr_warmup`` em toda barra — medido, na variante-parâmetro equivalente
(``mean_reversion v9``): 5760 barras, 100 % ``atr_warmup``. Rodá-la exige subir o
botão para ao menos 5820 (recomendado 5880), e ele é **compartilhado**: encarece
cada avaliação de toda versão viva. É decisão de operação, não desta versão — daí
o número estar fixado em teste em vez de a grade ter sido encolhida. Encolher tem
preço medido: com ``atr_bars = 24`` o ATR% mediano cai para 0,905–0,975 do de 97
barras (peso da semente 0,23 % → 51,3 %), e um ``trend_sma_bars`` que coubesse
poria a tendência no **mesmo** horizonte do z-score, onde as duas condições se
contradizem e nada dispararia.

Ordem dos motivos, parte do contrato, idêntica à da mãe: elegibilidade, janela de
sinal, janela de ATR, tendência, esticamento, estabilização, piso de custo,
geometria. Indisponibilidade nunca vira "condição falsa".
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
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, schema_of

_TIMEFRAME_PARAM: Final[Mapping[str, Any]] = {
    "type": "string",
    "enum": ["1m", "5m", "15m", "1h", "4h"],
}
"""``schema.TIMEFRAME_PARAM`` mais ``4h``, e mora **aqui** por isso: ``schema``
está dentro do fecho da mãe, de ``momentum_v1`` e de ``volume_anomaly_v1``, e
acrescentar um valor lá moveria o ``code_ref`` de toda versão já ativada na VPS
(a linha ``paper`` inclusive) — o motivo que pôs ``constraints.py`` fora (T3.26c)."""

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


class MeanReversionH1V1:
    """A reversão à média que decide em barras de 1 h. Sem estado e pura."""

    key: str = "mean_reversion_h1_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.H1

    default_parameters: Mapping[str, Any] = {
        "trend_timeframe": Timeframe.H4.value,
        "trend_sma_bars": 20,
        "zscore_bars": 20,
        "zscore_depth_min": Decimal("1"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.H1.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.006"),
        "atr_pct_max": Decimal("0.05"),
        "stop_atr": Decimal("1"),
        "target_atr": Decimal("1.5"),
        "target2_atr": Decimal("2.5"),
        "horizon_s": 57600,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "trend_timeframe": (_TIMEFRAME_PARAM, "timeframe of the trend gate"),
            "trend_sma_bars": (INTEGER_PARAM, "bars in the trend SMA, current bar excluded"),
            "zscore_bars": (INTEGER_PARAM, "1h closes in the z-score, current bar included"),
            "zscore_depth_min": (
                DECIMAL_PARAM,
                "how many sd below the mean the close must be (z <= -this)",
            ),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (_TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
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

        # A barra de 4 h em formação nunca entra: ``align_open_time`` corta no
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
                "no_uptrend_4h",
                {
                    "close_4h": canonical_number(trend_close),
                    "sma_4h": canonical_number(trend_sma),
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
                {"zscore_bars": str(zscore_bars), "sma_1h": canonical_number(mean)},
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
                {"zscore_1h": canonical_number(zscore)},
            )
        if signal.close < bar_mid:
            return Evaluation(
                None,
                EvaluationState.NOT_TRIGGERED,
                "close_below_mid",
                {
                    "close_1h": canonical_number(signal.close),
                    "bar_mid_1h": canonical_number(bar_mid),
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
                {"atr_pct_1h": canonical_number(atr_pct)},
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
                FeatureEvidence(name="open_1h", value=signal.open, source_ts=signal.open_time),
                FeatureEvidence(name="high_1h", value=signal.high),
                FeatureEvidence(name="low_1h", value=signal.low),
                FeatureEvidence(name="volume_1h", value=signal.volume),
                FeatureEvidence(name="close_1h", value=close, source_ts=signal.close_time),
                # média e desvio ao lado do z-score: um z sozinho não é auditável
                FeatureEvidence(name="sma_1h", value=mean, window=zscore_bars),
                FeatureEvidence(name="sd_1h", value=sd, window=zscore_bars),
                FeatureEvidence(name="zscore_1h", value=zscore, window=zscore_bars),
                FeatureEvidence(name="bar_mid_1h", value=bar_mid),
                FeatureEvidence(
                    name="close_4h", value=trend_close, source_ts=trend_bars[-1].close_time
                ),
                FeatureEvidence(name="sma_4h", value=trend_sma, window=trend_sma_bars),
                FeatureEvidence(name="atr_pct_1h", value=atr_pct, window=atr_bars),
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
                f"Mean reversion 1h: fechamento {canonical_number(close)} a "
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


MEAN_REVERSION_H1_V1: Final = MeanReversionH1V1()
"""A instância registrada; estratégias não têm estado, então uma basta."""
