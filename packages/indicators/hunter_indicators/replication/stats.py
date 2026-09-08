"""População avaliável, maturidade e o veredito do placar — as definições que o
resto do protocolo reusa (`docs/plans/REPLICATION.md` §1 e §2).

Um nome por conta, com o denominador junto (item 9 da decisão conjunta e a regra
5 do plantão): *expectancy líquida hipotética em R por entrada encerrada
avaliável* não é *taxa de lucro líquido*, e *profit factor* é **nulo com motivo**
quando um dos lados do quociente é vazio — nunca infinito, nunca zero inventado.

Só ``Decimal`` aqui: são os R que a tela mostra e que o placar persiste. A
estatística em ``float`` mora em :mod:`~hunter_indicators.replication.bootstrap`,
e a fronteira entre as duas é explícita de propósito.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

__all__ = [
    "EXPECTANCY_MIN",
    "MATURITY_DAYS",
    "MATURITY_HALF_DAYS",
    "MATURITY_HALF_OUTCOMES",
    "MATURITY_OUTCOMES",
    "PROFIT_FACTOR_MIN",
    "VERDICT_INCONCLUSIVE",
    "VERDICT_REJECTED",
    "VERDICT_VALIDATED",
    "Outcome",
    "PopulationStats",
    "after",
    "scoreboard_verdict",
]

MATURITY_OUTCOMES = 100
"""``MATURIDADE_RESULTADOS`` — régua cheia do placar (SHADOW-LAB.md §9)."""

MATURITY_DAYS = 30
"""``MATURIDADE_DIAS`` — régua cheia do placar."""

MATURITY_HALF_OUTCOMES = 50
"""``MATURIDADE_META_RESULTADOS`` — meia-régua dos blocos 1 e 2 (REPLICATION.md §1.5)."""

MATURITY_HALF_DAYS = 15
"""``MATURIDADE_META_DIAS`` — meia-régua dos blocos 1 e 2."""

EXPECTANCY_MIN = Decimal("0")
"""Desigualdade **estrita**: empate não passa."""

PROFIT_FACTOR_MIN = Decimal("1")
"""Idem."""

VERDICT_INCONCLUSIVE = "inconclusivo"
VERDICT_VALIDATED = "validada"
VERDICT_REJECTED = "reprovada"

_FOUR = Decimal("0.0001")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_FOUR, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Outcome:
    """Um resultado **avaliável**: R líquido, instante da decisão e mercado.

    Quem constrói esta lista já aplicou o filtro de avaliabilidade
    (``tracking_state = 'terminal'`` e ``r_multiple IS NOT NULL``); aqui dentro
    não existe outcome pendente, sem entrada ou censurado — o que entra conta.
    """

    r: Decimal
    decision_at: datetime
    market: str

    @property
    def day(self) -> date:
        """Dia UTC da **decisão** (``agent_signals.emitted_at``), não da saída."""
        return self.decision_at.date()


@dataclass(frozen=True, slots=True)
class PopulationStats:
    """As contas de uma população avaliável, todas com denominador declarado."""

    evaluable: int
    days: int
    markets: int
    expectancy_r: Decimal | None
    profit_factor: Decimal | None
    profit_factor_reason: str | None
    sum_r: Decimal | None
    wins: int
    losses: int

    @classmethod
    def of(cls, outcomes: Iterable[Outcome]) -> PopulationStats:
        rows = list(outcomes)
        if not rows:
            return cls(0, 0, 0, None, None, "sem_amostra", None, 0, 0)
        values = [row.r for row in rows]
        gains = sum((value for value in values if value > 0), Decimal(0))
        drops = sum((value for value in values if value < 0), Decimal(0))
        wins = sum(1 for value in values if value > 0)
        losses = sum(1 for value in values if value < 0)
        total = sum(values, Decimal(0))
        if losses == 0:
            factor, reason = None, "sem_perdas"
        elif wins == 0:
            factor, reason = None, "sem_ganhos"
        else:
            factor, reason = _quantize(gains / -drops), None
        return cls(
            evaluable=len(rows),
            days=len({row.day for row in rows}),
            markets=len({row.market for row in rows}),
            expectancy_r=_quantize(total / len(rows)),
            profit_factor=factor,
            profit_factor_reason=reason,
            sum_r=_quantize(total),
            wins=wins,
            losses=losses,
        )

    def mature(self, *, outcomes: int = MATURITY_OUTCOMES, days: int = MATURITY_DAYS) -> bool:
        """Régua **E**, nunca **OU**: 300 resultados em 3 dias não é maturidade."""
        return self.evaluable >= outcomes and self.days >= days

    def positive(self) -> bool:
        return self.expectancy_r is not None and self.expectancy_r > EXPECTANCY_MIN

    def shortfall(self, *, outcomes: int, days: int) -> str:
        """ "38 de 50 resultados · 9 de 15 dias" — o que falta, sempre visível."""
        return f"{self.evaluable} de {outcomes} resultados · {self.days} de {days} dias"

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "evaluable": self.evaluable,
            "days": self.days,
            "markets": self.markets,
            "expectancy_r": None if self.expectancy_r is None else str(self.expectancy_r),
            "profit_factor": None if self.profit_factor is None else str(self.profit_factor),
            "profit_factor_reason": self.profit_factor_reason,
            "sum_r": None if self.sum_r is None else str(self.sum_r),
            "wins": self.wins,
            "losses": self.losses,
        }


def scoreboard_verdict(stats: PopulationStats) -> str:
    """O veredito do placar (T3.18), reimplementado aqui como função pura.

    ``inconclusivo`` enquanto imaturo; depois ``validada`` sse
    ``expectancy_r > 0`` **e** ``profit_factor > 1``; senão ``reprovada``. Um PF
    nulo (um dos lados vazio) **não** é maior que 1: uma versão sem uma única
    perda em 100 resultados é um instrumento a conferir, não uma aprovação.
    """
    if not stats.mature():
        return VERDICT_INCONCLUSIVE
    if not stats.positive():
        return VERDICT_REJECTED
    if stats.profit_factor is None or stats.profit_factor <= PROFIT_FACTOR_MIN:
        return VERDICT_REJECTED
    return VERDICT_VALIDATED


def after(outcomes: Sequence[Outcome], moment: datetime) -> list[Outcome]:
    """Só o que foi decidido **depois** de ``moment`` — a fronteira do bloco 1.

    Estritamente maior: a decisão que aconteceu no mesmo instante em que a versão
    virou promissora ainda pertence à amostra que a tornou promissora.
    """
    return [outcome for outcome in outcomes if outcome.decision_at > moment]
