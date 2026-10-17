"""O gráfico congelado ``ia_grafico_chart/1`` que a IA recebe no instante *t*.

5 min dobrado de 1 min, 120 barras, eixo Y = 100·ln(p ÷ último fechamento) rotulado em %,
eixo X só com HH:MM (BRT) de hora em hora, separador tracejado entre pregões, volume sem escala.
Sem data, sem preço, sem símbolo (desenho §1.2). ``espelho=True`` desenha y → −y.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from infra.research.b3.ia_grafico.barras import (
    BaldeIncompletoError,
    Barra,
    dobrar,
    exigir_causal,
    janela_causal,
    utc,
)
from infra.research.b3.ia_grafico.raster import Cor, Tela

VERSAO = "ia_grafico_chart/1"
LARGURA, ALTURA = 1024, 640
N_BARRAS, MINUTOS = 120, 5
BRT = ZoneInfo("America/Sao_Paulo")

_X0, _X1 = 8, LARGURA - 84
_PRECO = (10, 470)
_VOLUME = (482, 600)
_ROTULO_HORA_Y = 610
_SLOT = (_X1 - _X0) / N_BARRAS
_PASSOS = (0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)

_FUNDO: Cor = (255, 255, 255)
_ALTA: Cor = (38, 166, 154)
_BAIXA: Cor = (239, 83, 80)
_GRADE: Cor = (228, 228, 228)
_ZERO: Cor = (170, 170, 170)
_TEXTO: Cor = (60, 60, 60)
_VOL: Cor = (160, 160, 160)


class JanelaCurtaError(ValueError):
    """Menos de 120 barras de 5 min antes de *t*: o instante é inelegível (contado antes do retorno)."""


@dataclass(frozen=True, slots=True)
class Grafico:
    versao: str
    t: datetime
    espelho: bool
    png: bytes
    sha256_pixels: str
    sha256_png: str
    referencia: Decimal
    n_barras: int
    separadores: tuple[int, ...]
    textos: tuple[str, ...]
    eixo_pct: tuple[float, float]
    ultima_barra_fim: datetime


def renderizar(barras: Sequence[Barra], t: datetime, *, espelho: bool = False) -> Grafico:
    """Seleciona a janela causal de *t* e desenha. Barras posteriores a *t* nunca chegam ao desenho."""
    return desenhar_janela(janela_causal(barras, t), t, espelho=espelho)


def desenhar_janela(janela: Sequence[Barra], t: datetime, *, espelho: bool = False) -> Grafico:
    t = utc(t, "t")
    exigir_causal(janela, t)
    cinco = dobrar(janela, t, minutos=MINUTOS)[-N_BARRAS:]
    if len(cinco) < N_BARRAS:
        raise JanelaCurtaError(f"{len(cinco)} barras de 5 min antes de {t.isoformat()}")
    if cinco[-1].fim != t:
        raise BaldeIncompletoError(
            f"cauda ausente: a última barra termina em {cinco[-1].fim.isoformat()}, não em t"
        )
    ref = cinco[-1].fechamento
    sinal = -1.0 if espelho else 1.0

    def y(p: Decimal) -> float:
        return sinal * 100.0 * math.log(float(p / ref))

    ohlc = [
        (y(b.abertura), *sorted((y(b.maxima), y(b.minima)), reverse=True), y(b.fechamento))
        for b in cinco
    ]
    baixo = min(v[2] for v in ohlc)
    alto = max(v[1] for v in ohlc)
    meio, faixa = (alto + baixo) / 2, max(alto - baixo, 0.2) * 1.12
    ymin, ymax = meio - faixa / 2, meio + faixa / 2
    topo, base = _PRECO

    def py(v: float) -> int:
        return topo + round((ymax - v) / (ymax - ymin) * (base - topo))

    tela = Tela(LARGURA, ALTURA, _FUNDO)
    textos: list[str] = []
    passo = next(p for p in _PASSOS if (ymax - ymin) / p <= 8)
    for k in range(math.ceil(ymin / passo), math.floor(ymax / passo) + 1):
        nivel = k * passo
        tela.retangulo(_X0, py(nivel), _X1, py(nivel), _ZERO if k == 0 else _GRADE)
        rotulo = "0.00" if k == 0 else f"{nivel:+.2f}"
        tela.texto(_X1 + 6, py(nivel) - 7, rotulo, _TEXTO)
        textos.append(rotulo)

    locais = [b.inicio.astimezone(BRT) for b in cinco]
    separadores = tuple(i for i in range(1, len(cinco)) if locais[i].date() != locais[i - 1].date())
    for i in separadores:
        tela.tracejado_vertical(round(_X0 + i * _SLOT), topo, _VOLUME[1], _ZERO)

    vmax = max(b.volume for b in cinco)
    for i, ((o, h, lo, c), b, loc) in enumerate(zip(ohlc, cinco, locais, strict=True)):
        xc = round(_X0 + (i + 0.5) * _SLOT)
        cor = _ALTA if c >= o else _BAIXA
        tela.retangulo(xc, py(h), xc, py(lo), cor)
        tela.retangulo(xc - 2, py(max(o, c)), xc + 2, py(min(o, c)), cor)
        if vmax > 0:
            altura = round(float(b.volume / vmax) * (_VOLUME[1] - _VOLUME[0]))
            tela.retangulo(xc - 2, _VOLUME[1] - altura, xc + 2, _VOLUME[1], _VOL)
        rotulo = loc.strftime("%H:%M")
        x_rotulo = xc - Tela.largura_texto(rotulo) // 2
        if loc.minute == 0 and x_rotulo >= _X0 and x_rotulo + Tela.largura_texto(rotulo) <= _X1:
            tela.texto(x_rotulo, _ROTULO_HORA_Y, rotulo, _TEXTO)
            textos.append(rotulo)

    png = tela.png()

    return Grafico(
        versao=VERSAO,
        t=t,
        espelho=espelho,
        png=png,
        sha256_pixels=tela.sha256_pixels(),
        sha256_png=hashlib.sha256(png).hexdigest(),
        referencia=ref,
        n_barras=len(cinco),
        separadores=separadores,
        textos=tuple(textos),
        eixo_pct=(ymin, ymax),
        ultima_barra_fim=cinco[-1].fim,
    )
