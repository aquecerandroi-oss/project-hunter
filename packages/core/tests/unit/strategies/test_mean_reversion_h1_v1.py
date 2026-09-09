"""``mean_reversion_h1_v1`` — brief T3.54, EXP-0021.

A série base é a da mãe **escalada por 4 no tempo**, e é isso que faz cada número
esperado continuar exato e escrito à mão. Cem barras de 1 h terminando no corte:

- barras 0–79: rampa de fechamentos ``20, 21, …, 99`` (subida de 1 por barra);
- barras 80–98: patamar em ``100``;
- barra 99 (o sinal): fecha em ``99``, máxima ``100.75``, mínima ``96.25``.

Toda barra tem ``half_range = 2.25`` e todo passo de fechamento é ``|Δ| ≤ 2.25``,
então **todo true range vale exatamente 4,5** e o ATR de Wilder(14) sobre as 97
barras da janela é ``4.5`` sem arredondamento.

O corte cai numa fronteira de 4 h (100 h de uma origem alinhada), então a janela
de tendência são as 21 barras de 4 h que terminam nele — e os fechamentos de 4 h
são os das horas ``19, 23, …, 99``. Daí saem, exatos:

``referência 99 · stop 94,5 · alvo1 105,75 · alvo2 informativo 110,25``
``z(1h) = −4,358898943540673552236981984 · SMA(4h) = 75,2 · fechamento(4h) = 99``

``SMA(4h) = 75,2`` é o **mesmo** número que a mãe obtém para ``sma_1h``: as duas
séries são a mesma aritmética em grades diferentes, o que é exatamente a
propriedade que este módulo existe para testar.

Run: ``uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_h1_v1.py -q``
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import Decision, EvaluationState, StrategyContext, build_context
from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.constraints import check_ranges
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.mean_reversion_h1_v1 import MEAN_REVERSION_H1_V1
from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1
from hunter_core.strategies.numeric import CONTEXT

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, explode, minute

pytestmark = pytest.mark.unit

PARAMS = MEAN_REVERSION_H1_V1.default_parameters
HOUR = timedelta(hours=1)
RAMP_BARS = 80
PLATEAU_BARS = 19
TOTAL_BARS = RAMP_BARS + PLATEAU_BARS + 1
"""100 barras de 1 h = 6000 min: cobre a janela de ATR (5820) e a de tendência
(5040 a partir do corte alinhado), que é o pior caso desta grade."""

CUT = ORIGIN + timedelta(hours=TOTAL_BARS)
"""``ORIGIN`` é meia-noite UTC, logo múltiplo de 4 h desde a época; 100 h também
é múltiplo de 4, então o corte é fronteira de 4 h e ``trend_end == CUT``."""

HALF = D("2.25")
VOLUME = D("100")
PLATEAU = D("100")

SIGNAL_BAR = BarSpec(D("99"), D("100.75"), D("96.25"), D("99"), VOLUME)
"""O recuo: fecha em 99 (0,95 abaixo da média de 99,95), meio da barra em 98,5 —
fecha **acima** do próprio meio — e ``true_range = max(4.5, 0.75, 3.75) = 4.5``."""

ZSCORE_1H = D("-4.358898943540673552236981984")
"""``(99 − 99.95) / sqrt(0.0475)`` sob ``CONTEXT`` (28 dígitos)."""

ATR = D("4.5")
SMA_4H = D("75.2")


def _bar(close: Decimal, *, half: Decimal = HALF, volume: Decimal = VOLUME) -> BarSpec:
    return BarSpec(close, close + half, close - half, close, volume)


def hour_series(specs: list[BarSpec], *, origin: datetime = ORIGIN) -> list[NormalizedCandle]:
    """Velas de 1 min para barras de 1 h consecutivas.

    ``conftest.series`` só conhece 5 m e 15 m — os timeframes das versões que
    existiam antes desta. Explodir 60 minutos por barra é a mesma construção,
    e o agregado reproduz ``spec`` exatamente.
    """
    candles: list[NormalizedCandle] = []
    for index, spec in enumerate(specs):
        candles.extend(explode(spec, origin + timedelta(hours=index), 60))
    return candles


def _ramp(start: Decimal, step: Decimal, *, half: Decimal = HALF) -> list[BarSpec]:
    return [_bar(start + step * D(index), half=half) for index in range(RAMP_BARS)]


def build_series(
    *,
    signal: BarSpec | None = None,
    ramp: list[BarSpec] | None = None,
    plateau: BarSpec | None = None,
    half: Decimal = HALF,
    bars: int = TOTAL_BARS,
) -> list[NormalizedCandle]:
    """A série base, ou uma variante com um pedaço trocado."""
    specs = [
        *(ramp if ramp is not None else _ramp(D("20"), D("1"), half=half)),
        *[plateau or _bar(PLATEAU, half=half)] * PLATEAU_BARS,
        signal or SIGNAL_BAR,
    ]
    return hour_series(specs[:bars])


FORMING_4H_BARS = TOTAL_BARS + 2
FORMING_4H_CUT = ORIGIN + timedelta(hours=FORMING_4H_BARS)
"""Corte duas horas dentro de uma barra de 4 h: as barras 100 e 101 caem na barra
de 4 h **em formação**, que a porta de tendência tem de ignorar inteira."""


def forming_4h_series(*, forming_close: Decimal = PLATEAU) -> list[NormalizedCandle]:
    """102 barras: a rampa, 20 de patamar, a barra 100 e o recuo."""
    return hour_series(
        [
            *_ramp(D("20"), D("1")),
            *[_bar(PLATEAU)] * (PLATEAU_BARS + 1),
            _bar(forming_close),
            SIGNAL_BAR,
        ]
    )


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def decision_of(candles: list[NormalizedCandle], cut: object = CUT) -> Decision | None:
    return MEAN_REVERSION_H1_V1.evaluate(context(candles=candles, cut=cut), PARAMS)


def features(decision: Any) -> dict[str, Any]:
    return {feature.name: feature.value for feature in decision.supporting_features.features}


# --------------------------------------------------------------------------- 1. dispara


def test_it_signals_on_the_constructed_pullback() -> None:
    decision = MEAN_REVERSION_H1_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == D("99")
    assert decision.stop == D("94.5")  # 99 − 1.0 × 4.5
    assert decision.target1 == D("105.75")  # 99 + 1.5 × 4.5
    assert decision.targets_informational == (D("110.25"),)  # 99 + 2.5 × 4.5
    assert decision.horizon_s == 57600
    assert decision.confidence == D("0.5")


def test_there_is_no_invalidation_on_purpose() -> None:
    """Braço ``INV-B`` da KB-0006, herdado da mãe: stop, alvo e horizonte são a
    política de saída inteira."""
    decision = MEAN_REVERSION_H1_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.invalidations == ()


def test_the_envelope_carries_the_numbers_of_the_1h_grid() -> None:
    decision = MEAN_REVERSION_H1_V1.evaluate(context(), PARAMS)

    assert decision is not None
    values = features(decision)
    assert values["open_1h"] == D("99")
    assert values["high_1h"] == D("100.75")
    assert values["low_1h"] == D("96.25")
    assert values["close_1h"] == D("99")
    assert values["sma_1h"] == D("99.95")
    assert values["zscore_1h"] == ZSCORE_1H
    assert values["bar_mid_1h"] == D("98.5")
    assert values["close_4h"] == D("99")
    assert values["sma_4h"] == SMA_4H
    with localcontext(CONTEXT):
        assert values["atr_pct_1h"] == ATR / D("99")
    assert set(values) == {
        "open_1h",
        "high_1h",
        "low_1h",
        "volume_1h",
        "close_1h",
        "sma_1h",
        "sd_1h",
        "zscore_1h",
        "bar_mid_1h",
        "close_4h",
        "sma_4h",
        "atr_pct_1h",
    }


def test_the_atr_evidence_names_the_1h_window_it_was_computed_on() -> None:
    decision = MEAN_REVERSION_H1_V1.evaluate(context(), PARAMS)

    assert decision is not None
    atr = decision.supporting_features.atr
    assert atr is not None
    assert atr.timeframe == "1h"
    assert atr.period == 14
    assert atr.value == ATR
    assert atr.seed == ATR
    assert atr.bars_used == 97
    assert atr.window_start == ORIGIN + timedelta(hours=TOTAL_BARS - 97)
    assert atr.window_end == CUT
    assert decision.supporting_features.timeframe == "1h"
    assert decision.supporting_features.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )


# --------------------------------------------------------------------------- 2. não dispara


def test_a_close_below_the_4h_sma_is_refused_before_the_zscore() -> None:
    """Rampa **descendente**: o fechamento de 4 h fica abaixo da SMA de 20 barras
    e o motivo é o da porta de tendência, não o do esticamento."""
    falling = MEAN_REVERSION_H1_V1.explain(
        context(candles=build_series(ramp=_ramp(D("180"), D("-1")))), PARAMS
    )

    assert falling.state is EvaluationState.NOT_TRIGGERED
    assert falling.reason == "no_uptrend_4h"


def test_a_close_that_is_not_stretched_is_refused() -> None:
    """Sinal fechando **acima** do patamar: o z-score fica positivo e a versão
    recusa por esticamento, não por geometria."""
    shallow = MEAN_REVERSION_H1_V1.explain(
        context(
            candles=build_series(
                signal=BarSpec(D("101"), D("103.25"), D("98.75"), D("101"), VOLUME)
            )
        ),
        PARAMS,
    )

    assert shallow.state is EvaluationState.NOT_TRIGGERED
    assert shallow.reason == "not_stretched"


def test_a_window_without_dispersion_is_unavailable_not_a_false_condition() -> None:
    """Vinte fechamentos idênticos não têm desvio: um z-score não existe ali, e a
    resposta honesta é indisponibilidade — nunca "a condição foi falsa"."""
    flat_window = MEAN_REVERSION_H1_V1.explain(
        context(candles=build_series(signal=_bar(PLATEAU))), PARAMS
    )

    assert flat_window.state is EvaluationState.UNAVAILABLE
    assert flat_window.reason == "zscore_degenerate"


def test_a_close_below_the_bar_mid_is_refused() -> None:
    weak = MEAN_REVERSION_H1_V1.explain(
        context(
            candles=build_series(signal=BarSpec(D("99"), D("101.5"), D("97"), D("99"), VOLUME))
        ),
        PARAMS,
    )

    assert weak.state is EvaluationState.NOT_TRIGGERED
    assert weak.reason == "close_below_mid"


def test_an_atr_below_the_declared_floor_is_refused() -> None:
    """``half = 0.02`` põe o ATR em 0,04 e o ATR% em 0,0004 — abaixo de 0,006."""
    quiet = MEAN_REVERSION_H1_V1.explain(
        context(
            candles=build_series(
                half=D("0.02"), signal=BarSpec(D("99"), D("99.99"), D("97.99"), D("99"), VOLUME)
            )
        ),
        PARAMS,
    )

    assert quiet.state is EvaluationState.NOT_TRIGGERED
    assert quiet.reason == "atr_out_of_range"


def test_a_short_history_is_unavailable_and_never_a_false_condition() -> None:
    """Um histórico que começa na hora 5 não alcança a hora 3, onde a janela de
    97 barras de ATR começa: a resposta é ``atr_warmup``, nunca ``not_triggered``
    — o worker não pode re-armar um mercado numa barra que não conseguiu ler."""
    late = [c for c in build_series() if c.open_time >= ORIGIN + timedelta(hours=5)]

    short = MEAN_REVERSION_H1_V1.explain(context(candles=late), PARAMS)

    assert short.state is EvaluationState.UNAVAILABLE
    assert short.reason == "atr_warmup"


def test_an_ineligible_market_never_reaches_the_windows() -> None:
    blocked = MEAN_REVERSION_H1_V1.explain(
        context(eligible=False, eligibility_reason="not_in_monitored_universe"), PARAMS
    )

    assert blocked.state is EvaluationState.INELIGIBLE
    assert blocked.reason == "ineligible"
    assert blocked.detail["eligibility_reason"] == "not_in_monitored_universe"


# ------------------------------------------------------------ 3. anti-antecipação


def test_it_ignores_the_future_the_forming_candle_and_a_mutated_future() -> None:
    """As três mutações: uma vela **não final** dentro da janela, sessenta velas
    finais **depois** do corte, e um futuro adulterado. Comparadas no JSON
    canônico do envelope, não só na decisão."""
    clean = build_series()
    baseline = decision_of(clean)

    forming = minute(
        CUT - timedelta(minutes=1),
        D("100"),
        D("9999"),
        D("1"),
        D("5000"),
        D("999"),
        is_final=False,
    )
    absurd = BarSpec(D("100"), D("9999"), D("0.01"), D("5000"), D("999999"))
    with_future = [*clean, *explode(absurd, CUT, 60)]
    mutated_future = [
        *clean,
        *explode(BarSpec(D("1"), D("2"), D("0.5"), D("1.5"), D("3")), CUT, 60),
    ]

    assert baseline is not None
    for polluted in ([*clean, forming], with_future, mutated_future):
        decision = decision_of(polluted)
        assert decision is not None
        assert canonical_json(decision.supporting_features.to_jsonable()) == canonical_json(
            baseline.supporting_features.to_jsonable()
        )
        assert decision == baseline


@pytest.mark.parametrize(
    ("high", "low", "close", "volume"),
    [
        (D("9999"), D("0.01"), D("5000"), D("999999")),
        (D("100.01"), D("99.99"), D("100"), D("0")),
        (D("120"), D("80"), D("81"), D("7")),
    ],
)
def test_mutating_the_candle_still_forming_never_moves_the_decision(
    high: Decimal, low: Decimal, close: Decimal, volume: Decimal
) -> None:
    """A propriedade que o brief pede por escrito: mexer numa vela ``is_final =
    False`` não muda **nenhum** número da decisão — nem o z-score, nem o ATR, nem
    os níveis, nem uma evidência do envelope."""
    clean = build_series()
    baseline = decision_of(clean)
    forming = minute(CUT - timedelta(minutes=1), D("100"), high, low, close, volume, is_final=False)

    mutated = decision_of([*clean, forming])

    assert baseline is not None and mutated is not None
    assert mutated == baseline
    assert canonical_json(mutated.supporting_features.to_jsonable()) == canonical_json(
        baseline.supporting_features.to_jsonable()
    )


def test_the_forming_4h_bar_never_reaches_the_trend_gate() -> None:
    """Corte duas horas dentro de uma barra de 4 h. A barra 100 está dentro dela:
    mexer no fechamento move o z-score de 1 h (−4,3589 → −3, e isso é correto) e
    **não pode** mover ``close_4h``, ``sma_4h`` nem os níveis da decisão."""
    baseline = decision_of(forming_4h_series(), FORMING_4H_CUT)
    mutated = decision_of(forming_4h_series(forming_close=D("99")), FORMING_4H_CUT)

    assert baseline is not None and mutated is not None
    trend = [features(decision) for decision in (baseline, mutated)]
    assert trend[0]["close_4h"] == trend[1]["close_4h"] == D("100")
    assert trend[0]["sma_4h"] == trend[1]["sma_4h"] == SMA_4H
    assert (baseline.reference_price, baseline.stop, baseline.target1) == (
        mutated.reference_price,
        mutated.stop,
        mutated.target1,
    )
    # a mutação é real e aparece exatamente onde deve: no z-score de 1 h
    assert trend[0]["zscore_1h"] != trend[1]["zscore_1h"]
    assert trend[1]["zscore_1h"] == D("-3")


def test_bootstrap_equals_a_longer_history() -> None:
    """A janela de ATR (97 barras de 1 h) é a mais longa das três, então uma série
    aparada nela decide o mesmo que uma com o histórico inteiro."""
    candles = build_series()
    atr_start = CUT - timedelta(hours=97)
    trimmed = [candle for candle in candles if candle.open_time >= atr_start]

    full = decision_of(candles)
    bootstrap = decision_of(trimmed)

    assert full is not None
    assert len(trimmed) < len(candles)
    assert bootstrap == full


def test_it_survives_a_hostile_ambient_decimal_context() -> None:
    ctx = context()
    baseline = MEAN_REVERSION_H1_V1.evaluate(ctx, PARAMS)

    with localcontext() as ambient:
        ambient.prec = 6
        ambient.rounding = ROUND_DOWN
        narrowed = MEAN_REVERSION_H1_V1.evaluate(ctx, PARAMS)

    assert baseline is not None
    assert narrowed == baseline


def test_evaluate_is_pure_two_calls_agree() -> None:
    ctx = context()

    assert MEAN_REVERSION_H1_V1.evaluate(ctx, PARAMS) == MEAN_REVERSION_H1_V1.evaluate(ctx, PARAMS)


# --------------------------------------------------------------- 4. isolamento do digest


def test_the_live_versions_digests_did_not_move() -> None:
    """Acrescentar este módulo não pode re-congelar nenhuma versão já ativada na
    VPS — inclusive a linha ``paper`` de ``momentum``."""
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
    """O fecho é o mesmo da mãe **mais este módulo**, e a mãe **não** está nele:
    importá-la amarraria os dois experimentos um ao outro."""
    from hunter_strategy_worker.code_ref import module_closure

    closure = module_closure("mean_reversion_h1_v1")

    assert closure == (
        "aggregate",
        "base",
        "canonical",
        "envelope",
        "indicators",
        "mean_reversion_h1_v1",
        "numeric",
        "schema",
    )
    assert "mean_reversion_v1" not in closure
    assert "constraints" not in closure
    for module in (
        "momentum_v1",
        "volume_anomaly_v1",
        "breakout_v1",
        "mean_reversion_v1",
        "session_orb_v1",
        "sweep_reclaim_v1",
        "trendline_breakout_v1",
    ):
        assert "mean_reversion_h1_v1" not in module_closure(module)


def test_the_catalogue_resolves_this_family_to_this_module_only() -> None:
    """``registry_key('mean_reversion_h1', 'v1') == 'mean_reversion_h1_v1'`` — a
    linha de ``strategies`` que ``seed_reference.py`` cria acha este código, e a
    **família** dela tem um membro só, então nenhuma outra estratégia pode ser
    executada sob esse nome.

    Consequência a declarar (não é defeito, é bom saber): a família de
    ``mean_reversion`` passa a ter **dois** membros, porque
    ``mean_reversion_h1_v1`` começa com ``mean_reversion_``. A checagem de
    família de ``catalogue.resolve_strategy`` fica um passo mais permissiva para
    aquela família — só alcança uma linha cujo ``code_ref`` tenha sido escrito à
    mão apontando para o módulo errado, que os scripts auditados nunca escrevem.
    """
    from hunter_core.strategies.registry import DEFAULT_REGISTRY
    from hunter_strategy_worker.catalogue import registry_key
    from hunter_strategy_worker.code_ref import strategy_module

    assert registry_key("mean_reversion_h1", "v1") == MEAN_REVERSION_H1_V1.key
    assert DEFAULT_REGISTRY.get("mean_reversion_h1_v1", "v1") is MEAN_REVERSION_H1_V1
    assert strategy_module(MEAN_REVERSION_H1_V1) == "mean_reversion_h1_v1"

    def family(key: str) -> set[str]:
        return {strategy_module(s) for s in DEFAULT_REGISTRY.all() if s.key.startswith(f"{key}_")}

    assert family("mean_reversion_h1") == {"mean_reversion_h1_v1"}
    assert family("mean_reversion") == {"mean_reversion_v1", "mean_reversion_h1_v1"}


# --------------------------------------------------------------- 5. orçamento de janela


def test_this_version_needs_more_context_than_the_worker_gives_today() -> None:
    """O custo operacional do eixo de timeframe, em um número.

    Escalar a grade por 4 escala o alcance por 4. ``SHADOW_CONTEXT_MINUTES`` é um
    botão **compartilhado** por todas as versões (subi-lo encarece cada barra de
    todo mundo), então este teste não o assume corrigido: ele **declara** o
    conflito, com os dois números fixados, para que o dia em que alguém subir o
    botão apareça num diff.
    """
    from hunter_strategy_worker.config import ShadowConfig

    atr_reach = int(PARAMS["atr_bars"]) * 60
    trend_reach = (int(PARAMS["trend_sma_bars"]) + 1) * 240 + (240 - 60)
    zscore_reach = int(PARAMS["zscore_bars"]) * 60

    assert (atr_reach, trend_reach, zscore_reach) == (5820, 5220, 1200)
    assert max(atr_reach, trend_reach, zscore_reach) == 5820
    assert ShadowConfig().context_minutes == 1560
    assert 5820 > ShadowConfig().context_minutes


def test_the_atr_window_dominates_the_trend_window_as_in_the_mother() -> None:
    atr_reach = int(PARAMS["atr_bars"]) * 60
    trend_reach = (int(PARAMS["trend_sma_bars"]) + 1) * 240 + (240 - 60)

    assert atr_reach > trend_reach


# --------------------------------------------------------------------- 6. constraints


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"zscore_depth_min": "0"}, "zscore_depth_min"),
        ({"stop_atr": "0"}, "stop_atr"),
        ({"target_atr": "-1"}, "target_atr"),
        ({"atr_pct_min": "0.9"}, "atr_pct_min"),
        ({"base_confidence": "42"}, "base_confidence"),
        ({"trend_sma_bars": "0"}, "trend_sma_bars"),
    ],
)
def test_check_ranges_refuses_the_probes(override: dict[str, str], fragment: str) -> None:
    parent = {name: str(value) for name, value in PARAMS.items()}

    problems = check_ranges(MEAN_REVERSION_H1_V1, parent, {**parent, **override})

    assert any(fragment in problem for problem in problems), problems


def test_the_frozen_contract_passes_its_own_check() -> None:
    parent = {name: str(value) for name, value in PARAMS.items()}

    assert check_ranges(MEAN_REVERSION_H1_V1, parent, parent) == []


# ------------------------------------------------------------- 7. identidade congelada


def test_default_parameters_are_the_frozen_contract() -> None:
    assert dict(PARAMS) == {
        "trend_timeframe": "4h",
        "trend_sma_bars": 20,
        "zscore_bars": 20,
        "zscore_depth_min": D("1"),
        "atr_period": 14,
        "atr_timeframe": "1h",
        "atr_bars": 97,
        "atr_pct_min": D("0.006"),
        "atr_pct_max": D("0.05"),
        "stop_atr": D("1"),
        "target_atr": D("1.5"),
        "target2_atr": D("2.5"),
        "horizon_s": 57600,
        "base_confidence": D("0.5"),
        "assumed_spread_bps": D("2"),
        "slippage_bps": D("5"),
        "fee_bps": D("4"),
        "max_entry_delay_s": 120,
    }


def test_exactly_three_parameters_differ_from_the_mother() -> None:
    """O experimento tem um eixo só: a grade. Se um quarto parâmetro divergir, a
    comparação pareada contra ``mean_reversion`` deixa de medir o timeframe."""
    mother = dict(MEAN_REVERSION_V1.default_parameters)
    child = dict(PARAMS)

    assert set(mother) == set(child)
    assert {name for name in mother if mother[name] != child[name]} == {
        "trend_timeframe",
        "atr_timeframe",
        "horizon_s",
    }
    assert MEAN_REVERSION_V1.timeframe is Timeframe.M15
    assert MEAN_REVERSION_H1_V1.timeframe is Timeframe.H1


def test_the_params_hash_is_pinned() -> None:
    """Identidade congelada deste conjunto: se ela se mover, é versão nova."""
    assert params_hash(PARAMS) == (
        "985316dde26224666176645749cfae0b7bcba2a8f7300ef0c98f31cb735c53d3"
    )


def test_the_identity_differs_from_the_mothers() -> None:
    assert params_hash(PARAMS) != params_hash(MEAN_REVERSION_V1.default_parameters)
