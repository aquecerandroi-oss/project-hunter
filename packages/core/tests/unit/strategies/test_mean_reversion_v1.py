"""``mean_reversion_v1`` — brief T3.33b, EXP-0009.

A série base é construída para que **todo número esperado seja exato e escrito à
mão**. Cem barras de 15 min terminando no corte:

- barras 0–79: rampa de fechamentos ``20, 21, …, 99`` (subida de 1 por barra);
- barras 80–98: patamar em ``100``;
- barra 99 (o sinal): fecha em ``99``, máxima ``100.75``, mínima ``96.25``.

Toda barra tem ``half_range = 2.25`` e todo passo de fechamento é ``|Δ| ≤ 2.25``,
então **todo true range vale exatamente 4,5** e o ATR de Wilder(14) sobre as 97
barras da janela é ``4.5`` sem arredondamento. Daí saem, exatos:

``referência 99 · stop 94,5 · alvo1 105,75 · alvo2 informativo 110,25``
``z(15m) = −4,358898943540673552236981984 · SMA(1h) = 75,2 · fechamento(1h) = 99``

Run: ``uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py -q``
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, localcontext
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import StrategyContext, build_context
from hunter_core.strategies.constraints import check_ranges
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1
from hunter_core.strategies.numeric import CONTEXT

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, series

pytestmark = pytest.mark.unit

PARAMS = MEAN_REVERSION_V1.default_parameters
RAMP_BARS = 80
PLATEAU_BARS = 19
TOTAL_BARS = RAMP_BARS + PLATEAU_BARS + 1
"""100 barras de 15 min = 1500 min: cobre a janela de ATR (1455) e a de tendência
(1260, terminando numa fronteira de hora), que é o pior caso do §7 do brief."""

CUT = ORIGIN + timedelta(minutes=15 * TOTAL_BARS)
HALF = D("2.25")
"""Meia-amplitude de toda barra: ``true_range = 2 × 2.25 = 4.5`` enquanto o passo
de fechamento não passar de 2,25."""
VOLUME = D("100")
PLATEAU = D("100")

SIGNAL_BAR = BarSpec(D("99"), D("100.75"), D("96.25"), D("99"), VOLUME)
"""O recuo: fecha em 99 (0,95 abaixo da média de 99,95), meio da barra em 98,5 —
fecha **acima** do próprio meio — e ``true_range = max(4.5, 0.75, 3.75) = 4.5``."""

ZSCORE_15M = D("-4.358898943540673552236981984")
"""``(99 − 99.95) / sqrt(0.0475)`` sob ``CONTEXT`` (28 dígitos)."""


def _bar(close: Decimal, *, half: Decimal = HALF, volume: Decimal = VOLUME) -> BarSpec:
    return BarSpec(close, close + half, close - half, close, volume)


def _ramp(start: Decimal, step: Decimal, *, half: Decimal = HALF) -> list[BarSpec]:
    """``RAMP_BARS`` barras cujos fechamentos andam ``step`` por barra a partir de
    ``start``; as duas rampas usadas terminam em 99, colada no patamar."""
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
    return series(specs[:bars], timeframe=Timeframe.M15)


FORMING_HOUR_BARS = TOTAL_BARS + 2
FORMING_HOUR_CUT = ORIGIN + timedelta(minutes=15 * FORMING_HOUR_BARS)
"""Corte às :30 de uma hora cheia: as barras 100 e 101 caem dentro da **hora em
formação**, que a porta de tendência tem de ignorar inteira."""


def forming_hour_series(*, forming_close: Decimal = PLATEAU) -> list[NormalizedCandle]:
    """102 barras: a rampa, 21 de patamar e o recuo. ``forming_close`` é o
    fechamento da barra 100 — a primeira barra da hora em formação."""
    specs = [
        *_ramp(D("20"), D("1")),
        *[_bar(PLATEAU)] * (PLATEAU_BARS + 1),
        _bar(forming_close),
        SIGNAL_BAR,
    ]
    return series(specs, timeframe=Timeframe.M15)


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def features(decision: Any) -> dict[str, Any]:
    return {feature.name: feature.value for feature in decision.supporting_features.features}


# --------------------------------------------------------------------------- 1. dispara


def test_it_signals_on_the_constructed_pullback() -> None:
    decision = MEAN_REVERSION_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == D("99")
    assert decision.stop == D("94.5")  # 99 − 1.0 × 4.5
    assert decision.target1 == D("105.75")  # 99 + 1.5 × 4.5
    assert decision.targets_informational == (D("110.25"),)  # 99 + 2.5 × 4.5
    assert decision.horizon_s == 14400
    assert decision.confidence == D("0.5")


def test_there_is_no_invalidation_on_purpose() -> None:
    """Braço ``INV-B`` da KB-0006: stop, alvo e horizonte são a política inteira."""
    decision = MEAN_REVERSION_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.invalidations == ()


def test_the_target_is_one_and_a_half_times_the_risk_at_the_reference() -> None:
    decision = MEAN_REVERSION_V1.evaluate(context(), PARAMS)

    assert decision is not None
    risk = decision.reference_price - decision.stop
    assert risk == D("4.5")
    assert decision.target1 - decision.reference_price == risk * D("1.5")


def test_the_envelope_carries_every_audited_value() -> None:
    decision = MEAN_REVERSION_V1.evaluate(context(), PARAMS)

    assert decision is not None
    envelope = decision.supporting_features
    assert envelope.observation_ts == CUT
    assert envelope.strategy_key == "mean_reversion_v1"
    assert envelope.strategy_version == "v1"
    assert envelope.timeframe == "15m"
    assert envelope.purpose == "research_only"
    values = features(decision)
    assert values["open_15m"] == D("99")
    assert values["high_15m"] == D("100.75")
    assert values["low_15m"] == D("96.25")
    assert values["volume_15m"] == VOLUME
    assert values["close_15m"] == D("99")
    assert values["sma_15m"] == D("99.95")
    assert values["sd_15m"] == D("0.2179449471770336776118490992")
    assert values["zscore_15m"] == ZSCORE_15M
    assert values["bar_mid_15m"] == D("98.5")
    assert values["close_1h"] == D("99")
    assert values["sma_1h"] == D("75.2")
    assert values["atr_pct_15m"] == D("0.04545454545454545454545454545")  # 4.5 / 99
    assert envelope.atr is not None
    assert envelope.atr.value == D("4.5")
    assert envelope.atr.seed == D("4.5")
    assert envelope.atr.period == 14
    assert envelope.atr.method == "wilder_v1"
    assert envelope.atr.origin == "rolling_window_v1"
    assert envelope.atr.bars_used == 97
    assert envelope.atr.window_end == CUT
    assert envelope.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )


def test_the_windows_recorded_next_to_each_number_are_the_frozen_ones() -> None:
    """Um z-score sem a janela, a média e o desvio ao lado não é auditável depois
    que as velas de 1 min saem da retenção (brief §9)."""
    decision = MEAN_REVERSION_V1.evaluate(context(), PARAMS)

    assert decision is not None
    windows = {f.name: f.window for f in decision.supporting_features.features}
    assert windows["zscore_15m"] == 20
    assert windows["sma_15m"] == 20
    assert windows["sd_15m"] == 20
    assert windows["sma_1h"] == 20
    assert windows["atr_pct_15m"] == 97


def test_the_reason_is_deterministic_and_quotes_the_numbers() -> None:
    first = MEAN_REVERSION_V1.evaluate(context(), PARAMS)
    second = MEAN_REVERSION_V1.evaluate(context(), PARAMS)

    assert first is not None and second is not None
    assert first.reason == second.reason
    assert first.reason == (
        "Mean reversion 15m: fechamento 99 a -4.36 desvios da média de 20 fechamentos "
        "(99.95), dentro de tendência de alta de 1h (fechamento 99 acima da SMA de 20 "
        "horas, 75.2), fechamento acima do meio da barra (98.5), ATR% 4.55%"
    )


# --------------------------------------------------------------- 2. a aritmética do z-score


def test_the_zscore_matches_the_value_computed_by_hand() -> None:
    """Série do brief §10.2: fechamentos ``[100]*19 + [97]``. Média, variância
    populacional e desvio calculados aqui, com ``Decimal``, não ``approx``."""
    closes = [D("100")] * 19 + [D("97")]
    with localcontext(CONTEXT):
        mean = sum(closes, start=D(0)) / D(20)
        variance = sum(((close - mean) ** 2 for close in closes), start=D(0)) / D(20)
        sd = variance.sqrt()
        expected = (closes[-1] - mean) / sd
    assert mean == D("99.85")
    assert variance == D("0.4275")
    assert sd == D("0.6538348415311010328355472976")
    assert expected == D("-4.358898943540673552236981984")

    decision = MEAN_REVERSION_V1.evaluate(
        context(candles=build_series(signal=_bar(D("97")))), PARAMS
    )

    assert decision is not None
    values = features(decision)
    assert values["sma_15m"] == mean
    assert values["sd_15m"] == sd
    assert values["zscore_15m"] == expected


def test_the_depth_gate_is_inclusive_at_exactly_one_sd() -> None:
    """Dez fechamentos em 101 e dez em 99 dão média 100 e desvio 1 exatos: o
    último fechamento está a ``z = −1``, e a regra é ``z <= −zscore_depth_min``."""
    alternating = [_bar(D("101") if index % 2 == 0 else D("99")) for index in range(PLATEAU_BARS)]
    candles = series(
        [*_ramp(D("20"), D("1")), *alternating, _bar(D("99"))], timeframe=Timeframe.M15
    )

    decision = MEAN_REVERSION_V1.evaluate(context(candles=candles), PARAMS)

    assert decision is not None
    values = features(decision)
    assert values["sma_15m"] == D("100")
    assert values["sd_15m"] == D("1")
    assert values["zscore_15m"] == D("-1")


# --------------------------------------------------------------- 3. não dispara, um ramo cada


def test_a_falling_hourly_trend_blocks_the_signal() -> None:
    """Rampa descendente de 178 a 99: a SMA de 20 horas fica em 123,2."""
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=build_series(ramp=_ramp(D("178"), D("-1")))), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.state.value == "not_triggered"
    assert evaluation.reason == "no_uptrend_1h"
    assert evaluation.detail == {"close_1h": "99", "sma_1h": "123.2"}


def test_a_close_that_is_not_stretched_blocks_the_signal() -> None:
    """Mesma série, sinal fechando **acima** do patamar: ``z = +4.36``."""
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=build_series(signal=_bar(D("101")))), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "not_stretched"
    assert evaluation.detail == {"zscore_15m": "4.358898943540673552236981984"}


def test_a_bar_still_falling_at_its_own_close_blocks_the_signal() -> None:
    """Mesmo fechamento esticado, mas a barra ainda cai no próprio fechamento:
    máxima 102,25 e mínima 97,75 põem o meio em 100, acima do fechamento 99."""
    still_falling = BarSpec(D("99"), D("102.25"), D("97.75"), D("99"), VOLUME)
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=build_series(signal=still_falling)), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "close_below_mid"
    assert evaluation.detail == {"close_15m": "99", "bar_mid_15m": "100"}


def test_volatility_above_the_ceiling_blocks_the_signal() -> None:
    """Toda barra com meia-amplitude 3: ATR 6 sobre 99 = 6,06 % > 5 %."""
    wild_signal = BarSpec(D("99"), D("100.5"), D("94.5"), D("99"), VOLUME)
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=build_series(half=D("3"), signal=wild_signal)), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "atr_out_of_range"
    assert evaluation.detail == {"atr_pct_15m": "0.06060606060606060606060606061"}


def test_an_ineligible_market_is_not_evaluated() -> None:
    evaluation = MEAN_REVERSION_V1.explain(
        context(eligible=False, eligibility_reason="not_in_universe"), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.state.value == "ineligible"
    assert evaluation.reason == "ineligible"
    assert evaluation.detail == {"eligibility_reason": "not_in_universe"}


# --------------------------------------------------------------- 4. indisponível, um ramo cada


def test_a_short_history_is_warmup_on_the_signal_window() -> None:
    candles = build_series(bars=19)
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=candles, cut=ORIGIN + timedelta(minutes=15 * 19)), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.state.value == "unavailable"
    assert evaluation.reason == "warmup"


def test_a_missing_minute_inside_the_signal_window_is_a_gap() -> None:
    candles = build_series()
    del candles[1400]  # 23h20 — dentro das 20 barras de 15 min do z-score

    evaluation = MEAN_REVERSION_V1.explain(context(candles=candles), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "gap"
    assert evaluation.detail["missing_minute"] == "2026-01-01T23:20:00Z"


def test_a_history_shorter_than_the_atr_window_is_atr_warmup() -> None:
    candles = build_series(bars=30)
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=candles, cut=ORIGIN + timedelta(minutes=15 * 30)), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "atr_warmup"


def test_a_trend_window_longer_than_the_history_is_trend_warmup() -> None:
    """Só alcançável por variante: com os defaults congelados a janela de ATR
    domina a de tendência (ver ``test_the_atr_window_dominates_the_trend_window``)."""
    evaluation = MEAN_REVERSION_V1.explain(context(), {**PARAMS, "trend_sma_bars": 40})

    assert evaluation.decision is None
    assert evaluation.reason == "trend_warmup"


def test_a_hole_inside_the_trend_window_is_trend_gap() -> None:
    """Idem: com ``atr_bars = 20`` a janela de ATR deixa de cobrir a de tendência,
    e o buraco do minuto 300 só é visto pela porta de 1 h."""
    candles = build_series()
    del candles[300]

    evaluation = MEAN_REVERSION_V1.explain(context(candles=candles), {**PARAMS, "atr_bars": 20})

    assert evaluation.decision is None
    assert evaluation.reason == "trend_gap"
    assert evaluation.detail["missing_minute"] == "2026-01-01T05:00:00Z"


def test_a_flat_window_has_no_dispersion_and_is_unavailable() -> None:
    """Patamar puro: desvio zero não é ``z = 0``, é leitura indisponível."""
    evaluation = MEAN_REVERSION_V1.explain(
        context(candles=build_series(signal=_bar(PLATEAU))), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.state.value == "unavailable"
    assert evaluation.reason == "zscore_degenerate"


def test_a_close_that_is_not_a_15m_boundary_is_misaligned() -> None:
    evaluation = MEAN_REVERSION_V1.explain(context(cut=CUT - timedelta(minutes=5)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "misaligned"


# --------------------------------------------------------------- 5. recusado


def test_a_stop_on_top_of_the_reference_is_refused_by_geometry() -> None:
    evaluation = MEAN_REVERSION_V1.explain(context(), {**PARAMS, "stop_atr": D("0")})

    assert evaluation.decision is None
    assert evaluation.state.value == "rejected"
    assert evaluation.reason == "geometry"
    assert evaluation.detail["stop"] == "99"


# --------------------------------------------------------------- 7/8. bootstrap, pureza


def test_bootstrap_equals_continuous_execution() -> None:
    """O worker faz bootstrap de uma janela só e depois cresce barra a barra; os
    dois caminhos têm de concordar em todo fechamento de referência."""
    candles = build_series()
    bootstrap = MEAN_REVERSION_V1.evaluate(context(candles=candles), PARAMS)

    grown: list[NormalizedCandle] = []
    decisions = []
    for index in range(TOTAL_BARS):
        grown.extend(candles[index * 15 : (index + 1) * 15])
        cut = ORIGIN + timedelta(minutes=15 * (index + 1))
        decisions.append(MEAN_REVERSION_V1.evaluate(context(candles=list(grown), cut=cut), PARAMS))

    assert bootstrap is not None
    assert decisions[-1] == bootstrap
    assert [decision for decision in decisions[:-1] if decision is not None] == []


def test_evaluate_is_pure_two_calls_agree() -> None:
    ctx = context()

    assert MEAN_REVERSION_V1.evaluate(ctx, PARAMS) == MEAN_REVERSION_V1.evaluate(ctx, PARAMS)


# --------------------------------------------------------------- 9. isolamento do digest


def test_the_live_versions_digests_did_not_move() -> None:
    """Brief §2: acrescentar este módulo não pode re-congelar as versões vivas."""
    from hunter_strategy_worker.code_ref import version_code_ref

    assert version_code_ref("momentum_v1") == (
        "hunter_core.strategies.momentum_v1@sha256:"
        "ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
    )
    assert version_code_ref("volume_anomaly_v1") == (
        "hunter_core.strategies.volume_anomaly_v1@sha256:"
        "9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"
    )


def test_this_version_closes_over_the_siblings_it_imports_and_no_others() -> None:
    from hunter_strategy_worker.code_ref import module_closure

    closure = module_closure("mean_reversion_v1")

    assert "constraints" not in closure
    assert "momentum_v1" not in closure and "volume_anomaly_v1" not in closure
    assert {"aggregate", "base", "indicators", "numeric", "schema"} <= set(closure)


# --------------------------------------------------------------- 10. constraints


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"zscore_depth_min": "0"}, "zscore_depth_min"),
        ({"stop_atr": "0"}, "stop_atr"),
        ({"target_atr": "-1"}, "target_atr"),
        ({"atr_pct_min": "0.9"}, "atr_pct_min"),
        ({"base_confidence": "42"}, "base_confidence"),
    ],
)
def test_check_ranges_refuses_the_probes(override: dict[str, str], fragment: str) -> None:
    parent = {name: str(value) for name, value in PARAMS.items()}

    problems = check_ranges(MEAN_REVERSION_V1, parent, {**parent, **override})

    assert any(fragment in problem for problem in problems), problems


def test_the_frozen_contract_passes_its_own_check() -> None:
    parent = {name: str(value) for name, value in PARAMS.items()}

    assert check_ranges(MEAN_REVERSION_V1, parent, parent) == []


# --------------------------------------------------------------- 11. orçamento de janela


def test_every_window_fits_the_shadow_context() -> None:
    """Brief §7. ``SHADOW_CONTEXT_MINUTES`` é botão do worker, compartilhado por
    todas as versões: subi-lo encarece cada barra de todo mundo."""
    from hunter_strategy_worker.config import ShadowConfig

    atr_reach = int(PARAMS["atr_bars"]) * 15
    trend_reach = (int(PARAMS["trend_sma_bars"]) + 1) * 60 + (60 - 15)
    zscore_reach = int(PARAMS["zscore_bars"]) * 15

    assert (atr_reach, trend_reach, zscore_reach) == (1455, 1305, 300)
    assert max(atr_reach, trend_reach, zscore_reach) <= ShadowConfig().context_minutes == 1560


def test_the_atr_window_dominates_the_trend_window() -> None:
    """Consequência a declarar: com os defaults congelados a janela de ATR começa
    **antes** da de tendência, então ``trend_warmup``/``trend_gap`` nunca aparecem
    no replay — o ``atr_*`` correspondente aparece primeiro. Só uma variante que
    encurte ``atr_bars`` ou alongue ``trend_sma_bars`` acorda esses dois ramos."""
    atr_reach = int(PARAMS["atr_bars"]) * 15
    trend_reach = (int(PARAMS["trend_sma_bars"]) + 1) * 60 + (60 - 15)

    assert atr_reach > trend_reach


# --------------------------------------------------------------- identidade congelada


def test_default_parameters_are_the_frozen_contract() -> None:
    assert dict(PARAMS) == {
        "trend_timeframe": "1h",
        "trend_sma_bars": 20,
        "zscore_bars": 20,
        "zscore_depth_min": D("1"),
        "atr_period": 14,
        "atr_timeframe": "15m",
        "atr_bars": 97,
        "atr_pct_min": D("0.006"),
        "atr_pct_max": D("0.05"),
        "stop_atr": D("1"),
        "target_atr": D("1.5"),
        "target2_atr": D("2.5"),
        "horizon_s": 14400,
        "base_confidence": D("0.5"),
        "assumed_spread_bps": D("2"),
        "slippage_bps": D("5"),
        "fee_bps": D("4"),
        "max_entry_delay_s": 120,
    }


def test_the_identity_is_the_one_the_catalogue_resolves() -> None:
    assert MEAN_REVERSION_V1.key == "mean_reversion_v1"
    assert MEAN_REVERSION_V1.version == "v1"
    assert MEAN_REVERSION_V1.timeframe is Timeframe.M15
