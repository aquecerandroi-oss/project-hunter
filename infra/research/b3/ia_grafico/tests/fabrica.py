"""Fábrica de barras SINTÉTICAS de 1 min do "WIN" para os testes do arnês.

Nada aqui é dado de mercado: é um passeio determinístico (semente fixa) em ticks de 5 pontos,
rotulado como fixture de teste. O dado real virá do export do MT5 do Everton.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np

from infra.research.b3.ia_grafico.barras import Barra

UM_MIN = timedelta(minutes=1)
TICK = Decimal(5)


def brt(d: date, hh: int, mm: int) -> datetime:
    """Instante BRT (UTC−3, sem horário de verão desde 2019) em UTC."""
    return datetime(d.year, d.month, d.day, hh + 3, mm, tzinfo=UTC)


def barra(
    inicio: datetime,
    o: int,
    h: int,
    lo: int,
    c: int,
    *,
    volume: int = 100,
    final: bool = True,
) -> Barra:
    return Barra(
        inicio=inicio,
        duracao=UM_MIN,
        abertura=Decimal(o),
        maxima=Decimal(h),
        minima=Decimal(lo),
        fechamento=Decimal(c),
        volume=Decimal(volume),
        final=final,
    )


def pregao(d: date, *, inicio_pts: int = 120_000, semente: int = 7) -> list[Barra]:
    """Um pregão sintético de 09:00 a 18:00 BRT (540 barras de 1 min)."""
    rng = np.random.default_rng(semente)
    passos = rng.integers(-3, 4, size=540)
    barras: list[Barra] = []
    preco = inicio_pts
    t0 = brt(d, 9, 0)
    for i, passo in enumerate(passos):
        o = preco
        c = preco + int(passo) * 5
        h = max(o, c) + 5 * int(rng.integers(0, 3))
        lo = min(o, c) - 5 * int(rng.integers(0, 3))
        barras.append(barra(t0 + i * UM_MIN, o, h, lo, c, volume=50 + int(rng.integers(0, 200))))
        preco = c
    return barras


def dois_pregoes() -> list[Barra]:
    return pregao(date(2026, 3, 9), semente=1) + pregao(
        date(2026, 3, 10), inicio_pts=121_000, semente=2
    )
