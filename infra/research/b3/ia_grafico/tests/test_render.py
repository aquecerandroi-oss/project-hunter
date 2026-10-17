"""O renderizador: determinístico, sem antecipação, sem identificador de período."""

from __future__ import annotations

import struct
import zlib
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from infra.research.b3.ia_grafico.barras import AntecipacaoError, BaldeIncompletoError
from infra.research.b3.ia_grafico.raster import TEXTO_PERMITIDO
from infra.research.b3.ia_grafico.render import (
    ALTURA,
    LARGURA,
    desenhar_janela,
    renderizar,
)
from infra.research.b3.ia_grafico.tests.fabrica import UM_MIN, barra, brt, dois_pregoes

D2 = date(2026, 3, 10)
T = brt(D2, 11, 0)


def _png_dimensoes(png: bytes) -> tuple[int, int]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    largura, altura = struct.unpack(">II", png[16:24])
    return largura, altura


def test_png_valido_tamanho_fixo_e_bytes_identicos_em_duas_chamadas() -> None:
    serie = dois_pregoes()
    a, b = renderizar(serie, T), renderizar(serie, T)
    assert _png_dimensoes(a.png) == (LARGURA, ALTURA)
    assert a.png == b.png and a.sha256_pixels == b.sha256_pixels and a.sha256_png == b.sha256_png
    # IDAT descomprime para altura × (1 + 3·largura) bytes (filtro 0 por linha)
    idat = a.png[33 + 8 : -12]
    assert len(zlib.decompress(idat)) == ALTURA * (1 + 3 * LARGURA)


def test_nenhuma_barra_depois_de_t_chega_a_imagem() -> None:
    """Mudar, apagar ou acrescentar barras depois de t não muda um pixel; mudar a última ≤ t muda."""
    serie = dois_pregoes()
    base = renderizar(serie, T).sha256_pixels

    depois = [b for b in serie if b.fim > T]
    antes = [b for b in serie if b.fim <= T]
    assert depois and antes
    choque = [
        replace(b, maxima=b.maxima * 2, fechamento=b.maxima * 2, volume=Decimal(10**9))
        for b in depois
    ]
    assert renderizar(antes + choque, T).sha256_pixels == base
    assert renderizar(antes, T).sha256_pixels == base
    extra = barra(depois[-1].inicio + UM_MIN, 1, 999_999, 1, 999_999, volume=10**9)
    assert renderizar([*serie, extra], T).sha256_pixels == base

    ultima = antes[-1]
    mexida = replace(ultima, fechamento=ultima.minima, abertura=ultima.maxima)
    assert renderizar([*antes[:-1], mexida], T).sha256_pixels != base


def test_barra_nao_final_e_barra_que_atravessa_t_nao_entram() -> None:
    serie = dois_pregoes()
    base = renderizar(serie, T).sha256_pixels
    parcial = barra(T - timedelta(seconds=30), 1, 999_999, 1, 999_999, volume=10**9)
    nao_final = barra(T - UM_MIN, 1, 999_999, 1, 999_999, final=False)
    assert renderizar([*serie, parcial], T).sha256_pixels == base
    # uma versão "não final" absurda da barra 10:59 ao lado da final não muda um pixel
    assert renderizar([*serie, nao_final], T).sha256_pixels == base
    # e sozinha ela não preenche o minuto: a janela fica indisponível, nunca desenhada
    sem_ultima = [b for b in serie if b.inicio != T - UM_MIN]
    with pytest.raises(BaldeIncompletoError):
        renderizar([*sem_ultima, nao_final], T)


def test_desenhar_janela_recusa_barra_futura_mesmo_se_passada_a_mao() -> None:
    """A trapaça de propósito: um chamador que entrega a janela já com o futuro é pego."""
    serie = dois_pregoes()
    with pytest.raises(AntecipacaoError):
        desenhar_janela(serie, T)


def test_espelho_muda_a_imagem_e_registra_a_referencia() -> None:
    serie = dois_pregoes()
    normal, espelho = renderizar(serie, T), renderizar(serie, T, espelho=True)
    assert normal.sha256_pixels != espelho.sha256_pixels
    assert normal.referencia == espelho.referencia
    assert normal.referencia == [b for b in serie if b.fim <= T][-1].fechamento
    assert espelho.espelho and not normal.espelho


def test_texto_desenhado_nao_carrega_data_nem_preco() -> None:
    g = renderizar(dois_pregoes(), T)
    assert g.textos, "o eixo precisa de rótulos"
    for texto in g.textos:
        assert set(texto) <= TEXTO_PERMITIDO
        assert len(texto.replace(":", "").replace(".", "").lstrip("+-").rstrip("%")) <= 4
    horas = [x for x in g.textos if ":" in x]
    assert "10:00" in horas and all(len(h) == 5 for h in horas)


def test_janela_tem_120_barras_de_5_min_e_separador_de_pregao() -> None:
    g = renderizar(dois_pregoes(), T)
    assert g.n_barras == 120
    # 11:00 do 2.º pregão: 24 barras dele (09:00–11:00) + 96 do 1.º (10:00–18:00)
    assert g.separadores == (96,)


def test_rotulo_de_hora_nunca_sai_cortado_da_tela() -> None:
    """Visto na fumaça: o "10:00" da borda esquerda saía como "0:00"."""
    g = renderizar(dois_pregoes(), T)
    idat = g.png[33 + 8 : -12]
    linhas = zlib.decompress(idat)
    passo = 1 + 3 * LARGURA
    for y in range(606, 626):
        linha = linhas[y * passo + 1 : (y + 1) * passo]
        assert set(linha[:6]) == {255}, f"texto encostado na borda na linha {y}"


def test_cauda_ausente_torna_a_janela_indisponivel() -> None:
    """Sonda da Astra R2: sem barras depois de 11:30, o gráfico das 12:00 não pode sair."""
    serie = [b for b in dois_pregoes() if b.inicio < brt(D2, 11, 30)]
    with pytest.raises(BaldeIncompletoError, match="cauda"):
        renderizar(serie, brt(D2, 12, 0))
