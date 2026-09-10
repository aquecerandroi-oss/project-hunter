"""O eixo da tabela de estresse quando o funding é indeterminado — T3.75.

A T3.62b mediu o estrago (`.claude/state/notes-T3.62b.md` §7.2): a coorte de 90
dias da `mean_reversion v10` tem 798 desfechos terminais e **498** deles com
`r_multiple` nulo por `funding_schedule_unknown`, porque `funding_rates` só
existia a partir de 2026-08-08 16:00Z. O motor de estresse reprecifica a partir
de `r_multiple`, então ele descartava aquelas 498 linhas: o `base` saía com
n = 300, a primeira metade do calendário saía com **n = 0** e o veredito
`dependente de metade` era um artefato de cobertura de dado, não uma leitura
sobre a estratégia.

Estes testes provam a queda para `r_ex_funding` **e o seu limite**: ela vale só
para `funding_schedule_unknown` — o único motivo que é um fato sobre a
*cobertura da tabela* (não há histórico para ler a cadência), e não sobre
*aquela operação*. `funding_ambiguous_exit`, `funding_missing` e
`funding_conflicting_rows` continuam descartes: ali a dúvida é da própria
operação, e trocar o eixo esconderia uma ambiguidade real.

Todos os números são conferidos por aritmética fechada à mão, nunca copiados da
saída do código.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.replay.stress import BASE, StressAxis, StressFamily, StressKind
from hunter_indicators.replay.stress_table import (
    StressOutcome,
    aggregate,
    halves,
    stress_verdict,
)

pytestmark = pytest.mark.unit

DAY0 = date(2026, 6, 12)
"""O primeiro dia da janela de 90 d da T3.62b — rótulo de dado de teste."""


def net(index: int, r: str, *, day: date = DAY0, result: str = "target") -> StressOutcome:
    """Um desfecho com ``R_net`` conhecido: o eixo continua ``r_net``."""
    return StressOutcome(
        signal_id=f"net-{index:03d}",
        market="binance:AAAUSDT",
        entry_day=day,
        result=result,
        r_net=Decimal(r),
    )


def blind(
    index: int,
    r_exf: str | None,
    *,
    day: date = DAY0,
    result: str = "target",
    indeterminate: bool = True,
    dropped: str | None = None,
) -> StressOutcome:
    """Um desfecho sem ``R_net``, com (ou sem) ``r_ex_funding`` para cair nele."""
    return StressOutcome(
        signal_id=f"blind-{index:03d}",
        market="binance:AAAUSDT",
        entry_day=day,
        result=result,
        r_net=None,
        dropped=dropped,
        r_ex_funding=None if r_exf is None else Decimal(r_exf),
        funding_indeterminate=indeterminate,
    )


# ---- o desfecho, uma linha por vez -----------------------------------------


def test_a_schedule_unknown_outcome_is_measured_on_r_ex_funding_not_dropped() -> None:
    """O caso das 498 linhas da ``v10``: sem ``R_net``, mas com ``r_ex_funding``."""
    outcome = blind(1, "0.2500")

    assert outcome.axis is StressAxis.R_EX_FUNDING
    assert outcome.r == Decimal("0.2500")
    assert outcome.evaluable is True


def test_an_outcome_with_r_net_stays_on_r_net_even_when_r_ex_funding_exists() -> None:
    """``r_ex_funding`` existe em 100 % dos desfechos: ele nunca pode
    *substituir* um ``R_net`` conhecido, só cobrir a ausência dele."""
    outcome = StressOutcome(
        signal_id="both",
        market="binance:AAAUSDT",
        entry_day=DAY0,
        result="target",
        r_net=Decimal("1.0000"),
        r_ex_funding=Decimal("1.0011"),
    )

    assert outcome.axis is StressAxis.R_NET
    assert outcome.r == Decimal("1.0000")


def test_a_funding_reason_that_is_not_schedule_unknown_is_still_a_drop() -> None:
    """Saída ambígua é dúvida sobre *aquela* operação, não sobre a cobertura."""
    outcome = blind(2, "0.9", indeterminate=False, dropped="funding_ambiguous_exit")

    assert outcome.axis is StressAxis.R_NET
    assert outcome.r is None
    assert outcome.evaluable is False


def test_an_indeterminate_outcome_without_r_ex_funding_is_still_never_zero() -> None:
    """Sem nenhum dos dois eixos não há número: a linha continua fora da conta."""
    outcome = blind(3, None)

    assert outcome.r is None
    assert outcome.evaluable is False


# ---- a linha da tabela ------------------------------------------------------


def test_the_row_declares_the_axis_and_counts_the_fallbacks() -> None:
    """Média conferida à mão sobre os cinco: (1,0 + 0,5 - 0,25 + 0,75 - 0,5)/5.

    soma = 1,50   n = 5   expectancy = 0,30
    PF = (1,0 + 0,5 + 0,75) / (0,25 + 0,5) = 2,25 / 0,75 = 3
    """
    outcomes = [
        net(1, "1.00"),
        net(2, "0.50"),
        blind(1, "-0.25"),
        blind(2, "0.75"),
        blind(3, "-0.50"),
    ]

    row = aggregate(BASE, outcomes, family=StressFamily.BASE, kind=StressKind.REWALK)

    assert row.n == 5
    assert row.expectancy_r == Decimal("0.30")
    assert row.profit_factor == Decimal(3)
    assert row.axis is StressAxis.R_EX_FUNDING
    assert row.funding_indeterminate == 3
    assert "funding_indeterminado" not in row.dropped


def test_a_row_with_no_indeterminate_funding_stays_declared_on_r_net() -> None:
    outcomes = [net(1, "1.00"), net(2, "-0.50")]

    row = aggregate(BASE, outcomes, family=StressFamily.BASE, kind=StressKind.REWALK)

    assert row.axis is StressAxis.R_NET
    assert row.funding_indeterminate == 0
    assert row.expectancy_r == Decimal("0.25")


def test_a_dropped_outcome_keeps_its_own_name_in_the_dropped_map() -> None:
    """O descarte que sobra é nomeado pelo motivo, nunca por um rótulo genérico
    que colidiria com a contagem do eixo."""
    outcomes = [net(1, "1.00"), blind(9, "0.4", indeterminate=False, dropped="funding_missing")]

    row = aggregate(BASE, outcomes, family=StressFamily.BASE, kind=StressKind.REWALK)

    assert row.n == 1
    assert row.dropped == {"funding_missing": 1}
    assert row.funding_indeterminate == 0


# ---- o artefato da T3.62b, reproduzido e fechado ----------------------------


def test_the_first_calendar_half_is_no_longer_empty_when_only_funding_was_missing() -> None:
    """O artefato do §7.2 da T3.62b, em miniatura.

    Quarenta entradas na primeira metade do calendário, **todas** sem ``R_net``
    por ``funding_schedule_unknown``, e quarenta na segunda metade com
    ``R_net``. Antes da queda para ``r_ex_funding`` a primeira metade saía com
    ``n = 0`` e ``no_evaluable_outcomes`` — e o veredito `dependente de metade`
    dizia algo sobre a tabela de funding, não sobre a estratégia.

    Expectancy conferida à mão: a primeira metade é 40 × (+0,10) / 40 = 0,10.
    """
    first = [blind(i, "0.10", day=DAY0 + timedelta(days=i % 20)) for i in range(40)]
    second = [net(i, "0.20", day=DAY0 + timedelta(days=60 + (i % 20))) for i in range(40)]

    early, late = halves([*first, *second])

    assert early.n == 40
    assert early.expectancy_r == Decimal("0.10")
    assert early.axis is StressAxis.R_EX_FUNDING
    assert early.funding_indeterminate == 40
    assert early.metrics.profit_factor_reason == "no_losses"
    assert late.n == 40
    assert late.axis is StressAxis.R_NET


def test_the_verdict_rules_do_not_move_because_the_axis_moved() -> None:
    """A queda de eixo muda o **denominador**, nunca a régua.

    Base com expectancy positiva e as duas metades concordando em sinal → o
    veredito continua ``robusto``; a família e a precedência não são tocadas.
    """
    first = [blind(i, "0.10", day=DAY0 + timedelta(days=i % 20)) for i in range(40)]
    second = [net(i, "0.20", day=DAY0 + timedelta(days=60 + (i % 20))) for i in range(40)]
    pool = [*first, *second]
    rows = [
        aggregate(BASE, pool, family=StressFamily.BASE, kind=StressKind.REWALK),
        *halves(pool),
    ]

    verdict = stress_verdict(rows)

    assert verdict.verdict == "robusto"
    assert verdict.reasons == ()
