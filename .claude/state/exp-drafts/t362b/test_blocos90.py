"""Séries sintéticas com valor esperado calculado à mão — T3.62b.

Cada teste tem o número esperado escrito antes do `assert`, e o motivo dele. Um
teste de bootstrap que só verifica "roda sem erro" é decoração.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from blocos90 import (
    Intervalo,
    delta_nao_pareado,
    delta_pareado_por_dia,
    ic_media,
    media,
    profit_factor,
)


# --------------------------------------------------------------- média e PF


def test_media_de_amostra_vazia_e_nan_e_nao_zero():
    assert math.isnan(media(np.array([], dtype=float)))


def test_media_conhecida():
    assert media(np.array([1.0, -1.0, 3.0])) == pytest.approx(1.0)


def test_profit_factor_conhecido():
    # ganhos 2+1 = 3; perdas 1+0,5 = 1,5; PF = 2,0 exatamente.
    assert profit_factor(np.array([2.0, 1.0, -1.0, -0.5])) == pytest.approx(2.0)


def test_profit_factor_sem_perda_e_infinito_e_sem_amostra_e_nan():
    assert profit_factor(np.array([1.0, 2.0])) == math.inf
    assert math.isnan(profit_factor(np.array([], dtype=float)))


# ------------------------------------------------------------------ ic_media


def test_ic_de_um_unico_dia_e_degenerado():
    """Com um dia só, toda reamostragem é o mesmo dia: o IC colapsa na média.

    Valores [1, −1, 3] → média = 1,0; IC = [1,0; 1,0].
    """
    r = ic_media(["2026-06-12"] * 3, np.array([1.0, -1.0, 3.0]), reamostragens=200, seed=1)
    assert r == Intervalo(n=3, dias=1, media=1.0, ic95=(1.0, 1.0), reamostragens=200)


def test_ic_de_dois_dias_opostos_tem_extremos_exatos():
    """Dia A = duas decisões +2; dia B = duas decisões −2. Média = 0.

    Reamostrando 2 dias com reposição há três resultados possíveis:
    AA → +2 (p = 1/4), AB ou BA → 0 (p = 1/2), BB → −2 (p = 1/4). O percentil
    2,5 % é −2,0 e o 97,5 % é +2,0 — exatos, não aproximados.
    """
    dias = ["A", "A", "B", "B"]
    r = ic_media(dias, np.array([2.0, 2.0, -2.0, -2.0]), reamostragens=4000, seed=3)
    assert r.dias == 2
    assert r.media == pytest.approx(0.0)
    assert r.ic95 == pytest.approx((-2.0, 2.0))


def test_o_bloco_e_o_dia_e_nao_a_decisao():
    """Vinte decisões, +1 num dia e −1 no outro.

    Por decisão (i.i.d.) o IC da média seria estreito, ~±0,45 com n = 20. Por dia
    inteiro, o IC vai de −1 a +1: dez vezes mais largo. É essa diferença que a
    escolha do bloco compra, e é por isso que ela não é cosmética.
    """
    dias = ["A"] * 10 + ["B"] * 10
    valores = np.array([1.0] * 10 + [-1.0] * 10)
    por_dia = ic_media(dias, valores, reamostragens=4000, seed=5)
    assert por_dia.ic95 == pytest.approx((-1.0, 1.0))

    iid = ic_media([f"d{i}" for i in range(20)], valores, reamostragens=4000, seed=5)
    largura_iid = iid.ic95[1] - iid.ic95[0]
    assert largura_iid < 1.0  # medido ~0,90 — menos da metade da largura por dia
    assert (por_dia.ic95[1] - por_dia.ic95[0]) > 2 * largura_iid


def test_ic_media_e_deterministico_pela_semente():
    dias = ["A", "A", "B", "C"]
    v = np.array([1.0, 2.0, -1.0, 0.5])
    assert ic_media(dias, v, reamostragens=300, seed=42) == ic_media(
        dias, v, reamostragens=300, seed=42
    )


def test_amostra_vazia_devolve_nan_e_nao_explode():
    r = ic_media([], np.array([], dtype=float), reamostragens=10, seed=1)
    assert r.n == 0 and r.dias == 0 and math.isnan(r.media) and math.isnan(r.ic95[0])


# ------------------------------------------------------------ delta não pareado


def test_delta_nao_pareado_entre_janelas_de_um_dia_cada():
    """A = um dia com [+1]; B = um dia com [−1]. Δ = +2, IC degenerado [2, 2]."""
    d = delta_nao_pareado(["A"], np.array([1.0]), ["B"], np.array([-1.0]), reamostragens=100, seed=1)
    assert d.media_a == pytest.approx(1.0)
    assert d.media_b == pytest.approx(-1.0)
    assert d.delta == pytest.approx(2.0)
    assert d.ic95 == pytest.approx((2.0, 2.0))


def test_delta_nao_pareado_e_a_diferenca_das_medias():
    """A = [2, 4] em dois dias (média 3); B = [0, 2] em dois dias (média 1); Δ = 2."""
    d = delta_nao_pareado(
        ["A1", "A2"], np.array([2.0, 4.0]), ["B1", "B2"], np.array([0.0, 2.0]),
        reamostragens=500, seed=9,
    )
    assert d.delta == pytest.approx(2.0)
    assert d.ic95[0] <= 2.0 <= d.ic95[1]


# -------------------------------------------------------------- delta pareado


def test_delta_pareado_com_valor_esperado_a_mao():
    """Quatro dias, uma decisão de cada grupo por dia: A vale +2, B vale −1.

    Δ = +3,0 em toda reamostragem que contenha ao menos um dia — e todo dia tem
    os dois grupos —, logo o IC 95 % é degenerado em [+3; +3].
    """
    dias, valores, ga = [], [], []
    for dia in ("2026-06-12", "2026-06-13", "2026-06-14", "2026-06-15"):
        dias += [dia, dia]
        valores += [2.0, -1.0]
        ga += [True, False]
    d = delta_pareado_por_dia(dias, np.array(valores), np.array(ga), reamostragens=300, seed=2)
    assert d.n_a == 4 and d.n_b == 4
    assert d.delta == pytest.approx(3.0)
    assert d.ic95 == pytest.approx((3.0, 3.0))
    assert d.reamostragens_validas == 300


def test_delta_pareado_descarta_reamostragem_sem_um_dos_lados_e_diz_quantas():
    """Dia A só tem grupo A; dia B só tem grupo B.

    Das quatro composições equiprováveis de dois dias, AA e BB deixam um lado
    vazio e são descartadas: ~50 % das reamostragens sobrevivem. O contrato é que
    o número que sobrou seja devolvido, e não escondido.
    """
    dias = ["A", "B"]
    d = delta_pareado_por_dia(
        dias, np.array([1.0, -1.0]), np.array([True, False]), reamostragens=1000, seed=11
    )
    assert 0 < d.reamostragens_validas < 1000
    assert d.delta == pytest.approx(2.0)


def test_delta_pareado_e_deterministico_pela_semente():
    dias = ["A", "A", "B", "B"]
    v = np.array([1.0, -1.0, 2.0, 0.0])
    g = np.array([True, False, True, False])
    a = delta_pareado_por_dia(dias, v, g, reamostragens=200, seed=7)
    b = delta_pareado_por_dia(dias, v, g, reamostragens=200, seed=7)
    assert a == b
