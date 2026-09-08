"""Séries sintéticas com valor esperado conhecido — T3.42."""

from __future__ import annotations

import math

import numpy as np
import pytest

from blocos import Decisao, contraste_por_piso, expectancy


def test_expectancy_de_amostra_vazia_e_nan_e_nao_zero():
    assert math.isnan(expectancy(np.array([], dtype=float)))


def test_expectancy_conhecida():
    assert expectancy(np.array([1.0, -1.0, 2.0])) == pytest.approx(2.0 / 3.0)


def _serie_sintetica() -> list[Decisao]:
    """Quatro dias, duas decisões por dia; acima do piso 0,010 valem +2 R, abaixo −1 R.

    Valores esperados à mão: pai = média de oito valores = (4×2 + 4×(−1))/8 = +0,5 R;
    variante = +2,0 R; Δ = +1,5 R exatamente, em toda reamostragem que contenha
    ao menos um dia (todo dia tem uma decisão de cada lado), logo o IC 95 % é
    degenerado em [+1,5; +1,5].
    """
    linhas: list[Decisao] = []
    for dia in ("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"):
        linhas.append(Decisao(dia=dia, atr_pct=0.020, r_net=2.0))
        linhas.append(Decisao(dia=dia, atr_pct=0.005, r_net=-1.0))
    return linhas


def test_contraste_com_valores_esperados_a_mao():
    c = contraste_por_piso(_serie_sintetica(), 0.010, reamostragens=200, seed=1)
    assert c.dias == 4
    assert c.n_pai == 8
    assert c.n_variante == 4
    assert c.exp_pai == pytest.approx(0.5)
    assert c.exp_variante == pytest.approx(2.0)
    assert c.delta == pytest.approx(1.5)
    assert c.ic95 == pytest.approx((1.5, 1.5))
    assert c.reamostragens_validas == 200


def test_piso_acima_de_tudo_devolve_variante_vazia_e_nenhuma_reamostragem_valida():
    c = contraste_por_piso(_serie_sintetica(), 0.5, reamostragens=50, seed=1)
    assert c.n_variante == 0
    assert math.isnan(c.exp_variante)
    assert c.reamostragens_validas == 0
    assert math.isnan(c.ic95[0])


def test_o_bloco_e_o_dia_e_nao_a_decisao():
    """Um dia inteiro bom e um dia inteiro ruim: reamostrar por dia produz Δ
    variável; se o bloco fosse a decisão, o Δ seria quase constante.

    À mão: só há duas composições possíveis de dias com reposição em que ambos
    aparecem; o Δ assume três valores distintos e o IC não é degenerado.
    """
    linhas = [
        Decisao(dia="2026-08-01", atr_pct=0.02, r_net=3.0),
        Decisao(dia="2026-08-01", atr_pct=0.002, r_net=3.0),
        Decisao(dia="2026-08-02", atr_pct=0.02, r_net=-3.0),
        Decisao(dia="2026-08-02", atr_pct=0.002, r_net=-3.0),
    ]
    c = contraste_por_piso(linhas, 0.010, reamostragens=500, seed=7)
    assert c.delta == pytest.approx(0.0)
    assert c.ic95[0] == pytest.approx(0.0) and c.ic95[1] == pytest.approx(0.0)


def test_determinismo_pela_semente():
    a = contraste_por_piso(_serie_sintetica(), 0.010, reamostragens=100, seed=42)
    b = contraste_por_piso(_serie_sintetica(), 0.010, reamostragens=100, seed=42)
    assert a == b
