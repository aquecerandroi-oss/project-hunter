"""Testes do segundo conjunto (definições da KB-0080 §7) — T3.55b.

Mesmas séries sintéticas de ATR exatamente 10. O que muda é a régua de contexto
(EMA10 com inclinação, no lugar da variação em ATR), e é justamente ela que os
dois primeiros testes fixam.
"""

from __future__ import annotations

from decimal import Decimal

import padroes_kb0080 as kb
import pytest
from series import atr, barra, prefixo
from test_padroes import serie_aleatoria


def montar(passo: int, extras: list):
    bars = prefixo(passo)
    bars.extend(extras)
    return bars, atr(bars), kb.ema10(bars)


def nomes(achados) -> set[str]:
    return {d.nome for d in achados}


def um(achados, nome):
    escolhidos = [d for d in achados if d.nome == nome]
    assert len(escolhidos) == 1, f"esperava um {nome}, veio {nomes(achados)}"
    return escolhidos[0]


def test_a_ema10_semeia_na_media_simples() -> None:
    """A semente é uma escolha declarada, não um detalhe: fixá-la é o teste."""
    bars = prefixo(-2)
    ema = kb.ema10(bars)
    assert ema[8] is None
    assert ema[9] == Decimal("991")  # media de 1000, 998, ..., 982


def test_o_contexto_e_preco_abaixo_da_ema_com_ema_caindo() -> None:
    bars = prefixo(-2)
    ema = kb.ema10(bars)
    assert kb.contexto(bars, ema, 20) == "baixa"
    subindo = prefixo(+2)
    assert kb.contexto(subindo, kb.ema10(subindo), 20) == "alta"
    parado = prefixo(0)
    assert kb.contexto(parado, kb.ema10(parado), 20) == "lateral"


def test_martelo_da_kb0080() -> None:
    bars, a, ema = montar(-2, [barra(20, "964", "964.5", "955", "963")])
    m = um(kb.detectar(bars, a, ema, 20), "a_martelo")
    assert m.stop == Decimal("955")
    assert m.stop_atr == Decimal("0.8")


def test_a_amplitude_minima_da_kb0080_e_maior_e_isso_muda_o_resultado() -> None:
    """Uma barra de 0,6 ATR é martelo em `padroes_v1` (>= 0,5) e não é aqui (>= 0,8)."""
    import padroes

    extra = [barra(20, "963.5", "964", "958", "963")]  # amp = 6 = 0,6 ATR
    bars, a, ema = montar(-2, extra)
    assert "martelo" in {d.nome for d in padroes.detectar(bars, a, 20)}
    assert "a_martelo" not in nomes(kb.detectar(bars, a, ema, 20))


def test_martelo_invertido_existe_so_no_conjunto_da_kb0080() -> None:
    bars, a, ema = montar(-2, [barra(20, "963", "973", "962.5", "964")])
    m = um(kb.detectar(bars, a, ema, 20), "a_martelo_invertido")
    assert m.direcao == "long"
    assert m.stop == Decimal("962.5")


def test_marubozu_da_kb0080_invalida_na_abertura() -> None:
    bars, a, ema = montar(-2, [barra(20, "962", "972.2", "961.8", "972")])
    m = um(kb.detectar(bars, a, ema, 20), "a_marubozu_alta")
    assert m.stop == Decimal("962")  # a abertura, nao a minima
    assert m.stop_atr == Decimal("1")


def test_harami_da_kb0080_exige_corpo_estritamente_dentro() -> None:
    dentro = [barra(20, "968", "969", "955", "956"), barra(21, "959", "963", "958", "962")]
    bars, a, ema = montar(-2, dentro)
    h = um(kb.detectar(bars, a, ema, 21), "a_harami_alta")
    assert h.stop == Decimal("955")  # so a minima da MAE, nao o minimo das duas
    encostado = [barra(20, "968", "969", "955", "956"), barra(21, "956", "963", "955", "962")]
    bars, a, ema = montar(-2, encostado)
    assert "a_harami_alta" not in nomes(kb.detectar(bars, a, ema, 21))


def test_tres_dentro_para_cima() -> None:
    bars, a, ema = montar(
        -2,
        [
            barra(20, "968", "969", "955", "956"),
            barra(21, "959", "963", "958", "962"),
            barra(22, "962", "970", "961", "969"),
        ],
    )
    t = um(kb.detectar(bars, a, ema, 22), "a_tres_dentro_alta")
    assert t.barras == 3
    assert t.stop == Decimal("955")


def test_um_padrao_da_kb0080_nao_muda_quando_o_futuro_muda() -> None:
    bars = serie_aleatoria()
    a, ema = atr(bars), kb.ema10(bars)
    for i in range(30, len(bars) - 1):
        alterada = list(bars)
        alterada[i + 1] = barra(i + 1, "9000", "9500", "8500", "8600")
        assert kb.detectar(alterada, atr(alterada), kb.ema10(alterada), i) == kb.detectar(
            bars, a, ema, i
        )


def test_o_corte_por_prefixo_e_o_corte_por_indice_sao_o_mesmo() -> None:
    """A EMA é recursiva e semeada no índice 9: cortar a série não pode movê-la."""
    bars = serie_aleatoria()
    a, ema = atr(bars), kb.ema10(bars)
    for i in range(30, len(bars)):
        p = bars[: i + 1]
        assert kb.detectar(p, atr(p), kb.ema10(p), i) == kb.detectar(bars, a, ema, i)


def test_a_serie_aleatoria_produz_ocorrencias_suficientes() -> None:
    bars = serie_aleatoria()
    assert len(kb.varrer(bars, atr(bars))) >= 10


@pytest.mark.parametrize("nome", kb.NOMES)
def test_todo_rotulo_tem_direcao_declarada(nome: str) -> None:
    assert kb.DIRECAO[nome] in {"long", "short"}
    assert kb.SINAL[nome] in {1, -1}
