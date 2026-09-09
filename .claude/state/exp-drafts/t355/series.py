"""Construtores de série sintética com ATR **exatamente** conhecido — T3.55b.

Toda barra do prefixo tem `TR = 10` por construção (`H-L = 10`, e o fechamento
anterior fica sempre dentro da faixa), então o ATR de Wilder da série é 10 na
casa exata assim que o aquecimento termina. Isso permite escrever os valores
esperados dos testes à mão, em vez de carimbar o que o código devolveu.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

for _pacote in (
    "C:/dev/project-hunter/packages/core",
    "C:/dev/project-hunter/packages/indicators",
):
    if _pacote not in sys.path:
        sys.path.insert(0, _pacote)

from hunter_core.domain.enums import Timeframe  # noqa: E402
from hunter_core.strategies.aggregate import Bar  # noqa: E402
from hunter_indicators.patterns.scale import atr_series  # noqa: E402

T0 = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
PASSO = timedelta(minutes=15)
TF = Timeframe.M15
ATR_PREFIXO = Decimal("10")


def barra(k: int, o: str, h: str, low: str, c: str) -> Bar:
    inicio = T0 + PASSO * k
    return Bar(
        open_time=inicio,
        close_time=inicio + PASSO,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1"),
    )


def prefixo(passo: int, n: int = 20, base: str = "1000") -> list[Bar]:
    """``n`` barras de ``TR = 10`` andando ``passo`` por barra (negativo = queda)."""
    saida: list[Bar] = []
    inicial = Decimal(base)
    for k in range(n):
        preco = inicial + Decimal(passo) * k
        saida.append(barra(k, str(preco), str(preco + 5), str(preco - 5), str(preco)))
    return saida


def atr(bars: list[Bar]) -> list[Decimal | None]:
    return list(atr_series(bars, timeframe=TF))
