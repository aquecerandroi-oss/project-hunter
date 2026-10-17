"""O que a IA tem de vencer, e a ponte da resposta para a ordem.

- ``distancia_direcional``: stop = alvo = 2 × ATR(14) das barras de 5 min **da janela** (causal),
  teto ao tick — a geometria do braço direcional, simétrica e independente do lado escolhido
  (Astra R1: com geometria da IA dependente do lado o "acaso exato" dá D > 0 sem ler nada).
- ``lado_media_movel``: fechamento contra a média dos últimos 20 fechamentos de 5 min.
- ``ordem_da_resposta``: níveis do eixo (100·ln(p ÷ ref)) para pontos, arredondados ao tick para
  o lado conservador (stop para longe, alvo e limite para o lado mais difícil).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from infra.research.b3.ia_grafico.barras import Barra
from infra.research.b3.ia_grafico.protocolo import ATR_BARRAS, ATR_MULTIPLO, TICK
from infra.research.b3.ia_grafico.resposta import Lado, Resposta
from infra.research.b3.ia_grafico.simulador import Ordem


def ao_tick(valor: Decimal, *, para_cima: bool) -> Decimal:
    passos = (valor / TICK).to_integral_value(ROUND_CEILING if para_cima else ROUND_FLOOR)
    return passos * TICK


def atr(barras: Sequence[Barra], n: int = ATR_BARRAS) -> Decimal:
    if len(barras) < n + 1:
        raise ValueError(f"ATR({n}) precisa de {n + 1} barras, veio {len(barras)}")
    janela = barras[-(n + 1) :]
    trs = [
        max(b.maxima - b.minima, abs(b.maxima - a.fechamento), abs(b.minima - a.fechamento))
        for a, b in zip(janela, janela[1:], strict=False)
    ]
    return sum(trs, Decimal(0)) / n


def distancia_direcional(barras: Sequence[Barra], n: int = ATR_BARRAS) -> Decimal:
    return max(ao_tick(ATR_MULTIPLO * atr(barras, n), para_cima=True), TICK)


def lado_media_movel(barras: Sequence[Barra], n: int = 20) -> Lado:
    if len(barras) < n:
        raise ValueError(f"média de {n} precisa de {n} barras")
    fechamentos = [b.fechamento for b in barras[-n:]]
    media = sum(fechamentos, Decimal(0)) / n
    ultimo = fechamentos[-1]
    if ultimo > media:
        return Lado.COMPRA
    if ultimo < media:
        return Lado.VENDA
    return Lado.NENHUM


def _preco(ref: Decimal, y: float) -> Decimal:
    return ref * Decimal(repr(math.exp(y / 100.0)))


def ordem_da_resposta(r: Resposta, ref: Decimal) -> Ordem:
    if r.lado is Lado.NENHUM or r.stop_y is None or r.alvo_y is None or r.tipo_entrada is None:
        raise ValueError("resposta none não vira ordem")
    compra = r.lado is Lado.COMPRA
    stop = ao_tick(_preco(ref, r.stop_y), para_cima=not compra)
    alvo = ao_tick(_preco(ref, r.alvo_y), para_cima=compra)
    limite = None
    if r.entrada_y is not None:
        limite = ao_tick(_preco(ref, r.entrada_y), para_cima=not compra)
    return Ordem(lado=r.lado, tipo=r.tipo_entrada, stop=stop, alvo=alvo, limite=limite)
