"""``sweep_reclaim_v1`` — brief T3.45b, EXP-0017.

A série base é construída para que **todo número esperado seja exato e escrito à
mão**. 120 barras de 15 min terminando no corte:

- barras 0–106: patamar em ``100`` com meia-amplitude ``0.45``;
- barras 107–113: o mergulho ``99.6, 99.2, 98.75, 99.2, 99.6`` em volta do fundo
  — a barra 111 é o pivô, com **mínima 98,30**;
- barras 114–118: patamar em ``100`` de novo;
- barra 119 (o sinal): abre em 100, máxima ``100.3``, **mínima 98**, fecha em
  ``100``, volume ``200`` (2× a mediana de 20 barras).

Todo passo de fechamento é ``<= 0.45`` e toda barra tem amplitude ``0.9``, então
**todo true range vale exatamente 0,9** menos o da barra de sinal, que vale
``max(100.3 − 98, 0.3, 2) = 2.3``. O ATR de Wilder(14) sobre as 97 barras da
janela é portanto ``(0.9 × 13 + 2.3) / 14 = 1`` **exato** — e é isso que faz a
geometria do §10.2 do brief cair redonda:

``referência 100 · stop 97,9 · risco 2,1 · alvo1 104,2 · alvo2 106,3``
``risk_pct 0,021 · risk_atr 2,1 · varredura 0,30 ATR · proeminência 2,15 ATR``

Run: ``uv run pytest packages/core/tests/unit/strategies/test_sweep_reclaim_v1.py -q``
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, localcontext
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.aggregate import aggregate
from hunter_core.strategies.base import EvaluationState, StrategyContext, build_context
from hunter_core.strategies.constraints import check_ranges
from hunter_core.strategies.envelope import PURPOSE_RESEARCH_ONLY, AssumedCosts
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.sweep_reclaim_v1 import (
    SWEEP_RECLAIM_V1,
    _latest_pivot_low,  # pyright: ignore[reportPrivateUsage]
)
from hunter_core.strategies.tl_pivots import PivotKind, find_pivots

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, series

pytestmark = pytest.mark.unit

PARAMS = SWEEP_RECLAIM_V1.default_parameters
TOTAL_BARS = 120
TAIL_BARS = 4
"""120 barras de 15 min = 1800 min: cobre a janela de ATR (1455) e a de sinal
(660), que é o orçamento do §7 do brief."""

CUT = ORIGIN + timedelta(minutes=15 * TOTAL_BARS)
HALF = D("0.45")
"""Meia-amplitude de toda barra que não é o sinal: ``true_range = 0.9`` enquanto o
passo de fechamento não passar de 0,45."""
VOLUME = D("100")
PLATEAU = D("100")
ATR = D("1")
PIVOT_LOW = D("98.30")

SIGNAL_BAR = BarSpec(D("100"), D("100.3"), D("98"), D("100"), D("200"))
"""A varredura: mínima 98 = ``98.30 − 0.30 ATR``, fechamento de volta em 100 (bem
acima do pivô) e volume 2× a mediana. ``true_range = 2.3``."""


def _bar(close: Decimal, *, volume: Decimal = VOLUME) -> BarSpec:
    return BarSpec(close, close + HALF, close - HALF, close, volume)


DIP = [_bar(D("99.6")), _bar(D("99.2")), _bar(D("98.75")), _bar(D("99.2")), _bar(D("99.6"))]
"""O mergulho: o fundo em 98,75 tem mínima 98,30, estritamente abaixo das três
mínimas à esquerda e menor-ou-igual às três da direita."""

TIES_DIP = [
    _bar(D("99.6")),
    _bar(D("99.2")),
    _bar(D("98.75")),
    _bar(D("98.75")),
    _bar(D("98.75")),
    _bar(D("99.2")),
    _bar(D("99.6")),
]
"""Um platô de três mínimas iguais: a regra do empate diz que **a mais velha** é o
pivô, então o platô rende um pivô e não três."""

SHALLOW_DIP = [_bar(D("99.95")), _bar(D("99.95"))]
"""Uma ondulação de mínima 99,50 contra ombros de 100,45: proeminência 0,95 —
abaixo de 1 ATR, e por isso não é pivô nenhum."""

TALL_PIVOT_DIP = [
    BarSpec(D("99.95"), D("101.5"), D("99.5"), D("99.95"), VOLUME),
    _bar(D("99.95")),
]
"""A mesma ondulação, mas a barra do próprio candidato tem uma máxima de 101,5:
com ela **dentro** dos ombros a proeminência seria 2,0; a regra exclui a barra e
ela continua valendo 0,95."""

WICK = BarSpec(D("100"), D("101.5"), D("99.55"), D("100"), VOLUME)
SHOULDER_DIP = [WICK, BarSpec(D("99.95"), D("100.4"), D("99.5"), D("99.95"), VOLUME), WICK]
"""A mesma máxima de 101,5, agora nos **vizinhos**: aí ela conta, a proeminência
passa de 1 ATR e o pivô existe. O par com ``TALL_PIVOT_DIP`` é o teste da regra."""


def build_series(
    *,
    tail: int = TAIL_BARS,
    signal: BarSpec | None = None,
    dip: list[BarSpec] | None = None,
    bars: int = TOTAL_BARS,
    plateau_volume: Decimal | None = None,
) -> list[NormalizedCandle]:
    """A série base, ou uma variante com um pedaço trocado."""
    dip = DIP if dip is None else dip
    head = bars - 1 - len(dip) - tail - 1
    specs = [_bar(PLATEAU)] * head + list(dip) + [_bar(PLATEAU)] * (tail + 1)
    if plateau_volume is not None:
        specs = [BarSpec(s.open, s.high, s.low, s.close, plateau_volume) for s in specs]
    specs.append(signal or SIGNAL_BAR)
    assert len(specs) == bars
    return series(specs, timeframe=Timeframe.M15)


K_CONFIRM_CUT = ORIGIN + timedelta(minutes=15 * (TOTAL_BARS - 2))
"""Duas barras antes do corte normal: com ``tail = 0`` o fundo cai em ``t-2`` e um
pivô em ``t-2`` **não existe ainda** para quem decide em ``t``."""


def build_k_confirmation_series() -> list[NormalizedCandle]:
    """A mesma série com ``tail = 0``: o fundo fica em ``t-4`` no corte cheio e em
    ``t-2`` no corte de ``K_CONFIRM_CUT``."""
    return build_series(tail=0)


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def variant(**overrides: object) -> dict[str, Any]:
    return {**PARAMS, **overrides}


def features(decision: Any) -> dict[str, Any]:
    return {feature.name: feature.value for feature in decision.supporting_features.features}


# --------------------------------------------------------------------------- 1. dispara


def test_it_signals_on_the_constructed_sweep_and_reclaim() -> None:
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == D("100")
    assert decision.stop == D("97.9")  # 98 − 0.1 × 1
    assert decision.target1 == D("104.2")  # 100 + 2 × 2.1
    assert decision.targets_informational == (D("106.3"),)  # 100 + 3 × 2.1
    assert decision.horizon_s == 14400
    assert decision.confidence == D("0.5")
    assert decision.supporting_features.purpose == PURPOSE_RESEARCH_ONLY


def test_the_reason_names_the_pivot_the_sweep_and_the_toll() -> None:
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.reason == (
        "Sweep and reclaim 15m: mínima 98 varreu 0.30 ATR abaixo do pivô de 98.3 "
        "(8 barras atrás, proeminência 2.15 ATR) e o fechamento 100 voltou acima dele, "
        "volume relativo 2.00x da mediana de 20 barras; stop 97.9 (2.10 ATR, "
        "risco 2.10%), pedágio máximo 0.10 R"
    )


def test_there_is_no_invalidation_on_purpose() -> None:
    """Braço ``INV-B`` da KB-0006: a mínima varrida já é o stop, e uma regra que
    sai acima dele é um segundo stop sem tese. C8 do portão pontua isto como
    ``fail`` e a divergência está declarada no EXP-0017 — não é para consertar."""
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.invalidations == ()


def test_the_envelope_carries_the_pivot_with_its_age_and_provenance() -> None:
    """§9 do brief: ``pivot_low`` sozinho não é auditável depois que as velas saem
    da retenção — "qual mínima era essa?" precisa de idade e proeminência."""
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    values = features(decision)
    assert values["pivot_low"] == PIVOT_LOW
    assert values["pivot_index_back"] == 8
    assert values["pivot_prominence_atr"] == D("2.15")  # min(100.45, 100.45) − 98.30
    assert values["sweep_depth_atr"] == D("0.3")
    assert values["rvol_15m"] == D("2")
    assert values["risk_pct"] == D("0.021")
    assert values["risk_atr"] == D("2.1")
    assert (values["open_15m"], values["high_15m"]) == (D("100"), D("100.3"))
    assert (values["low_15m"], values["close_15m"]) == (D("98"), D("100"))
    assert values["volume_15m"] == D("200")

    pivot = next(f for f in decision.supporting_features.features if f.name == "pivot_low")
    assert pivot.source_ts == ORIGIN + timedelta(minutes=15 * 111)
    assert decision.supporting_features.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )


def test_the_atr_reading_is_reproducible_from_the_envelope() -> None:
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    atr = decision.supporting_features.atr
    assert atr is not None
    assert atr.value == ATR
    assert atr.percent == D("0.01")
    assert atr.period == 14
    assert atr.bars_used == 97
    assert atr.timeframe == "15m"
    assert atr.window_end == CUT
    assert atr.window_start == CUT - timedelta(minutes=15 * 97)
    assert atr.seed == D("0.9")  # os 14 primeiros true ranges valem 0,9


# --------------------------------------------------------------- 2. a geometria, à mão


def test_the_geometry_is_the_one_written_by_hand_in_the_brief() -> None:
    """§10.2: ``ATR = 1``, ``close = 100``, ``low = 98``, ``stop_buffer_atr = 0.1``.
    Igualdade em ``Decimal``, nunca ``pytest.approx``."""
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    low, atr = D("98"), ATR
    stop = low - D("0.1") * atr
    risk = decision.reference_price - stop
    assert (stop, risk) == (D("97.9"), D("2.1"))
    assert decision.stop == stop
    assert decision.target1 == decision.reference_price + D("2") * risk == D("104.2")
    assert decision.targets_informational == (decision.reference_price + D("3") * risk,)
    values = features(decision)
    assert values["risk_atr"] == risk / atr == D("2.1")
    assert values["risk_pct"] == risk / decision.reference_price == D("0.021")


def test_the_published_toll_is_the_identity_of_kb_0076() -> None:
    """``custo_R = ida-e-volta / risco%``. Os 20 bps saem dos parâmetros de custo
    congelados (2 + 2×5 + 2×4), não de um ``0,0020`` cravado no caminho quente."""
    decision = SWEEP_RECLAIM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    round_trip = (
        PARAMS["assumed_spread_bps"] + 2 * PARAMS["slippage_bps"] + 2 * PARAMS["fee_bps"]
    ) / D("10000")
    assert round_trip == D("0.0020")
    with localcontext(CONTEXT):
        assert features(decision)["toll_cap_r"] == round_trip / D("0.021")


# --------------------------------------------------------------- 3. as regras do pivô


def test_a_plateau_of_equal_lows_yields_one_pivot_and_it_is_the_oldest() -> None:
    """Regra 3 da T3.34: o empate vai para a barra mais velha. As três mínimas
    iguais estão nas barras 109, 110 e 111; a escolhida tem de ser a 109."""
    decision = SWEEP_RECLAIM_V1.evaluate(context(candles=build_series(dip=TIES_DIP)), PARAMS)

    assert decision is not None
    values = features(decision)
    assert values["pivot_low"] == PIVOT_LOW
    assert values["pivot_index_back"] == 10  # 119 − 109, e não 8 nem 9
    assert values["pivot_prominence_atr"] == D("1.35")  # min(100.45, 99.65) − 98.30


def test_a_wiggle_shallower_than_one_atr_is_not_a_pivot() -> None:
    """Proeminência 0,95 contra ``min_swing_atr × ATR = 1``: a ondulação existe e
    **não** é estrutura."""
    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=build_series(dip=SHALLOW_DIP)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "no_pivot"
    assert evaluation.detail == {"lookback_bars": "40"}


def test_the_shoulders_exclude_the_pivot_bars_own_range() -> None:
    """Regra 2 da T3.34, provada por par: a **mesma** máxima de 101,5 na barra do
    candidato não conta (proeminência 0,95, não é pivô) e nos vizinhos conta
    (proeminência ~1,84 ATR, é pivô). Incluir a própria barra fazia a proeminência
    valer ~1 ATR por construção e o filtro não filtrava nada."""
    own_range = SWEEP_RECLAIM_V1.explain(context(candles=build_series(dip=TALL_PIVOT_DIP)), PARAMS)
    on_shoulders = SWEEP_RECLAIM_V1.evaluate(
        context(candles=build_series(dip=SHOULDER_DIP)), PARAMS
    )

    assert own_range.state is EvaluationState.NOT_TRIGGERED
    assert own_range.reason == "no_pivot"
    assert D("101.5") - D("99.5") > D("1") > D("100.45") - D("99.5")  # 2,0 contra 0,95
    assert on_shoulders is not None
    assert features(on_shoulders)["pivot_low"] == D("99.5")


def test_the_detector_agrees_digit_for_digit_with_the_tl_pivots_port() -> None:
    """O módulo **não importa** ``tl_pivots`` (§2 do brief: juntar os fechos faria
    um conserto numa reta de tendência re-congelar esta coorte). A regra é a mesma
    mesmo assim, e é este teste — fora de qualquer fecho — que mantém isso
    verdadeiro em vez da disciplina. Divergência declarada: aqui a escala é **uma**
    leitura de ATR por decisão, lá é o ATR de cada barra."""
    for dip in (DIP, TIES_DIP, SHALLOW_DIP, TALL_PIVOT_DIP, SHOULDER_DIP):
        ctx = context(candles=build_series(dip=dip))
        window = aggregate(ctx.candles_1m, Timeframe.M15, CUT, 44)
        assert window.available
        bars = window.bars
        scale = D("1.1")  # uma escala qualquer, a mesma dos dois lados
        mine = _latest_pivot_low(bars, k=3, lookback=40, scale=scale, min_swing_atr=D("1"))
        theirs = [
            pivot
            for pivot in find_pivots(bars, (scale,) * len(bars), k=3, min_swing_atr=D("1"))
            if pivot.kind is PivotKind.LOW and pivot.index >= len(bars) - 1 - 40
        ]
        expected = (theirs[-1].index, theirs[-1].prominence_atr) if theirs else None
        assert mine == expected, dip


# ------------------------------------------- 4. a não-antecipação desta versão: o k


def test_a_swing_low_two_bars_old_does_not_exist_yet() -> None:
    """O teste central desta versão. O fundo cai em ``t-2`` no corte curto: ele
    *seria* um pivô se as duas barras seguintes existissem, e por isso **não pode**
    ser usado. Duas barras depois ele vira ``t-4``, fica confirmado, e aí sim é o
    pivô da decisão. Mesmas velas nos dois cortes — só o corte muda."""
    candles = build_k_confirmation_series()

    too_early = SWEEP_RECLAIM_V1.explain(context(candles=candles, cut=K_CONFIRM_CUT), PARAMS)
    confirmed = SWEEP_RECLAIM_V1.evaluate(context(candles=candles), PARAMS)

    assert too_early.state is EvaluationState.NOT_TRIGGERED
    assert too_early.reason == "no_pivot"
    assert confirmed is not None
    assert features(confirmed)["pivot_index_back"] == 4
    assert features(confirmed)["pivot_low"] == PIVOT_LOW
    assert confirmed.stop == D("97.9")


# --------------------------------------------------------------------------- 5. não dispara


def test_a_low_that_does_not_pierce_deep_enough_is_no_sweep() -> None:
    shallow = BarSpec(D("100"), D("100.5"), D("98.2"), D("100"), D("200"))
    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=build_series(signal=shallow)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "no_sweep"
    assert evaluation.detail == {
        "low_15m": "98.2",
        "pivot_low": "98.3",
        "sweep_atr_observed": "0.1",  # 0,1 ATR contra os 0,25 exigidos
    }


def test_a_close_exactly_at_the_pivot_is_not_a_reclaim() -> None:
    """A comparação é **estrita**: fechar em cima da mínima varrida é ficar
    dentro dela, não voltar acima."""
    at_the_level = BarSpec(D("100"), D("100.3"), D("98"), PIVOT_LOW, D("200"))
    evaluation = SWEEP_RECLAIM_V1.explain(
        context(candles=build_series(signal=at_the_level)), PARAMS
    )

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "no_reclaim"
    assert evaluation.detail == {"close_15m": "98.3", "pivot_low": "98.3"}


def test_a_reclaim_without_volume_is_not_a_signal() -> None:
    quiet = BarSpec(D("100"), D("100.3"), D("98"), D("100"), VOLUME)
    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=build_series(signal=quiet)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "low_rvol"
    assert evaluation.detail == {"rvol_15m": "1"}


def test_a_stop_too_close_to_pay_the_toll_is_refused_with_its_toll() -> None:
    """A porta que mais corta na pré-checagem (177 -> 58). O motivo publica o
    pedágio da barra recusada, que é o número com que a próxima versão discute."""
    evaluation = SWEEP_RECLAIM_V1.explain(context(), variant(risk_pct_min=D("0.05")))

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "risk_below_floor"
    assert evaluation.detail["risk_pct"] == "0.021"
    with localcontext(CONTEXT):
        assert evaluation.detail["toll_cap_r"] == str(D("0.0020") / D("0.021"))


def test_the_frozen_floor_refuses_a_shallow_reclaim_on_the_real_geometry() -> None:
    """O mesmo ramo sem mexer em parâmetro: uma barra que varre 98,05 e fecha em
    98,40 tem ``risco% ~ 0,45 %``, abaixo do piso congelado de 0,6 %."""
    thin = BarSpec(D("98.4"), D("98.4"), D("98.05"), D("98.4"), D("200"))
    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=build_series(signal=thin)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "risk_below_floor"
    assert D(evaluation.detail["risk_pct"]) < D("0.006")


def test_a_stop_wider_than_the_cap_is_refused() -> None:
    """Guarda, não condição: a pré-checagem mediu **1** evento recusado por ela em
    31 dias × 4 mercados."""
    wide = BarSpec(D("100"), D("100"), D("94.9"), D("100"), D("200"))
    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=build_series(signal=wide)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "risk_above_cap"
    assert evaluation.detail == {"risk_atr": "4.35"}  # ATR 1,2; risco 5,22


def test_an_ineligible_market_is_not_a_false_condition() -> None:
    evaluation = SWEEP_RECLAIM_V1.explain(
        context(eligible=False, eligibility_reason="not_monitored"), PARAMS
    )

    assert evaluation.state is EvaluationState.INELIGIBLE
    assert evaluation.reason == "ineligible"
    assert evaluation.detail == {"eligibility_reason": "not_monitored"}


# --------------------------------------------------------------------------- 6. indisponível


def test_a_short_history_is_warmup_not_a_false_condition() -> None:
    evaluation = SWEEP_RECLAIM_V1.explain(
        context(candles=build_series(bars=40), cut=ORIGIN + timedelta(minutes=15 * 40)), PARAMS
    )

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "warmup"


def test_one_missing_minute_inside_the_signal_window_is_a_gap() -> None:
    candles = build_series()
    missing = candles[-30].open_time
    holed = [candle for candle in candles if candle.open_time != missing]

    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=holed), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "gap"
    assert evaluation.detail["missing_minute"] == missing.isoformat().replace("+00:00", "Z")


def test_a_hole_only_in_the_atr_window_is_reported_as_the_atr_gap() -> None:
    """A janela de ATR (1455 min) começa antes da de sinal (660 min): um buraco
    naquele trecho deixa o sinal inteiro e mata a escala."""
    candles = build_series()
    missing = candles[30 * 15].open_time
    holed = [candle for candle in candles if candle.open_time != missing]

    evaluation = SWEEP_RECLAIM_V1.explain(context(candles=holed), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "atr_gap"
    assert evaluation.detail["missing_minute"] == missing.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("atr_bars", [200, 15], ids=["window_too_long", "indicator_warmup"])
def test_the_atr_reports_its_own_warmup(atr_bars: int) -> None:
    evaluation = SWEEP_RECLAIM_V1.explain(context(), variant(atr_bars=atr_bars))

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "atr_warmup"


def test_a_zero_volume_baseline_is_unavailable_not_a_low_rvol() -> None:
    """Um mercado que não negociou não tem linha de base, e isso não é condição
    falsa: o worker não pode re-armar o slot nessa barra."""
    evaluation = SWEEP_RECLAIM_V1.explain(
        context(candles=build_series(plateau_volume=D("0"))), PARAMS
    )

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "rvol_unavailable"
    assert evaluation.detail == {"rvol_window": "20"}


# --------------------------------------------------------------------------- 7. rejeitado


def test_a_stop_below_zero_is_rejected_by_the_geometry_guard() -> None:
    """Estruturalmente inalcançável com os defaults (``stop < low <= close``
    sempre), e mantida assim mesmo: a guarda custa nada e uma geometria que
    dispara sem ninguém ver matou a ``breakout_v1`` (14/14). Precisa de **dois**
    parâmetros absurdos porque o teto de risco morde antes."""
    evaluation = SWEEP_RECLAIM_V1.explain(
        context(), variant(stop_buffer_atr=D("200"), risk_atr_max=D("1000"))
    )

    assert evaluation.state is EvaluationState.REJECTED
    assert evaluation.reason == "geometry"
    assert evaluation.detail["stop"] == "-102"
    assert evaluation.detail["reference_price"] == "100"


# --------------------------------------------------------------- 8. pureza e reprodução


def test_evaluate_is_pure_two_calls_agree() -> None:
    ctx = context()

    assert SWEEP_RECLAIM_V1.evaluate(ctx, PARAMS) == SWEEP_RECLAIM_V1.evaluate(ctx, PARAMS)


def test_nothing_in_the_module_reads_a_clock_or_does_io() -> None:
    """``Strategy.evaluate`` é função pura (ARCHITECTURE §6): o contexto carrega
    tudo. Uma leitura de relógio faria a mesma barra decidir duas coisas."""
    from pathlib import Path

    import hunter_core.strategies.sweep_reclaim_v1 as module

    source = Path(module.__file__ or "").read_text(encoding="utf-8")
    for forbidden in ("now(", "utcnow", "import time", "import random", "open("):
        assert forbidden not in source, forbidden


def test_bootstrap_equals_continuous_execution() -> None:
    """Uma leitura longa contra um contexto crescido barra a barra: a mesma
    decisão no mesmo fechamento de referência, e **só** nele."""
    candles = build_series()

    bootstrap = SWEEP_RECLAIM_V1.evaluate(context(candles=candles), PARAMS)

    grown: list[NormalizedCandle] = []
    decisions: list[Any] = []
    for index in range(TOTAL_BARS):
        grown.extend(candles[index * 15 : (index + 1) * 15])
        cut = ORIGIN + timedelta(minutes=15 * (index + 1))
        decisions.append(SWEEP_RECLAIM_V1.evaluate(context(candles=list(grown), cut=cut), PARAMS))

    assert bootstrap is not None
    assert decisions[-1] == bootstrap
    assert [decision for decision in decisions[:-1] if decision is not None] == []


def test_the_decision_does_not_depend_on_how_much_history_is_kept() -> None:
    """97 barras de 15 min é a janela declarada; um contexto com 120 decide o
    mesmo, e a janela de ATR é a que começa mais cedo."""
    candles = build_series()
    atr_start = CUT - timedelta(minutes=15 * 97)
    trimmed = [candle for candle in candles if candle.open_time >= atr_start]

    full = SWEEP_RECLAIM_V1.evaluate(context(candles=candles), PARAMS)
    bootstrap = SWEEP_RECLAIM_V1.evaluate(context(candles=trimmed), PARAMS)

    assert full is not None
    assert len(trimmed) < len(candles)
    assert bootstrap == full


# --------------------------------------------------------------- 9. isolamento do digest


def test_the_live_versions_digests_did_not_move() -> None:
    """§2 do brief: acrescentar este módulo não pode re-congelar nenhuma versão já
    ativada na VPS — inclusive a linha ``paper``."""
    from hunter_strategy_worker.code_ref import version_code_ref

    assert version_code_ref("momentum_v1") == (
        "hunter_core.strategies.momentum_v1@sha256:"
        "ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
    )
    assert version_code_ref("volume_anomaly_v1") == (
        "hunter_core.strategies.volume_anomaly_v1@sha256:"
        "9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"
    )
    assert version_code_ref("breakout_v1") == (
        "hunter_core.strategies.breakout_v1@sha256:"
        "4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1"
    )
    assert version_code_ref("mean_reversion_v1") == (
        "hunter_core.strategies.mean_reversion_v1@sha256:"
        "a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f"
    )
    assert version_code_ref("session_orb_v1") == (
        "hunter_core.strategies.session_orb_v1@sha256:"
        "a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba"
    )


def test_this_version_closes_over_the_siblings_it_imports_and_no_others() -> None:
    """A sexta asserção do §2, feita pela **estrutura** e não pelo dígito: a
    ``trendline_breakout_v1`` está em obra na T3.34b em paralelo e o digest dela é
    alvo móvel. O que este teste protege é o que importa — nenhum ``tl_*`` entra
    neste fecho, e este módulo não entra no fecho de ninguém."""
    from hunter_strategy_worker.code_ref import module_closure

    closure = module_closure("sweep_reclaim_v1")

    assert closure == (
        "aggregate",
        "base",
        "canonical",
        "envelope",
        "indicators",
        "numeric",
        "schema",
        "sweep_reclaim_v1",
    )
    assert not [name for name in closure if name.startswith("tl_")]
    for module in ("momentum_v1", "volume_anomaly_v1", "breakout_v1", "mean_reversion_v1"):
        assert "sweep_reclaim_v1" not in module_closure(module)
    assert "sweep_reclaim_v1" not in module_closure("session_orb_v1")
    assert "sweep_reclaim_v1" not in module_closure("trendline_breakout_v1")


# --------------------------------------------------------------------------- 10. constraints


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"pivot_k": "0"}, "pivot_k"),
        ({"sweep_atr": "-0.1"}, "sweep_atr"),
        ({"stop_buffer_atr": "0"}, "stop_buffer_atr"),
        ({"risk_pct_min": "0"}, "risk_pct_min"),
        ({"risk_pct_min": "0.5"}, "risk_pct_min"),
        ({"target_r": "4"}, "target_r"),
        ({"base_confidence": "42"}, "base_confidence"),
    ],
)
def test_check_ranges_refuses_the_probes(override: dict[str, str], fragment: str) -> None:
    parent = {name: str(value) for name, value in PARAMS.items()}

    problems = check_ranges(SWEEP_RECLAIM_V1, parent, {**parent, **override})

    assert any(fragment in problem for problem in problems), problems


def test_the_frozen_contract_passes_its_own_check() -> None:
    parent = {name: str(value) for name, value in PARAMS.items()}

    assert check_ranges(SWEEP_RECLAIM_V1, parent, parent) == []


# --------------------------------------------------------------- 11. o ponto de equilíbrio


def test_the_break_even_arithmetic_that_chose_a_two_r_target() -> None:
    """§5 do brief, em ``Decimal``: no piso de custo congelado (``risco% = 0,6 %``,
    ``a = 6 bps/lado`` dentro dos preços, ``f = 4 bps/lado`` fora), o alvo de 2 R
    rende ``+1,5133 R`` e o stop ``−1,2112 R``, o que pede **44,46 %** de acerto.
    A mesma linha aparece dígito a dígito na tabela da ``session_orb_v1``
    (notes-T3.33 §4), então isto reproduz aritmética publicada, não inventa."""
    with localcontext(CONTEXT):
        risk = D("0.006")
        inside = (PARAMS["assumed_spread_bps"] / 2 + PARAMS["slippage_bps"]) / D("10000")
        outside = PARAMS["fee_bps"] / D("10000")
        assert (inside, outside) == (D("0.0006"), D("0.0004"))

        entry = D(1) + inside
        unit = risk + inside  # a distância real da entrada até o stop
        at_target = (D(1) + PARAMS["target_r"] * risk) * (D(1) - inside)
        at_stop = (D(1) - risk) * (D(1) - inside)
        win = (at_target - entry - outside * (entry + at_target)) / unit
        loss = (at_stop - entry - outside * (entry + at_stop)) / unit
        break_even = -loss / (win - loss)
        toll = (
            (PARAMS["assumed_spread_bps"] + 2 * PARAMS["slippage_bps"] + 2 * PARAMS["fee_bps"])
            / D("10000")
            / risk
        )

    places = D("0.0001")
    assert win.quantize(places) == D("1.5133")
    assert loss.quantize(places) == D("-1.2112")
    assert break_even.quantize(places) == D("0.4446")
    assert toll.quantize(places) == D("0.3333")


# --------------------------------------------------------------- 12. orçamento de janela


def test_every_window_fits_the_shadow_context() -> None:
    """§7 do brief. ``SHADOW_CONTEXT_MINUTES`` é botão do worker compartilhado por
    todas as versões: subi-lo encarece cada barra de todo mundo."""
    from hunter_strategy_worker.config import ShadowConfig

    signal_bars = max(
        int(PARAMS["pivot_lookback_bars"]) + int(PARAMS["pivot_k"]) + 1,
        int(PARAMS["rvol_window"]) + 1,
    )
    atr_reach = int(PARAMS["atr_bars"]) * 15

    assert signal_bars == 44
    assert (signal_bars * 15, atr_reach) == (660, 1455)
    assert max(signal_bars * 15, atr_reach) <= ShadowConfig().context_minutes == 1560


def test_the_signal_window_is_derived_from_the_parameters() -> None:
    """Nunca 44 cravado: uma variante que alargue o alcance do pivô tem de alargar
    a janela junto, ou o pivô mais antigo que ela admite não teria ombro esquerdo."""
    longer = variant(pivot_lookback_bars=80)

    evaluation = SWEEP_RECLAIM_V1.explain(context(), longer)

    assert evaluation.state is EvaluationState.TRIGGERED  # 84 barras cabem nas 120
    assert SWEEP_RECLAIM_V1.explain(context(), variant(pivot_lookback_bars=200)).reason == "warmup"


# --------------------------------------------------------------- identidade congelada


def test_default_parameters_are_the_frozen_contract() -> None:
    assert dict(PARAMS) == {
        "pivot_k": 3,
        "min_swing_atr": D("1"),
        "pivot_lookback_bars": 40,
        "sweep_atr": D("0.25"),
        "rvol_window": 20,
        "rvol_min": D("1.5"),
        "atr_period": 14,
        "atr_timeframe": "15m",
        "atr_bars": 97,
        "stop_buffer_atr": D("0.1"),
        "risk_pct_min": D("0.006"),
        "risk_atr_max": D("3"),
        "target_r": D("2"),
        "target2_r": D("3"),
        "horizon_s": 14400,
        "base_confidence": D("0.5"),
        "assumed_spread_bps": D("2"),
        "slippage_bps": D("5"),
        "fee_bps": D("4"),
        "max_entry_delay_s": 120,
    }
    assert len(PARAMS) == 20
    assert (SWEEP_RECLAIM_V1.key, SWEEP_RECLAIM_V1.version) == ("sweep_reclaim_v1", "v1")
    assert SWEEP_RECLAIM_V1.timeframe is Timeframe.M15
    assert "atr_pct_min" not in PARAMS and "atr_pct_max" not in PARAMS


def test_the_params_hash_is_pinned() -> None:
    """Identidade dourada deste conjunto congelado: se ela mudar, mudou o
    experimento — e isso é versão nova e linha nova, nunca uma edição."""
    from hunter_core.strategies.canonical import params_hash

    assert params_hash(PARAMS) == "ba2b91be91f20db40508e5c6295aa3a7a8dd3686af9edabcc21400589f658f3f"


def test_the_jsonb_round_trip_keeps_the_hash_and_the_decision() -> None:
    """typed -> JSONB -> typed tem de dar o mesmo ``params_hash`` **e** a mesma
    decisão; senão a versão relida do Postgres é outro experimento."""
    import json

    from hunter_core.strategies.canonical import canonical_json, params_hash

    wire = json.loads(canonical_json(PARAMS))

    assert params_hash(wire) == params_hash(PARAMS)
    ctx = context()
    assert SWEEP_RECLAIM_V1.evaluate(ctx, wire) == SWEEP_RECLAIM_V1.evaluate(ctx, PARAMS)
