"""TDD do D-P23 — series sinteticas com valor esperado calculado a mao.

O que estes testes fixam (e o que um erro aqui custaria):

* `resumo` — media, mediana, p25/p75 e fracao positiva de um horizonte. A
  convencao de percentil e declarada e testada (interpolacao linear, a de
  `numpy.percentile`), porque "p25" sem convencao nao e um numero.
* `curva_por_horizonte` — a mesma populacao lida em varios horizontes, com a
  cobertura POR horizonte contada e nunca preenchida.
* `delta_pareado_por_decisao` — o Δ(240 − 80) e pareado **por decisao** (a mesma
  linha nos dois horizontes) e so existe para a decisao que tem os dois pontos.
* `ret_atr` — a aritmetica de (close − open)/ATR, long-only.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from curva import (
    Resumo,
    curva_por_horizonte,
    delta_pareado_por_decisao,
    resumo,
    ret_atr,
)


def test_ret_atr_e_a_distancia_em_atr_a_partir_do_open_da_entrada():
    # open 100, close 101, ATR 2 -> meio ATR
    assert ret_atr(entry_open=100.0, preco=101.0, atr=2.0) == pytest.approx(0.5)
    # movimento adverso e negativo, nunca em modulo
    assert ret_atr(entry_open=100.0, preco=98.0, atr=2.0) == pytest.approx(-1.0)


def test_ret_atr_recusa_atr_nao_positivo_em_vez_de_devolver_infinito():
    with pytest.raises(ValueError):
        ret_atr(entry_open=100.0, preco=101.0, atr=0.0)
    with pytest.raises(ValueError):
        ret_atr(entry_open=100.0, preco=101.0, atr=-1.0)


def test_resumo_com_valores_a_mao():
    # 4 valores: -1, 0, 1, 3  -> media 0.75; mediana (0+1)/2 = 0.5
    # p25 por interpolacao linear: posicao 0.25*(4-1)=0.75 entre -1 e 0 -> -0.25
    # p75: posicao 2.25 entre 1 e 3 -> 1 + 0.25*(3-1) = 1.5
    # positivos ESTRITOS: 1 e 3 -> 2/4 = 0.5 ; um zero nao conta como positivo
    r = resumo(np.array([-1.0, 0.0, 1.0, 3.0]))
    assert r == Resumo(n=4, media=0.75, mediana=0.5, p25=-0.25, p75=1.5, frac_pos=0.5, zeros=1)


def test_resumo_de_amostra_vazia_e_nan_nunca_zero():
    r = resumo(np.array([], dtype=float))
    assert r.n == 0
    assert math.isnan(r.media) and math.isnan(r.mediana)
    assert math.isnan(r.p25) and math.isnan(r.p75) and math.isnan(r.frac_pos)


def test_resumo_ignora_ausencia_em_vez_de_preencher():
    # o nan e AUSENCIA de endpoint; ele nao entra no denominador
    r = resumo(np.array([1.0, float("nan"), 3.0]))
    assert r.n == 2
    assert r.media == pytest.approx(2.0)
    assert r.frac_pos == pytest.approx(1.0)


def test_curva_por_horizonte_conta_cobertura_por_ponto():
    # duas decisoes; a segunda nao tem o endpoint de 240
    linhas = [
        ("d1", 80, 0.5),
        ("d1", 240, 1.5),
        ("d2", 80, -0.5),
        ("d2", 240, float("nan")),
    ]
    curva = curva_por_horizonte(linhas, horizontes=(80, 240))
    assert curva[80].n == 2
    assert curva[80].media == pytest.approx(0.0)
    assert curva[240].n == 1
    assert curva[240].media == pytest.approx(1.5)


def test_delta_pareado_por_decisao_usa_so_quem_tem_os_dois_pontos():
    # d1 tem os dois (1.5 - 0.5 = +1.0); d2 so tem o de 80 -> fora do pareamento
    linhas = [
        ("d1", "2026-06-12", 80, 0.5),
        ("d1", "2026-06-12", 240, 1.5),
        ("d2", "2026-06-13", 80, -0.5),
        ("d2", "2026-06-13", 240, float("nan")),
    ]
    d = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=200, seed=1)
    assert d.n == 1
    assert d.media == pytest.approx(1.0)
    assert d.dias == 1


def test_delta_pareado_e_a_media_das_diferencas_nao_a_diferenca_das_medias_de_populacoes_diferentes():
    # se a populacao fosse recortada por horizonte, 240 teria media 1.5 e 80
    # media 0.0 -> "Δ" = 1.5. Pareado por decisao o Δ e +1.0 (so d1 conta).
    linhas = [
        ("d1", "2026-06-12", 80, 0.5),
        ("d1", "2026-06-12", 240, 1.5),
        ("d2", "2026-06-13", 80, -0.5),
        ("d2", "2026-06-13", 240, float("nan")),
    ]
    d = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=200, seed=1)
    assert d.media == pytest.approx(1.0)
    assert d.media != pytest.approx(1.5)


def test_delta_pareado_ic_de_uma_constante_colapsa_no_valor():
    # todas as diferencas iguais a +0.25, em tres dias -> o IC de blocos de dia
    # nao pode ter largura: nenhuma reamostragem muda a media
    linhas = []
    for i, dia in enumerate(["2026-06-12", "2026-06-13", "2026-06-14"]):
        for k in range(3):
            linhas.append((f"d{i}{k}", dia, 80, 0.0))
            linhas.append((f"d{i}{k}", dia, 240, 0.25))
    d = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=500, seed=7)
    assert d.media == pytest.approx(0.25)
    assert d.ic95[0] == pytest.approx(0.25)
    assert d.ic95[1] == pytest.approx(0.25)


def test_delta_pareado_ic_de_dois_dias_opostos_cobre_os_dois_extremos():
    # dia A com Δ = +1 (2 decisoes), dia B com Δ = -1 (2 decisoes). Media 0.
    # Reamostrando dias inteiros, as tres reamostragens possiveis dao
    # {+1, 0, -1}: o IC tem de conter -1 e +1.
    linhas = [
        ("a1", "2026-06-12", 80, 0.0), ("a1", "2026-06-12", 240, 1.0),
        ("a2", "2026-06-12", 80, 0.0), ("a2", "2026-06-12", 240, 1.0),
        ("b1", "2026-06-13", 80, 0.0), ("b1", "2026-06-13", 240, -1.0),
        ("b2", "2026-06-13", 80, 0.0), ("b2", "2026-06-13", 240, -1.0),
    ]
    d = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=5000, seed=11)
    assert d.media == pytest.approx(0.0)
    assert d.ic95[0] == pytest.approx(-1.0)
    assert d.ic95[1] == pytest.approx(1.0)


def test_delta_pareado_sem_par_nenhum_e_nan_nunca_zero():
    linhas = [("d1", "2026-06-12", 80, 0.5), ("d1", "2026-06-12", 240, float("nan"))]
    d = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=10, seed=1)
    assert d.n == 0
    assert math.isnan(d.media)
    assert math.isnan(d.ic95[0]) and math.isnan(d.ic95[1])


def test_a_ordem_das_linhas_nao_muda_o_delta_nem_o_ic():
    linhas = [
        ("a1", "2026-06-12", 80, 0.1), ("a1", "2026-06-12", 240, 0.4),
        ("b1", "2026-06-13", 80, -0.2), ("b1", "2026-06-13", 240, 0.3),
        ("c1", "2026-06-14", 80, 0.7), ("c1", "2026-06-14", 240, 0.2),
    ]
    d1 = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=500, seed=3)
    d2 = delta_pareado_por_decisao(list(reversed(linhas)), h_longo=240, h_curto=80,
                                   reamostragens=500, seed=3)
    assert d1.media == pytest.approx(d2.media)
    assert d1.ic95 == pytest.approx(d2.ic95)


# --------------------------------------------------------------------------
# Anti-antecipacao (PIPELINE §2): a curva nao pode mudar quando muda uma vela
# que, no instante medido, ainda nao fechou.
# --------------------------------------------------------------------------

from curva import endpoint_open_time, escolhe_endpoint  # noqa: E402


def test_o_endpoint_de_mais_h_e_a_vela_que_fecha_em_mais_h_nao_a_que_abre():
    # entrada no open do minuto 0. O preco "aos +5 min" e o close da vela que
    # abre no minuto 4 e fecha no minuto 5. A vela que ABRE no minuto 5 fecha no
    # minuto 6 -- um minuto de horizonte a mais, e um minuto que aos +5 ainda
    # estava se formando.
    assert endpoint_open_time(0, 5) == 4
    assert endpoint_open_time(0, 240) == 239
    assert endpoint_open_time(100, 80) == 179


def test_horizonte_menor_que_um_minuto_e_recusado():
    with pytest.raises(ValueError):
        endpoint_open_time(0, 0)


def test_mudar_a_vela_que_ainda_nao_fechou_no_instante_medido_nao_muda_a_curva():
    # a vela do minuto 5 (que fecha no minuto 6) nao participa do ponto +5.
    velas_a = [(4, 101.0, True), (5, 999.0, False)]
    velas_b = [(4, 101.0, True), (5, -999.0, False)]
    velas_c = [(4, 101.0, True)]  # ela nem existe
    for velas in (velas_a, velas_b, velas_c):
        assert escolhe_endpoint(velas, entry_minuto=0, h=5) == pytest.approx(101.0)


def test_uma_vela_nao_final_no_proprio_endpoint_e_ausencia_nunca_substituida():
    # a vela do minuto 4 existe mas is_final=False: o ponto +5 NAO existe, e a
    # resposta e None -- nunca o fechamento do minuto 3.
    velas = [(3, 100.5, True), (4, 101.0, False)]
    assert escolhe_endpoint(velas, entry_minuto=0, h=5) is None


def test_virar_is_final_para_true_e_o_que_faz_o_ponto_existir():
    velas_antes = [(4, 101.0, False)]
    velas_depois = [(4, 101.0, True)]
    assert escolhe_endpoint(velas_antes, entry_minuto=0, h=5) is None
    assert escolhe_endpoint(velas_depois, entry_minuto=0, h=5) == pytest.approx(101.0)


# --------------------------------------------------------------------------
# IC da MEDIANA por blocos de dia: a media do Δ e sensivel a cauda, e sem um
# segundo estimador nao da para dizer se a acumulacao tardia e de muitas
# decisoes ou de poucas grandes.
# --------------------------------------------------------------------------

from curva import ic_mediana_blocos  # noqa: E402


def test_ic_mediana_de_uma_constante_colapsa_no_valor():
    dias = ["2026-06-12"] * 3 + ["2026-06-13"] * 3
    r = ic_mediana_blocos(dias, np.full(6, 0.5), reamostragens=500, seed=5)
    assert r.media == pytest.approx(0.5)  # `media` guarda a ESTATISTICA pedida
    assert r.ic95 == pytest.approx((0.5, 0.5))
    assert r.n == 6 and r.dias == 2


def test_ic_mediana_e_a_mediana_nao_a_media():
    # 1, 1, 1, 97 -> media 25, mediana 1
    dias = ["2026-06-12"] * 4
    r = ic_mediana_blocos(dias, np.array([1.0, 1.0, 1.0, 97.0]), reamostragens=100, seed=5)
    assert r.media == pytest.approx(1.0)


def test_ic_mediana_de_dois_dias_opostos_cobre_os_dois_lados():
    # dia A: tres valores +1 ; dia B: tres valores -1. Mediana global = 0
    # (media dos dois centrais). Reamostrando dias inteiros: AA -> +1, BB -> -1.
    dias = ["2026-06-12"] * 3 + ["2026-06-13"] * 3
    vals = np.array([1.0, 1.0, 1.0, -1.0, -1.0, -1.0])
    r = ic_mediana_blocos(dias, vals, reamostragens=5000, seed=13)
    assert r.media == pytest.approx(0.0)
    assert r.ic95[0] == pytest.approx(-1.0)
    assert r.ic95[1] == pytest.approx(1.0)


def test_ic_mediana_de_amostra_vazia_e_nan():
    r = ic_mediana_blocos([], np.array([], dtype=float), reamostragens=10, seed=1)
    assert r.n == 0 and math.isnan(r.media)
    assert math.isnan(r.ic95[0]) and math.isnan(r.ic95[1])


from curva import diferencas_pareadas  # noqa: E402


def test_diferencas_pareadas_e_a_mesma_populacao_do_delta_pareado():
    linhas = [
        ("a1", "2026-06-12", 80, 0.1), ("a1", "2026-06-12", 240, 0.4),
        ("b1", "2026-06-13", 80, -0.2), ("b1", "2026-06-13", 240, 0.3),
        ("c1", "2026-06-14", 80, 0.7), ("c1", "2026-06-14", 240, float("nan")),
    ]
    dias, diffs = diferencas_pareadas(linhas, h_longo=240, h_curto=80)
    d = delta_pareado_por_decisao(linhas, h_longo=240, h_curto=80, reamostragens=50, seed=1)
    assert len(dias) == d.n == diffs.size == 2
    assert float(diffs.mean()) == pytest.approx(d.media)
    assert sorted(dias) == ["2026-06-12", "2026-06-13"]
