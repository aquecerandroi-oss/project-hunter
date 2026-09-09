"""``sweep_reclaim_v1`` — a varredura de uma mínima de swing, recuperada (15 m).

Brief ``.claude/state/brief-T3.45b-sweep_reclaim_v1.md``, experimento EXP-0017. O
Lab já compra força (``momentum_v1``, ``breakout_v1``), fraqueza dentro de força
(``mean_reversion_v1``) e a quebra de uma reta (``trendline_breakout_v1``); esta
compra **a perda falsa de um suporte**: o estoque de stops abaixo de uma mínima
visível é liquidez, e a varredura que *não segura* marca o fim do desequilíbrio.

LONG quando, num fechamento de 15 m: a mínima da barra **fura** em pelo menos
``sweep_atr`` ATRs a mínima de um pivô de swing **confirmado** (``pivot_k`` barras
de cada lado, proeminência >= ``min_swing_atr``) das últimas ``pivot_lookback_bars``
barras, o **fechamento volta acima** daquela mínima, o volume relativo chega a
``rvol_min`` e a distância até o stop paga o pedágio (``risk_pct_min``).

Quatro decisões que valem estar escritas aqui e não só no brief:

- **O detector de pivô mora aqui dentro.** ``version_code_ref`` congela cada versão
  com o fecho transitivo dos irmãos que ela importa; ``tl_pivots`` já tem a mesma
  regra, e importá-lo juntaria esta versão ao fecho da ``trendline_breakout_v1``,
  onde um conserto futuro numa reta re-congelaria *esta* coorte. O fecho aqui é o
  da ``mean_reversion_v1``, e a paridade com ``tl_pivots`` é mantida por **teste**.
- **Um pivô só existe ``k`` barras depois.** ``i <= t - pivot_k`` é a regra inteira
  contra antecipação nesta versão: uma mínima em ``t-1`` *ainda não é* pivô, por
  mais que pareça uma no gráfico impresso depois.
- **Uma leitura de ATR escala tudo** — proeminência, varredura, folga do stop e
  ``risk_atr``. Divergência declarada contra ``hunter_indicators.patterns.pivots``,
  onde cada pivô é escalado pelo ATR da própria barra (EXP-0017, Protocolo).
- **``invalidations = ()``, de propósito.** Braço ``INV-B`` da KB-0006: a mínima
  varrida *é* a estrutura e já é o stop; uma regra que sai acima dele é um segundo
  stop sem tese própria — o desenho que custou ~ -53 R à ``momentum v2``. O portão
  C8 pontua isto como ``fail``; a divergência está declarada no EXP-0017 e **não é
  para ser "consertada" em código**.

Ordem dos motivos, parte do contrato: elegibilidade, janela de sinal, janela de ATR,
pivô, varredura, recuperação, volume, piso de custo, teto de risco, geometria.
Indisponibilidade nunca é "condição falsa": o worker não pode re-armar um mercado
numa barra que ele não conseguiu avaliar.
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
    assumed_costs,
    canonical_number,
    param_decimal,
    param_int,
)
from hunter_core.strategies.envelope import AtrEvidence, FeatureEvidence, SupportingFeatures
from hunter_core.strategies.indicators import atr_percent, relative_volume, wilder_atr
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of

_PERCENT: Final = Decimal("100")
_BPS: Final = Decimal("10000")
_TWO: Final = Decimal(2)
_ZERO: Final = Decimal(0)
_DISPLAY: Final = Decimal("0.01")
"""Duas casas, só para a frase humana — nunca para uma comparação nem para um
valor persistido (o envelope guarda a precisão inteira)."""


def _display(value: Decimal, scale: Decimal = Decimal(1)) -> str:
    with localcontext(CONTEXT):
        return f"{(value * scale).quantize(_DISPLAY):f}"


def _not_triggered(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.NOT_TRIGGERED, reason, detail)


def _unavailable(reason: str, detail: Mapping[str, str] | None = None) -> Evaluation:
    return Evaluation(None, EvaluationState.UNAVAILABLE, reason, detail or {})


def _round_trip(params: Mapping[str, Any]) -> Decimal:
    """Custo de ida e volta assumido, em fração do preço — 20 bps nos defaults.

    Lido dos parâmetros (``2 + 2x5 + 2x4``) em vez de cravado como ``0,0020``: o
    numerador da identidade do pedágio é a hipótese de custo do experimento, e uma
    variante que a mexa tem de mover o pedágio publicado junto.
    """
    with localcontext(CONTEXT):
        per_side = param_decimal(params, "slippage_bps") + param_decimal(params, "fee_bps")
        return (param_decimal(params, "assumed_spread_bps") + _TWO * per_side) / _BPS


def _is_swing_low(bars: Sequence[Bar], index: int, k: int) -> bool:
    """Mínima estritamente menor à esquerda e menor-ou-igual à direita — a
    assimetria é a regra 3 da T3.34: o empate vai para a barra **mais velha**, e
    um platô de mínimas iguais rende um pivô só, não três."""
    low = bars[index].low
    return all(bars[j].low > low for j in range(index - k, index)) and all(
        bars[j].low >= low for j in range(index + 1, index + k + 1)
    )


def _prominence(bars: Sequence[Bar], index: int, k: int) -> Decimal:
    """``min(maior máxima à esquerda, maior máxima à direita) - mínima do pivô``. A
    amplitude da própria barra fica **fora** dos ombros (regra 2 da T3.34):
    incluí-la fazia a proeminência valer ~1 ATR por construção."""
    left = max(bars[j].high for j in range(index - k, index))
    right = max(bars[j].high for j in range(index + 1, index + k + 1))
    return min(left, right) - bars[index].low


def _latest_pivot_low(
    bars: Sequence[Bar], *, k: int, lookback: int, scale: Decimal, min_swing_atr: Decimal
) -> tuple[int, Decimal] | None:
    """``(índice, proeminência em ATR)`` do pivô confirmado mais recente, ou ``None``.
    O teto do laço é ``t - k`` e é o ponto inteiro: um pivô só é *conhecido* ``k``
    barras depois, então uma mínima em ``t-1`` não existe para quem decide em ``t``."""
    last = len(bars) - 1
    oldest = max(k, last - lookback)
    for index in range(last - k, oldest - 1, -1):
        if not _is_swing_low(bars, index, k):
            continue
        with localcontext(CONTEXT):
            prominence = _prominence(bars, index, k) / scale
        if prominence < min_swing_atr:
            continue
        return index, prominence
    return None


class SweepReclaimV1:
    """A estratégia v1 de varredura e recuperação, congelada. Sem estado e pura."""

    key: str = "sweep_reclaim_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
        "pivot_k": 3,
        "min_swing_atr": Decimal("1"),
        "pivot_lookback_bars": 40,
        "sweep_atr": Decimal("0.25"),
        "rvol_window": 20,
        "rvol_min": Decimal("1.5"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "stop_buffer_atr": Decimal("0.1"),
        "risk_pct_min": Decimal("0.006"),
        "risk_atr_max": Decimal("3"),
        "target_r": Decimal("2"),
        "target2_r": Decimal("3"),
        "horizon_s": 14400,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "pivot_k": (INTEGER_PARAM, "bars each side that confirm a swing low"),
            "min_swing_atr": (DECIMAL_PARAM, "minimum pivot prominence, in ATR (inclusive)"),
            "pivot_lookback_bars": (INTEGER_PARAM, "how far back a pivot may sit, in 15m bars"),
            "sweep_atr": (DECIMAL_PARAM, "how deep the low must pierce the pivot, in ATR"),
            "rvol_window": (INTEGER_PARAM, "bars in the relative-volume median, current excluded"),
            "rvol_min": (DECIMAL_PARAM, "minimum relative volume (inclusive)"),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
            "atr_bars": (INTEGER_PARAM, "bars the ATR is recomputed from (rolling_window_v1)"),
            "stop_buffer_atr": (DECIMAL_PARAM, "stop below the swept low, in ATR"),
            "risk_pct_min": (DECIMAL_PARAM, "minimum (close - stop)/close as a fraction"),
            "risk_atr_max": (DECIMAL_PARAM, "maximum (close - stop)/ATR (inclusive)"),
            "target_r": (DECIMAL_PARAM, "target1 in nominal R of the structural risk"),
            "target2_r": (DECIMAL_PARAM, "informational target 2, in nominal R"),
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
            why = {"eligibility_reason": ctx.eligibility_reason or "unknown"}
            return Evaluation(None, EvaluationState.INELIGIBLE, "ineligible", why)

        pivot_k = param_int(params, "pivot_k")
        lookback = param_int(params, "pivot_lookback_bars")
        rvol_window = param_int(params, "rvol_window")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])
        cut = ctx.source_bar_close

        # Derivada, nunca cravada: alongar ``pivot_lookback_bars`` numa variante
        # alonga a janela junto, ou o pivô mais antigo que ela admite não teria
        # ombro esquerdo para ser confirmado.
        signal_bars = max(lookback + pivot_k + 1, rvol_window + 1)
        window = aggregate(ctx.candles_1m, self.timeframe, cut, signal_bars)
        if not window.available:
            return _unavailable(window.reason or "", window.detail)

        atr_end = align_open_time(cut, atr_timeframe)
        atr_window = aggregate(ctx.candles_1m, atr_timeframe, atr_end, atr_bars)
        if not atr_window.available:
            return _unavailable(f"atr_{atr_window.reason}", atr_window.detail)
        atr = wilder_atr(atr_window.bars, param_int(params, "atr_period"))
        atr_pct = None if atr is None else atr_percent(atr, atr_window.bars[-1].close)
        if atr is None or atr_pct is None:
            return _unavailable("atr_warmup")

        bars = window.bars
        signal = bars[-1]
        found = _latest_pivot_low(
            bars,
            k=pivot_k,
            lookback=lookback,
            scale=atr.value,
            min_swing_atr=param_decimal(params, "min_swing_atr"),
        )
        if found is None:
            return _not_triggered("no_pivot", {"lookback_bars": str(lookback)})
        pivot_index, prominence_atr = found
        pivot_bar = bars[pivot_index]
        pivot_low = pivot_bar.low
        index_back = len(bars) - 1 - pivot_index

        with localcontext(CONTEXT):
            sweep_floor = pivot_low - param_decimal(params, "sweep_atr") * atr.value
            sweep_depth_atr = (pivot_low - signal.low) / atr.value
        level = {"pivot_low": canonical_number(pivot_low)}
        if signal.low > sweep_floor:
            observed = canonical_number(sweep_depth_atr)
            low_15m = canonical_number(signal.low)
            detail = {"low_15m": low_15m, **level, "sweep_atr_observed": observed}
            return _not_triggered("no_sweep", detail)
        close = signal.close
        if close <= pivot_low:
            return _not_triggered("no_reclaim", {"close_15m": canonical_number(close), **level})

        rvol = relative_volume(bars, rvol_window)
        if rvol is None:
            return _unavailable("rvol_unavailable", {"rvol_window": str(rvol_window)})
        if rvol < param_decimal(params, "rvol_min"):
            return _not_triggered("low_rvol", {"rvol_15m": canonical_number(rvol)})

        with localcontext(CONTEXT):
            stop = signal.low - param_decimal(params, "stop_buffer_atr") * atr.value
            risk = close - stop
            risk_pct = risk / close
            toll_cap_r = _round_trip(params) / risk_pct if risk_pct > _ZERO else _ZERO
            risk_atr = risk / atr.value
        if risk_pct < param_decimal(params, "risk_pct_min"):
            # Publica o pedágio da barra recusada: é o número com que a próxima
            # versão vai discutir este piso.
            refused = {"risk_pct": canonical_number(risk_pct)}
            refused["toll_cap_r"] = canonical_number(toll_cap_r)
            return _not_triggered("risk_below_floor", refused)
        if risk_atr > param_decimal(params, "risk_atr_max"):
            return _not_triggered("risk_above_cap", {"risk_atr": canonical_number(risk_atr)})

        with localcontext(CONTEXT):
            target1 = close + param_decimal(params, "target_r") * risk
            informational = (close + param_decimal(params, "target2_r") * risk,)
        # Estruturalmente inalcançável (``stop < low <= close`` sempre), e mantida
        # de propósito: uma guarda que nunca dispara é barata, e uma geometria que
        # dispara sem ninguém ver custou a ``breakout_v1`` inteira (14/14).
        if not _ZERO < stop < close < target1:
            levels = {"stop": canonical_number(stop), "target1": canonical_number(target1)}
            levels["reference_price"] = canonical_number(close)
            return Evaluation(None, EvaluationState.REJECTED, "geometry", levels)

        envelope = SupportingFeatures(
            observation_ts=cut,
            timeframe=self.timeframe.value,
            strategy_key=self.key,
            strategy_version=self.version,
            features=(
                # a barra de referência inteira (mínima e fechamento são condição *e*
                # nível) e o pivô com idade e proeminência: depois que as velas saem
                # da retenção, um nível sem proveniência não é auditável, e "qual
                # mínima era essa?" é a pergunta que a decisão que perdeu recebe
                FeatureEvidence(name="open_15m", value=signal.open, source_ts=signal.open_time),
                FeatureEvidence(name="high_15m", value=signal.high),
                FeatureEvidence(name="low_15m", value=signal.low),
                FeatureEvidence(name="volume_15m", value=signal.volume),
                FeatureEvidence(name="close_15m", value=close, source_ts=signal.close_time),
                FeatureEvidence(name="pivot_low", value=pivot_low, source_ts=pivot_bar.open_time),
                FeatureEvidence(name="pivot_index_back", value=index_back, window=lookback),
                FeatureEvidence(name="pivot_prominence_atr", value=prominence_atr, window=pivot_k),
                FeatureEvidence(name="sweep_depth_atr", value=sweep_depth_atr),
                FeatureEvidence(name="rvol_15m", value=rvol, window=rvol_window),
                FeatureEvidence(name="risk_pct", value=risk_pct),
                FeatureEvidence(name="risk_atr", value=risk_atr),
                FeatureEvidence(name="toll_cap_r", value=toll_cap_r),
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
                f"Sweep and reclaim 15m: mínima {canonical_number(signal.low)} varreu "
                f"{_display(sweep_depth_atr)} ATR abaixo do pivô de {canonical_number(pivot_low)} "
                f"({index_back} barras atrás, proeminência {_display(prominence_atr)} ATR) e o "
                f"fechamento {canonical_number(close)} voltou acima dele, volume relativo "
                f"{_display(rvol)}x da mediana de {rvol_window} barras; stop "
                f"{canonical_number(stop)} ({_display(risk_atr)} ATR, risco "
                f"{_display(risk_pct, _PERCENT)}%), pedágio máximo {_display(toll_cap_r)} R"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


SWEEP_RECLAIM_V1: Final = SweepReclaimV1()
"""A instância registrada; estratégias não têm estado, então uma basta."""
