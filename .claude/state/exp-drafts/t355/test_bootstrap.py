"""Testes do bootstrap de blocos — T3.55b.

O teste que importa é o primeiro: o atalho por estatística suficiente tem de
devolver **os mesmos números** que `t342-blocos/blocos.py`, arquivo que esta task
não pode e não vai modificar. Se um dia divergirem, o número publicado é o do
`blocos.py`.
"""

from __future__ import annotations

import numpy as np
import pytest
from blocos import contraste_por_piso
from bootstrap_padroes import PISO, como_decisoes, contraste_rapido, holm, media_por_blocos


def populacao(semente: int = 7, dias: int = 20, por_dia: int = 40, taxa: float = 0.08):
    rng = np.random.default_rng(semente)
    dias_linha = np.repeat([f"2026-08-{d + 1:02d}" for d in range(dias)], por_dia)
    residuo = rng.normal(0.0, 1.0, dias * por_dia)
    marca = rng.random(dias * por_dia) < taxa
    return dias_linha, residuo, marca


def test_o_atalho_reproduz_blocos_numero_a_numero() -> None:
    dias_linha, residuo, marca = populacao()
    rapido = contraste_rapido("teste", dias_linha, residuo, marca, reamostragens=500, seed=123)
    lento = contraste_por_piso(
        como_decisoes(dias_linha, residuo, marca), PISO, reamostragens=500, seed=123
    )
    assert rapido.n_pai == lento.n_pai
    assert rapido.n_variante == lento.n_variante
    assert rapido.dias == lento.dias
    assert rapido.reamostragens_validas == lento.reamostragens_validas
    assert rapido.exp_pai == pytest.approx(lento.exp_pai, abs=1e-12)
    assert rapido.exp_variante == pytest.approx(lento.exp_variante, abs=1e-12)
    assert rapido.delta == pytest.approx(lento.delta, abs=1e-12)
    assert rapido.ic95[0] == pytest.approx(lento.ic95[0], abs=1e-12)
    assert rapido.ic95[1] == pytest.approx(lento.ic95[1], abs=1e-12)


def test_um_efeito_plantado_aparece_e_o_intervalo_exclui_zero() -> None:
    """Se o padrão de fato adianta +0,5 ATR, o bootstrap tem de enxergar."""
    dias_linha, residuo, marca = populacao(semente=11)
    residuo = residuo + marca * 0.8
    c = contraste_rapido("plantado", dias_linha, residuo, marca, reamostragens=2000)
    assert c.delta > 0.4
    assert c.ic95[0] > 0
    assert c.p_valor < 0.05


def test_ruido_puro_nao_produz_significancia() -> None:
    dias_linha, residuo, marca = populacao(semente=13)
    c = contraste_rapido("ruido", dias_linha, residuo, marca, reamostragens=2000)
    assert c.ic95[0] < 0 < c.ic95[1]
    assert c.p_valor > 0.05


def test_o_bloco_e_o_dia_e_isso_alarga_o_intervalo() -> None:
    """Um choque comum ao dia inteiro: tratar linha como independente estreita mentira.

    Aqui o efeito é **do dia**, não do padrão: metade dos dias anda +1 e o padrão
    aparece com a mesma taxa em todos. Um bootstrap por linha veria um Δ grande e
    apertado; o bootstrap por dia tem de deixar o zero dentro do intervalo.
    """
    dias_linha, residuo, marca = populacao(semente=17, dias=20, por_dia=60, taxa=0.10)
    choque = np.array([1.5 if int(d[-2:]) % 2 == 0 else -1.5 for d in dias_linha])
    c = contraste_rapido("choque", dias_linha, residuo + choque, marca, reamostragens=2000)
    assert c.ic95[0] < 0 < c.ic95[1]


def test_a_media_por_blocos_cobre_o_valor_verdadeiro() -> None:
    dias_linha, residuo, _ = populacao(semente=23, dias=25, por_dia=50)
    media, ic = media_por_blocos(dias_linha, residuo + 0.3, reamostragens=2000)
    assert media == pytest.approx(float((residuo + 0.3).mean()))
    assert ic[0] < media < ic[1]


def test_a_media_por_blocos_alarga_quando_o_choque_e_do_dia() -> None:
    """O mesmo ruído, agrupado por dia, tem de dar intervalo maior que o ingênuo."""
    dias_linha, residuo, _ = populacao(semente=29, dias=25, por_dia=50)
    choque = np.array([1.5 if int(d[-2:]) % 2 == 0 else -1.5 for d in dias_linha])
    _, ic = media_por_blocos(dias_linha, residuo + choque, reamostragens=2000)
    ingenuo = 1.96 * float(np.std(residuo + choque)) / np.sqrt(residuo.size)
    assert (ic[1] - ic[0]) > 4 * (2 * ingenuo)


def test_holm_ordena_e_e_monotono() -> None:
    p = {"a": 0.001, "b": 0.02, "c": 0.30, "d": 0.9}
    saida = holm(p)
    assert saida["a"][0] == pytest.approx(0.004)
    assert saida["b"][0] == pytest.approx(0.06)
    assert saida["a"][1] is True
    assert saida["b"][1] is False
    assert saida["c"][0] >= saida["b"][0]
    assert saida["d"][0] >= saida["c"][0]


def test_holm_nao_deixa_nada_passar_quando_a_familia_e_grande() -> None:
    """84 testes: um p de 0,01 sozinho não é evidência de nada."""
    p = {f"t{k}": 0.01 if k == 0 else 0.5 for k in range(84)}
    assert holm(p)["t0"][1] is False


def test_populacao_sem_ocorrencia_devolve_nan_e_nao_zero() -> None:
    dias_linha, residuo, _ = populacao()
    marca = np.zeros(residuo.size, dtype=bool)
    c = contraste_rapido("vazio", dias_linha, residuo, marca, reamostragens=100)
    assert np.isnan(c.delta)
    assert c.reamostragens_validas == 0
