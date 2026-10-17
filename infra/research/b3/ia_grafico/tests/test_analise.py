"""Resumo para o veredito e os diagnósticos (espelho, autoconcordância) — valores conhecidos."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from infra.research.b3.ia_grafico.analise import autoconcordancia, consistencia_espelho, resumir
from infra.research.b3.ia_grafico.estatistica import Celula
from infra.research.b3.ia_grafico.pipeline import Avaliacao
from infra.research.b3.ia_grafico.resposta import Lado

C, V, N = Lado.COMPRA, Lado.VENDA, Lado.NENHUM


def test_consistencia_do_espelho_conta_so_pares_validos_com_lado() -> None:
    originais = {"a": C, "b": V, "c": N, "d": C, "e": None}
    espelhados = {"a": V, "b": V, "c": N, "d": V, "e": C}  # leitura igual = lado oposto
    r = consistencia_espelho(originais, espelhados)
    assert r == {"pares": 3, "consistentes": 2, "taxa": 2 / 3, "none_concorda": 1}


def test_autoconcordancia_e_kappa() -> None:
    primeira = {"a": C, "b": V, "c": N, "d": C}
    repeticoes = {"a": [C, C], "b": [V, C], "c": [N, N], "d": [V, None]}
    r = autoconcordancia(primeira, repeticoes)
    # todos os pares entre as respostas válidas (Astra R2): a CCC → 3 iguais; b VVC → 1 de 3;
    # c NNN → 3; d CV → 0 de 1. Total 10 pares, 7 iguais.
    assert r["pares"] == 10 and r["iguais"] == 7 and r["taxa"] == 0.7
    # marginais 1.º elemento C4 V3 N3, 2.º C5 V2 N3 → pe = 0,35; kappa = (0,7 − 0,35) ÷ 0,65
    assert r["kappa"] == pytest.approx(0.35 / 0.65)
    assert autoconcordancia({"a": C}, {"a": [C]})["kappa"] is None  # uma classe só: indefinido


def _celulas(
    rng: np.random.Generator, meses: int, acerto: float, inicio: date = date(2024, 1, 1)
) -> list[Celula]:
    saida: list[Celula] = []
    for k in range(meses * 20):
        dia = inicio + timedelta(days=k * 30 // 20)
        for slot in range(12):
            mov = float(rng.normal(0, 30))
            b, s = mov - 1.5, -mov - 1.5
            certo = rng.random() < acerto
            lado = C if (b > s) == certo else V
            saida.append(Celula(dia, slot, lado, b, s, -32.0, -32.0, 28.0, 28.0, N))
    return saida


def test_resumir_monta_todas_as_cifras_e_o_holdout() -> None:
    rng = np.random.default_rng(4)
    prim = Avaliacao(_celulas(rng, 13, 0.6), [2.0] * 100, 0, 0, 0)
    hold = Avaliacao(_celulas(rng, 4, 0.6, inicio=date(2025, 3, 1)), [1.0] * 50, 0, 0, 0)
    r = resumir(
        primario=prim,
        patamar45=prim,
        patamar75=prim,
        holdout=hold,
        n_chamadas=3120,
        n_invalidas=3,
        holdout_n_chamadas=960,
        holdout_n_invalidas=0,
        reps=200,
    )
    assert r.n_operacoes == 13 * 20 * 12 and r.n_meses == 13
    assert r.d > 3 and r.ic[0] > 0 and r.p < 0.05 and r.nivel_completo == 2.0
    assert r.holdout_meses == 4 and r.holdout_operacoes == 4 * 20 * 12
    assert r.holdout_nivel_completo == 1.0 and r.holdout_d is not None and r.holdout_d > 0
    assert r.d_mm > 0  # a regra sem lado (N) rende 0


def test_resumir_sem_holdout_e_sem_operacao_da_nan_e_zero_honestos() -> None:
    vazio = Avaliacao([], [], 0, 0, 0)
    r = resumir(
        primario=vazio,
        patamar45=vazio,
        patamar75=vazio,
        holdout=None,
        n_chamadas=0,
        n_invalidas=0,
        holdout_n_chamadas=0,
        holdout_n_invalidas=0,
        reps=10,
    )
    assert r.n_operacoes == 0 and math.isnan(r.d) and math.isnan(r.nivel_completo)
    assert r.holdout_operacoes == 0 and r.holdout_d is None


def test_resumir_recusa_holdout_que_nao_vem_depois_e_patamar_com_outros_instantes() -> None:
    """Astra R2: disjunção e mesmos instantes verificados no caminho de análise, não só no texto."""
    rng = np.random.default_rng(7)
    prim = Avaliacao(_celulas(rng, 2, 0.5), [0.0], 0, 0, 0)
    sobreposto = Avaliacao(_celulas(rng, 1, 0.5), [0.0], 0, 0, 0)  # começa em 2024-01-01
    with pytest.raises(ValueError, match="holdout"):
        resumir(
            primario=prim,
            patamar45=prim,
            patamar75=prim,
            holdout=sobreposto,
            n_chamadas=1,
            n_invalidas=0,
            holdout_n_chamadas=1,
            holdout_n_invalidas=0,
            reps=5,
        )
    outro = Avaliacao(prim.celulas[1:], [0.0], 0, 0, 0)
    with pytest.raises(ValueError, match="patamar"):
        resumir(
            primario=prim,
            patamar45=outro,
            patamar75=prim,
            holdout=None,
            n_chamadas=1,
            n_invalidas=0,
            holdout_n_chamadas=0,
            holdout_n_invalidas=0,
            reps=5,
        )


def test_resumir_soma_a_censura_dos_dois_lados_e_dos_patamares() -> None:
    """Sonda da Astra R3: 12 gêmeos ausentes em P não podem virar contagem zero."""
    base = [
        Celula(date(2024, 1, 1) + timedelta(days=k), 0, C, 10.0, -10.0, -30.0, -30.0, 28.0, 28.0, N)
        for k in range(30)
    ]
    gemeo_ausente = [replace(base[0], venda_bp=None), *base[1:]]
    p45_ausente = [replace(base[1], compra_bp=None), base[0], *base[2:]]
    prim = Avaliacao(gemeo_ausente, [1.0], 0, 0, 0)
    r = resumir(
        primario=prim,
        patamar45=Avaliacao(p45_ausente, [1.0], 0, 0, 0),
        patamar75=Avaliacao(base, [1.0], 0, 0, 0),
        holdout=None,
        n_chamadas=30,
        n_invalidas=0,
        holdout_n_chamadas=0,
        holdout_n_invalidas=0,
        reps=5,
    )
    assert r.n_censuradas == 2  # união das chaves: (dia 1, slot 0) em P e (dia 2, slot 0) no 45
