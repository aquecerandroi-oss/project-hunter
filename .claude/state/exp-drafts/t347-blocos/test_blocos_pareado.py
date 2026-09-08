"""Séries sintéticas com o valor esperado calculado à mão — T3.47.

Escritas antes de ``blocos_pareado.py`` existir. Cada caso responde a uma
pergunta que a nota faz do estimador:

1. Δ constante  -> o intervalo colapsa no próprio Δ (nada a reamostrar).
2. o bloco é o **dia**, não a decisão -> com um único dia o intervalo é
   degenerado mesmo com Δ diferentes dentro dele.
3. dias com mais decisões pesam mais (concatenação, não média de médias).
4. o suporte da reamostragem é exatamente o conjunto das combinações de dias.
5. a semente fixa o resultado.
6. população vazia devolve ``nan``, nunca 0,0.
"""

from __future__ import annotations

import math

import pytest

from blocos_pareado import Par, bootstrap_pareado


def _pares(linhas: list[tuple[str, float]]) -> list[Par]:
    return [Par(rotulo="X", dia=dia, delta=delta) for dia, delta in linhas]


def test_delta_constante_colapsa_o_intervalo() -> None:
    pares = _pares([("d1", 1.5), ("d1", 1.5), ("d2", 1.5), ("d3", 1.5), ("d4", 1.5)])
    c = bootstrap_pareado(pares, reamostragens=200)
    assert c.pares == 5
    assert c.dias == 4
    assert c.delta == pytest.approx(1.5)
    assert c.ic95 == pytest.approx((1.5, 1.5))
    assert c.reamostragens_validas == 200


def test_o_bloco_e_o_dia_nao_a_decisao() -> None:
    # um único dia com Δ muito diferentes: média +1,0 e intervalo degenerado,
    # porque toda reamostragem de dias devolve o mesmo dia inteiro.
    pares = _pares([("d1", 3.0), ("d1", -1.0)])
    c = bootstrap_pareado(pares, reamostragens=100)
    assert c.dias == 1
    assert c.delta == pytest.approx(1.0)
    assert c.ic95 == pytest.approx((1.0, 1.0))


def test_dia_com_mais_decisoes_pesa_mais() -> None:
    # 3 decisões de +1 num dia e 1 de −3 no outro: média da população = 0,0
    # (a média das médias diárias seria (1 + (−3))/2 = −1,0 — não é isto que medimos).
    pares = _pares([("d1", 1.0), ("d1", 1.0), ("d1", 1.0), ("d2", -3.0)])
    c = bootstrap_pareado(pares, reamostragens=500)
    assert c.delta == pytest.approx(0.0)


def test_suporte_da_reamostragem_e_o_conjunto_de_combinacoes_de_dias() -> None:
    # d1 = [+2, +2], d2 = [−1]. Δ da população = (2+2−1)/3 = +1,0.
    # As quatro reamostragens possíveis de dois dias com reposição:
    #   d1,d1 -> (2+2+2+2)/4 = +2,0     d1,d2 -> (2+2−1)/3 = +1,0
    #   d2,d1 -> +1,0                    d2,d2 -> (−1−1)/2 = −1,0
    pares = _pares([("d1", 2.0), ("d1", 2.0), ("d2", -1.0)])
    c = bootstrap_pareado(pares, reamostragens=2000)
    assert c.delta == pytest.approx(1.0)
    assert set(round(x, 6) for x in c.amostras) == {2.0, 1.0, -1.0}
    assert c.ic95[0] == pytest.approx(-1.0)
    assert c.ic95[1] == pytest.approx(2.0)


def test_semente_fixa_o_resultado() -> None:
    pares = _pares([("d1", 2.0), ("d1", -1.0), ("d2", 0.5), ("d3", -2.0)])
    a = bootstrap_pareado(pares, reamostragens=300, seed=7)
    b = bootstrap_pareado(pares, reamostragens=300, seed=7)
    d = bootstrap_pareado(pares, reamostragens=300, seed=8)
    assert (a.amostras == b.amostras).all()
    # com tres dias o IC percentil satura nos extremos e nao distingue sementes;
    # o que a semente fixa e a sequencia inteira de reamostragens.
    assert not (a.amostras == d.amostras).all()
    assert a.ic95 == b.ic95


def test_populacao_vazia_devolve_nan_nunca_zero() -> None:
    c = bootstrap_pareado([], reamostragens=10)
    assert c.pares == 0 and c.dias == 0
    assert math.isnan(c.delta)
    assert math.isnan(c.ic95[0]) and math.isnan(c.ic95[1])
    assert c.reamostragens_validas == 0
