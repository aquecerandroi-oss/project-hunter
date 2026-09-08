"""A passada de estresse sobre um livro-razão sintético — T3.36.

Todos os números aqui são construídos à mão e conferidos por aritmética
fechada, nunca por "o que o código devolveu": um teste que aceita a saída do
próprio código não prova cálculo nenhum.

Os dois cenários que o brief exige por nome estão em
``test_costs_x2_flips_a_marginal_strategy`` e
``test_leave_one_out_finds_the_single_market_dependence``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from hunter_core.strategies.envelope import AssumedCosts
from hunter_indicators.replay.stress import (
    BASE,
    REWALK_SCENARIOS,
    StressFamily,
    StressKind,
    StressScenario,
    scenario,
    stressed_costs,
    stressed_levels,
)
from hunter_indicators.replay.stress_table import (
    MIN_SAMPLE,
    StressOutcome,
    aggregate,
    halves,
    leave_one_out,
    stress_verdict,
)

pytestmark = pytest.mark.unit

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=120
)
"""A hipótese congelada do Lab (SHADOW-LAB.md §3), rótulo de dado de teste."""

DAY0 = date(2026, 8, 8)


def outcome(
    index: int,
    r: str | None,
    *,
    market: str = "binance:AAAUSDT",
    day: date = DAY0,
    result: str = "target",
    dropped: str | None = None,
) -> StressOutcome:
    """Um desfecho sintético; ``r`` em string para nunca passar por float."""
    return StressOutcome(
        signal_id=f"sig-{index:03d}",
        market=market,
        entry_day=day,
        result=result,
        r_net=None if r is None else Decimal(r),
        dropped=dropped,
    )


def ledger(values: list[str], **kwargs: object) -> list[StressOutcome]:
    return [
        outcome(i, v, result=("target" if Decimal(v) > 0 else "stop"), **kwargs)  # type: ignore[arg-type]
        for i, v in enumerate(values)
    ]


# --- declarações -----------------------------------------------------------


def test_every_scenario_is_registered_with_its_identity() -> None:
    """Um cenário sem versão, descrição, entradas e parâmetros não é auditável."""
    for spec in REWALK_SCENARIOS:
        assert spec.version >= 1
        assert spec.description
        assert spec.inputs
        assert scenario(spec.key) is spec
    keys = [spec.key for spec in REWALK_SCENARIOS]
    assert keys[0] == BASE
    assert len(set(keys)) == len(keys)


def test_only_the_entry_delay_is_not_a_repricing() -> None:
    """A fronteira que o brief pede explicitamente."""
    not_repriced = [spec.key for spec in REWALK_SCENARIOS if not spec.repriced]
    assert not_repriced == ["entrada_mais_1_barra"]


def test_a_scenario_refuses_a_non_positive_factor() -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        StressScenario(
            key="x",
            version=1,
            description="d",
            family=StressFamily.PARAMETERS,
            kind=StressKind.REWALK,
            inputs=("candles:1m",),
            stop_scale=Decimal(0),
        )


# --- aritmética ------------------------------------------------------------


def test_doubling_the_costs_doubles_the_three_declared_bps_and_nothing_else() -> None:
    doubled = stressed_costs(COSTS, scenario("custos_x2"))
    assert doubled.spread_bps == Decimal(4)
    assert doubled.slippage_bps == Decimal(10)
    assert doubled.fee_bps == Decimal(8)
    assert doubled.max_entry_delay_s == 120, "o limite de atraso é admissão, não custo"
    assert stressed_costs(COSTS, scenario(BASE)) is COSTS


def test_levels_scale_around_the_entry_price() -> None:
    """entry 100, stop 98, alvo 103 → risco 2 e recompensa 3, escalados."""
    entry, stop, target = Decimal(100), Decimal(98), Decimal(103)
    tight, _ = stressed_levels(entry=entry, stop=stop, target1=target, spec=scenario("stop_x0.75"))
    wide, _ = stressed_levels(entry=entry, stop=stop, target1=target, spec=scenario("stop_x1.25"))
    assert tight == Decimal("98.5")
    assert wide == Decimal("97.5")
    _, near = stressed_levels(entry=entry, stop=stop, target1=target, spec=scenario("alvo_x0.75"))
    _, far = stressed_levels(entry=entry, stop=stop, target1=target, spec=scenario("alvo_x1.25"))
    assert near == Decimal("102.25")
    assert far == Decimal("103.75")


def test_scaling_a_parameter_never_breaks_the_frozen_geometry() -> None:
    """``stop < P_entry < target1`` sobrevive a qualquer fator positivo."""
    entry, stop, target = Decimal(100), Decimal(98), Decimal(103)
    for key in ("stop_x0.75", "stop_x1.25", "alvo_x0.75", "alvo_x1.25"):
        new_stop, new_target = stressed_levels(
            entry=entry, stop=stop, target1=target, spec=scenario(key)
        )
        assert new_stop < entry < new_target


# --- agregação -------------------------------------------------------------


def test_aggregate_counts_the_unevaluable_by_reason_and_never_as_zero() -> None:
    rows = [
        outcome(0, "0.5"),
        outcome(1, "-1"),
        outcome(2, None, dropped="gap:2026-08-09T00:00:00+00:00"),
        outcome(3, None),
    ]
    row = aggregate("x", rows, family=StressFamily.BASE)
    assert row.total == 4
    assert row.n == 2
    assert row.expectancy_r == Decimal("-0.25")
    assert row.dropped == {"gap:2026-08-09T00:00:00+00:00": 1, "r_net_indisponivel": 1}


def test_profit_factor_and_expectancy_agree_on_the_sign() -> None:
    """PF > 1 e expectancy > 0 são a mesma afirmação; o veredito usa uma só."""
    row = aggregate("x", ledger(["1.5", "-1", "-1", "1.2"]), family=StressFamily.BASE)
    assert row.expectancy_r == Decimal("0.175")
    assert row.profit_factor == Decimal("1.35")


# --- os dois cenários que o brief cobra por nome ---------------------------


def test_costs_x2_flips_a_marginal_strategy() -> None:
    """Base com +0,04 R por operação; dobrar o custo tira 0,10 R e vira o sinal.

    O livro-razão é o mesmo em ambos os cenários — 40 operações, 20 ganhos de
    +1 R e 20 perdas de −0,92 R —, e o cenário de custo aplica o desconto
    fechado de 0,10 R que o dobro do custo hipotético representa neste tamanho
    de risco. Base: (20·1 − 20·0,92)/40 = +0,04. Custo ×2: 0,04 − 0,10 = −0,06.
    """
    base_values = ["1"] * 20 + ["-0.92"] * 20
    base = aggregate(BASE, ledger(base_values), family=StressFamily.BASE)
    assert base.n == 40
    assert base.expectancy_r == Decimal("0.04")
    assert base.profit_factor is not None
    assert base.profit_factor > 1

    doubled_values = ["0.9"] * 20 + ["-1.02"] * 20
    stressed = aggregate("custos_x2", ledger(doubled_values), family=StressFamily.COSTS)
    assert stressed.expectancy_r == Decimal("-0.06")
    assert stressed.profit_factor is not None
    assert stressed.profit_factor < 1

    verdict = stress_verdict([base, stressed])
    assert verdict.verdict == "frágil a custos"
    assert verdict.reasons[0].startswith("frágil a custos: custos_x2")
    assert not verdict.robust


def test_leave_one_out_finds_the_single_market_dependence() -> None:
    """Um mercado carrega a vantagem inteira; sem ele a expectancy vira negativa.

    30 operações em AAA a +1 R e 30 em BBB a −0,8 R: base = +0,10 R. Tirar BBB
    sobe para +1 R (nada quebra); tirar AAA derruba para −0,8 R — e é essa a
    linha que o veredito tem de encontrar.
    """
    aaa = ledger(["1"] * 30, market="binance:AAAUSDT")
    bbb = ledger(["-0.8"] * 30, market="binance:BBBUSDT")
    everything = [*aaa, *bbb]
    base = aggregate(BASE, everything, family=StressFamily.BASE)
    assert base.expectancy_r == Decimal("0.1")

    rows = leave_one_out(everything)
    assert [row.key for row in rows] == ["sem_binance:AAAUSDT", "sem_binance:BBBUSDT"]
    without_aaa, without_bbb = rows
    assert without_aaa.n == 30
    assert without_aaa.expectancy_r == Decimal("-0.8")
    assert without_bbb.expectancy_r == Decimal("1")
    assert all(row.kind is StressKind.SUBSET for row in rows)

    verdict = stress_verdict([base, *rows])
    assert verdict.verdict == "dependente de um mercado"
    assert len(verdict.reasons) == 1
    assert "sem_binance:AAAUSDT" in verdict.reasons[0]


def test_leave_one_out_is_empty_with_a_single_market() -> None:
    assert leave_one_out(ledger(["1"] * 5)) == []


# --- metades ---------------------------------------------------------------


def test_halves_split_the_calendar_and_not_the_trade_count() -> None:
    """Janela 08-08..08-18: o corte é 08-13, mesmo com 1 operação numa metade."""
    early = [outcome(0, "3", day=date(2026, 8, 8))]
    late = [outcome(i, "-1", day=date(2026, 8, 18)) for i in range(1, 10)]
    rows = halves([*early, *late])
    assert [row.key for row in rows] == ["1a_metade_ate_2026-08-13", "2a_metade_apos_2026-08-13"]
    assert rows[0].n == 1
    assert rows[1].n == 9


def test_a_window_that_lives_in_one_day_has_no_halves() -> None:
    assert halves(ledger(["1", "-1"])) == []


def test_second_half_that_loses_makes_the_pass_dependent_on_a_half() -> None:
    first = [outcome(i, "1", day=date(2026, 8, 8)) for i in range(20)]
    second = [outcome(20 + i, "-0.5", day=date(2026, 9, 6)) for i in range(20)]
    everything = [*first, *second]
    base = aggregate(BASE, everything, family=StressFamily.BASE)
    assert base.expectancy_r == Decimal("0.25")
    rows = halves(everything)
    verdict = stress_verdict([base, *rows])
    assert verdict.verdict == "dependente de metade"


# --- veredito --------------------------------------------------------------


def test_a_base_below_the_minimum_sample_has_no_verdict() -> None:
    base = aggregate(BASE, ledger(["1"] * (MIN_SAMPLE - 1)), family=StressFamily.BASE)
    verdict = stress_verdict([base])
    assert verdict.verdict == "amostra_insuficiente"
    assert verdict.reasons == (f"{MIN_SAMPLE - 1} desfechos avaliáveis de {MIN_SAMPLE}",)


def test_a_losing_base_is_never_called_robust() -> None:
    """É o caso do `momentum v2`: robustez de uma vantagem que não existe."""
    base = aggregate(BASE, ledger(["-0.2"] * 40), family=StressFamily.BASE)
    stressed = aggregate("custos_x2", ledger(["-0.3"] * 40), family=StressFamily.COSTS)
    verdict = stress_verdict([base, stressed])
    assert verdict.verdict == "sem_vantagem_na_base"
    assert not verdict.robust


def test_a_strategy_that_survives_everything_is_robust() -> None:
    values = ["1", "-0.5"] * 20
    base = aggregate(BASE, ledger(values), family=StressFamily.BASE)
    rows = [
        aggregate(spec.key, ledger(values), family=spec.family)
        for spec in REWALK_SCENARIOS
        if spec.key != BASE
    ]
    verdict = stress_verdict([base, *rows])
    assert verdict.verdict == "robusto"
    assert verdict.reasons == ()


def test_a_scenario_without_evaluable_outcomes_is_a_disagreement_not_a_zero() -> None:
    base = aggregate(BASE, ledger(["1", "-0.5"] * 20), family=StressFamily.BASE)
    blind = aggregate(
        "custos_x2",
        [outcome(i, None, dropped="geometry") for i in range(40)],
        family=StressFamily.COSTS,
    )
    assert blind.expectancy_r is None
    assert stress_verdict([base, blind]).verdict == "frágil a custos"


def test_the_verdict_reports_every_broken_family_not_only_the_first() -> None:
    values = ["1", "-0.5"] * 20
    base = aggregate(BASE, ledger(values), family=StressFamily.BASE)
    costs = aggregate("custos_x2", ledger(["-0.1"] * 40), family=StressFamily.COSTS)
    params = aggregate("stop_x0.75", ledger(["-0.2"] * 40), family=StressFamily.PARAMETERS)
    verdict = stress_verdict([base, costs, params])
    assert verdict.verdict == "frágil a custos"
    assert len(verdict.reasons) == 2
    assert "stop_x0.75" in verdict.reasons[1]
