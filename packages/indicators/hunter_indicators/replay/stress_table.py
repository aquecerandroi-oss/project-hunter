"""A tabela de estresse e o veredito que sai dela — T3.36.

Metade estatística da passada: os cenários e a aritmética dos níveis estão em
:mod:`hunter_indicators.replay.stress`; aqui os desfechos já reprecificados
viram linhas com denominador visível (:mod:`hunter_indicators.replay.metrics`,
as métricas da SHADOW-LAB.md §9) e as linhas viram um veredito.

Duas regras que valem mais que o código:

- **nada vira zero.** Um sinal que o cenário não conseguiu resolver é contado
  por motivo, nunca como "diferença zero" — é a mesma recusa do ``contrast.py``
  do EXP-0004;
- **expectancy positiva e PF > 1 são a mesma afirmação** (``ΣR > 0``), então o
  veredito decide por uma só e a tabela publica as duas. Ler as duas como se
  fossem duas confirmações seria contar a mesma evidência duas vezes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from hunter_indicators.replay.metrics import LabMetrics, lab_metrics
from hunter_indicators.replay.stress import BASE, StressAxis, StressFamily, StressKind

__all__ = [
    "MIN_SAMPLE",
    "StressOutcome",
    "StressRow",
    "StressVerdict",
    "aggregate",
    "halves",
    "leave_one_out",
    "stress_verdict",
]

MIN_SAMPLE: Final = 30
"""Abaixo disto a passada não emite veredito (``amostra_insuficiente``).

Não é número novo: é o mesmo ``BOOTSTRAP_N_MIN`` do bloco 4 da REPLICATION.md
§3.4 e o "mínimo absoluto 30" do `backtest-expert`. Um veredito de robustez
sobre 12 desfechos seria ruído sobre ruído."""


@dataclass(frozen=True, slots=True)
class StressOutcome:
    """Um desfecho já reprecificado, no mínimo que a agregação precisa."""

    signal_id: str
    market: str
    entry_day: date | None
    result: str | None
    r_net: Decimal | None
    dropped: str | None = None
    """Por que este sinal não produziu R avaliável neste cenário — nunca zero."""
    r_ex_funding: Decimal | None = None
    """O mesmo R **sem** a perna de funding (``settle`` grava os dois)."""
    funding_indeterminate: bool = False
    """``True`` só quando ``R_net`` faltou por ``funding_schedule_unknown`` —
    ausência de histórico em ``funding_rates``, não dúvida sobre a operação
    (T3.75; ver :class:`~hunter_indicators.replay.stress.StressAxis`)."""

    @property
    def axis(self) -> StressAxis:
        """Em que R esta linha entra na conta."""
        if self.r_net is None and self.funding_indeterminate and self.r_ex_funding is not None:
            return StressAxis.R_EX_FUNDING
        return StressAxis.R_NET

    @property
    def r(self) -> Decimal | None:
        """O R que esta linha contribui, no eixo que :attr:`axis` declara."""
        return self.r_ex_funding if self.axis is StressAxis.R_EX_FUNDING else self.r_net

    @property
    def evaluable(self) -> bool:
        return self.dropped is None and self.r is not None


@dataclass(frozen=True, slots=True)
class StressRow:
    """Uma linha da tabela de estresse."""

    key: str
    family: StressFamily
    kind: StressKind
    total: int
    metrics: LabMetrics
    dropped: Mapping[str, int]
    axis: StressAxis = StressAxis.R_NET
    """``r_ex_funding`` assim que **uma** linha avaliável tiver caído nele."""
    funding_indeterminate: int = 0
    """Quantas das linhas avaliáveis vieram de ``r_ex_funding`` (T3.75)."""

    @property
    def n(self) -> int:
        """Desfechos avaliáveis — o denominador de tudo nesta linha."""
        return self.metrics.evaluable

    @property
    def expectancy_r(self) -> Decimal | None:
        return self.metrics.expectancy_r

    @property
    def profit_factor(self) -> Decimal | None:
        return self.metrics.profit_factor


def _counted(outcomes: Iterable[StressOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.evaluable:
            continue
        reason = outcome.dropped or "r_net_indisponivel"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def aggregate(
    key: str,
    outcomes: Sequence[StressOutcome],
    *,
    family: StressFamily,
    kind: StressKind = StressKind.REWALK,
) -> StressRow:
    """Uma linha a partir dos desfechos de um cenário."""
    evaluable = [(o.result or "", o.r) for o in outcomes if o.evaluable]
    fallbacks = sum(1 for o in outcomes if o.evaluable and o.axis is StressAxis.R_EX_FUNDING)
    return StressRow(
        key=key,
        family=family,
        kind=kind,
        total=len(outcomes),
        metrics=lab_metrics(evaluable),
        dropped=_counted(outcomes),
        axis=StressAxis.R_EX_FUNDING if fallbacks else StressAxis.R_NET,
        funding_indeterminate=fallbacks,
    )


def leave_one_out(outcomes: Sequence[StressOutcome]) -> list[StressRow]:
    """Uma linha por mercado deixado de fora, em ordem estável de símbolo."""
    markets = sorted({o.market for o in outcomes})
    if len(markets) < 2:
        return []
    return [
        aggregate(
            f"sem_{market}",
            [o for o in outcomes if o.market != market],
            family=StressFamily.MARKET,
            kind=StressKind.SUBSET,
        )
        for market in markets
    ]


def halves(outcomes: Sequence[StressOutcome]) -> list[StressRow]:
    """Primeira e segunda metade da janela, cortadas pelo **meio do calendário**.

    Pelo calendário e não pela mediana dos desfechos: metades com o mesmo número
    de operações teriam durações diferentes, e a pergunta do bloco é se a
    vantagem sobreviveu ao **tempo**, não a uma partição balanceada.
    """
    days = sorted({o.entry_day for o in outcomes if o.entry_day is not None})
    if len(days) < 2:
        return []
    cut = days[0] + timedelta(days=(days[-1] - days[0]).days // 2)
    inside = [o for o in outcomes if o.entry_day is not None]
    return [
        aggregate(
            f"1a_metade_ate_{cut.isoformat()}",
            [o for o in inside if o.entry_day is not None and o.entry_day <= cut],
            family=StressFamily.TIME,
            kind=StressKind.SUBSET,
        ),
        aggregate(
            f"2a_metade_apos_{cut.isoformat()}",
            [o for o in inside if o.entry_day is not None and o.entry_day > cut],
            family=StressFamily.TIME,
            kind=StressKind.SUBSET,
        ),
    ]


@dataclass(frozen=True, slots=True)
class StressVerdict:
    """O veredito e **todos** os motivos, não só o que ganhou a precedência."""

    verdict: str
    reasons: tuple[str, ...]

    @property
    def robust(self) -> bool:
        return self.verdict == "robusto"


def _disagrees(base: Decimal | None, other: Decimal | None) -> bool:
    """Se ``other`` não concorda com o **sinal** da expectancy da base."""
    if base is None or other is None:
        return True
    return (base > 0 >= other) or (base < 0 <= other)


def stress_verdict(rows: Sequence[StressRow]) -> StressVerdict:
    """O veredito da passada, na precedência declarada.

    ``amostra_insuficiente`` e ``sem_vantagem_na_base`` vêm antes de tudo: uma
    tabela de robustez sobre uma base sem vantagem responde a uma pergunta que
    ninguém fez, e chamar de "robusta" uma estratégia de expectancy negativa
    seria a pior leitura possível do mesmo número.
    """
    by_key = {row.key: row for row in rows}
    base = by_key.get(BASE)
    if base is None:
        return StressVerdict("sem_base", ("a linha base não foi calculada",))
    if base.n < MIN_SAMPLE:
        return StressVerdict(
            "amostra_insuficiente", (f"{base.n} desfechos avaliáveis de {MIN_SAMPLE}",)
        )
    if base.expectancy_r is None or base.expectancy_r <= 0:
        return StressVerdict("sem_vantagem_na_base", (f"expectancy da base = {base.expectancy_r}",))
    order = (
        (StressFamily.COSTS, "frágil a custos"),
        (StressFamily.PARAMETERS, "frágil a parâmetros"),
        (StressFamily.MARKET, "dependente de um mercado"),
        (StressFamily.TIME, "dependente de metade"),
    )
    verdict = "robusto"
    reasons: list[str] = []
    for family, label in order:
        broken = [
            row
            for row in rows
            if row.family is family and _disagrees(base.expectancy_r, row.expectancy_r)
        ]
        reasons.extend(
            f"{label}: {row.key} → expectancy {row.expectancy_r} (n={row.n})" for row in broken
        )
        if broken and verdict == "robusto":
            verdict = label
    return StressVerdict(verdict, tuple(reasons))
