"""Séries sintéticas com valor esperado conhecido para os testes de replicação.

Dado rotulado como teste (CLAUDE.md): nada aqui sai de ``tests/``. A construção
é deliberadamente aritmética — quem lê o teste consegue calcular a expectancy no
papel antes de rodar.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_indicators.replication import Outcome

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
"""Âncora fixa: todo teste conta dias a partir daqui."""

HALF_A_MARKETS = ("ETHUSDT", "SOLUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT", "TONUSDT")
HALF_B_MARKETS = ("BTCUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT")
"""Metades reais de ``market_half`` (sha256), fixadas aqui para os testes lerem
como tabela em vez de recalcular o hash."""

MARKETS = HALF_A_MARKETS + HALF_B_MARKETS


def population(
    *,
    days: int,
    per_day: int,
    markets: Sequence[str] = MARKETS,
    r_for: Callable[[str, int], Decimal],
    start: datetime = START,
) -> list[Outcome]:
    """``days × per_day`` resultados, um mercado por vez, em rodízio."""
    rows: list[Outcome] = []
    index = 0
    for day in range(days):
        for slot in range(per_day):
            market = markets[index % len(markets)]
            rows.append(
                Outcome(
                    r=r_for(market, index),
                    decision_at=start + timedelta(days=day, minutes=slot * 7),
                    market=market,
                )
            )
            index += 1
    return rows


def alternating(pattern: Sequence[str]) -> Callable[[str, int], Decimal]:
    """R em ciclo fixo: ``["1", "1", "1", "-0.5", "-0.5"]`` = 0,4 de expectancy."""
    values = [Decimal(item) for item in pattern]
    return lambda _market, index: values[index % len(values)]


def by_half(half_a: Sequence[str], half_b: Sequence[str]) -> Callable[[str, int], Decimal]:
    """Um ciclo de R para cada metade de mercado — o bloco 3 sob controle."""
    values_a = [Decimal(item) for item in half_a]
    values_b = [Decimal(item) for item in half_b]

    def choose(market: str, index: int) -> Decimal:
        if market in HALF_A_MARKETS:
            return values_a[index % len(values_a)]
        return values_b[index % len(values_b)]

    return choose
