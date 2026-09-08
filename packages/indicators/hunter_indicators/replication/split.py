"""Metades de mercado — bloco 3 do protocolo (`docs/plans/REPLICATION.md` §3.3).

Os mercados que produziram resultados avaliáveis são partidos em duas metades
por hash determinístico do símbolo, e as duas precisam ter expectancy positiva.
Computação pura sobre o que já existe: **nenhuma coorte nova**, nenhum sinal
novo, custo zero para o worker.

Duas escolhas que valem estar escritas:

- **``sha256``, nunca ``hash()``.** O ``hash()`` do Python é salgado por processo:
  a mesma população cairia em metades diferentes a cada reinício, e um bloco de
  validação que muda de resposta sozinho não valida nada.
- **A partição não sabe nada sobre desempenho.** "As dez maiores contra as dez
  menores", ou qualquer corte escolhido olhando o resultado, é a mesma pesquisa
  disfarçada de validação (KB-0003, KB-0010).

As metades quase nunca saem do mesmo tamanho, e isso é esperado: o hash é
imparcial, não equilibrado. Por isso cada metade tem a sua própria maturidade.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_indicators.replication.stats import PopulationStats

if TYPE_CHECKING:
    from hunter_indicators.replication.stats import Outcome

__all__ = [
    "HALF_A",
    "HALF_B",
    "MIN_MARKETS_PER_HALF",
    "MIN_OUTCOMES_PER_HALF",
    "HalfStats",
    "HalvesResult",
    "market_half",
    "split_by_market",
]

HALF_A = "a"
HALF_B = "b"

MIN_MARKETS_PER_HALF = 3
"""``METADES_MIN_MERCADOS``: com um ou dois mercados a "metade" é um mercado com
outro nome, e a conclusão seria sobre ele, não sobre a estratégia."""

MIN_OUTCOMES_PER_HALF = 20
"""``METADES_MIN_RESULTADOS`` por metade."""


def market_half(market: str) -> str:
    """``a`` ou ``b`` — bit menos significativo do primeiro byte do sha256.

    Estável entre processos, versões e máquinas: é o que permite comparar o
    relatório de hoje com o de daqui a um mês.
    """
    digest = hashlib.sha256(market.encode("utf-8")).digest()
    return HALF_A if digest[0] & 1 == 0 else HALF_B


@dataclass(frozen=True, slots=True)
class HalfStats:
    """Uma metade: quantos mercados, quantos resultados, que expectancy."""

    half: str
    markets: int
    evaluable: int
    expectancy_r: Decimal | None
    mature: bool
    reason: str | None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "half": self.half,
            "markets": self.markets,
            "evaluable": self.evaluable,
            "expectancy_r": None if self.expectancy_r is None else str(self.expectancy_r),
            "mature": self.mature,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class HalvesResult:
    """As duas metades e o veredito do bloco."""

    a: HalfStats
    b: HalfStats
    passed: bool | None
    """``True`` as duas positivas; ``False`` alguma metade **madura** negativa;
    ``None`` alguma metade imatura — imaturidade nunca refuta."""

    reason: str | None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "a": self.a.to_jsonable(),
            "b": self.b.to_jsonable(),
            "passed": self.passed,
            "reason": self.reason,
        }


def _half_stats(half: str, outcomes: Sequence[Outcome]) -> HalfStats:
    stats = PopulationStats.of(outcomes)
    markets = stats.markets
    mature = markets >= MIN_MARKETS_PER_HALF and stats.evaluable >= MIN_OUTCOMES_PER_HALF
    reason = None
    if not mature:
        reason = (
            f"imatura: {markets} de {MIN_MARKETS_PER_HALF} mercados, "
            f"{stats.evaluable} de {MIN_OUTCOMES_PER_HALF} resultados"
        )
    return HalfStats(
        half=half,
        markets=markets,
        evaluable=stats.evaluable,
        expectancy_r=stats.expectancy_r,
        mature=mature,
        reason=reason,
    )


def split_by_market(outcomes: Iterable[Outcome]) -> HalvesResult:
    """Parte a população em duas metades e diz se o bloco passa, falha ou espera."""
    buckets: dict[str, list[Outcome]] = {HALF_A: [], HALF_B: []}
    for outcome in outcomes:
        buckets[market_half(outcome.market)].append(outcome)
    a = _half_stats(HALF_A, buckets[HALF_A])
    b = _half_stats(HALF_B, buckets[HALF_B])
    for half in (a, b):
        if half.mature and half.expectancy_r is not None and half.expectancy_r <= 0:
            return HalvesResult(a, b, False, f"metade_{half.half}_negativa")
    if not (a.mature and b.mature):
        immature = HALF_A if not a.mature else HALF_B
        return HalvesResult(a, b, None, f"metade_{immature}_imatura")
    return HalvesResult(a, b, True, None)
