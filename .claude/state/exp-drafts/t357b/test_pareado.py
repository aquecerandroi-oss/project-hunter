"""Oráculo do estimador pareado da T3.57b — séries sintéticas com valor esperado conhecido.

Três provas, e a terceira é a que importa: com **uma** decisão por dia o bootstrap de
blocos de dia degenera no bootstrap ordinário da média das diferenças, então o
estimador novo tem de concordar com o cálculo direto — é a mesma disciplina do
`t352d/test_oraculo.py` (um estimador novo não pode ter liberdade de discordar do
antigo no que os dois compartilham).
"""

from __future__ import annotations

import numpy as np
import pytest
from pareado import delta_pareado, holm


def test_delta_pontual_e_a_media_das_diferencas() -> None:
    # 4 pares, diferenças conhecidas: +1, +1, -1, +1  -> média +0,5
    pares = [("d1", 0.0, 1.0), ("d1", 2.0, 3.0), ("d2", 5.0, 4.0), ("d2", 1.0, 2.0)]
    c = delta_pareado(pares, reamostragens=2000, seed=7)
    assert c.n_pares == 4
    assert c.dias == 2
    assert c.delta == pytest.approx(0.5)
    assert c.exp_v1 == pytest.approx(2.0)
    assert c.exp_v2 == pytest.approx(2.5)


def test_diferenca_constante_da_intervalo_degenerado_e_p_no_piso() -> None:
    # toda barra melhora exatamente +0,25 R: nenhuma reamostragem pode cruzar zero
    pares = [(f"d{i}", float(i), float(i) + 0.25) for i in range(12)]
    c = delta_pareado(pares, reamostragens=1000, seed=11)
    assert c.delta == pytest.approx(0.25)
    assert c.ic95[0] == pytest.approx(0.25)
    assert c.ic95[1] == pytest.approx(0.25)
    assert c.p_bootstrap == pytest.approx(2.0 / 1000)


def test_um_par_por_dia_concorda_com_o_bootstrap_ordinario() -> None:
    rng = np.random.default_rng(2026)
    difs = rng.normal(0.1, 1.0, size=40)
    pares = [
        (f"d{i:02d}", 0.0, float(x)) for i, x in enumerate(difs)
    ]  # nome ordenavel: sorted(dias) tem de ser a ordem numerica
    c = delta_pareado(pares, reamostragens=5000, seed=99)

    r2 = np.random.default_rng(99)
    idx = np.arange(40)
    direto = np.array([difs[r2.choice(idx, size=40, replace=True)].mean() for _ in range(5000)])
    assert c.delta == pytest.approx(float(difs.mean()))
    assert c.ic95[0] == pytest.approx(float(np.percentile(direto, 2.5)), abs=1e-12)
    assert c.ic95[1] == pytest.approx(float(np.percentile(direto, 97.5)), abs=1e-12)


def test_holm_e_monotono_e_multiplica_pelo_posto() -> None:
    ajust = holm({"a": 0.01, "b": 0.04, "c": 0.30})
    assert ajust["a"] == pytest.approx(0.03)  # 3 x 0,01
    assert ajust["b"] == pytest.approx(0.08)  # 2 x 0,04
    assert ajust["c"] == pytest.approx(0.30)  # 1 x 0,30
    assert ajust["a"] <= ajust["b"] <= ajust["c"]


def test_holm_nunca_passa_de_um_e_nunca_desce() -> None:
    ajust = holm({"a": 0.9, "b": 0.5, "c": 0.6})
    assert ajust["b"] == pytest.approx(1.0)
    assert ajust["c"] == pytest.approx(1.0)
    assert ajust["a"] == pytest.approx(1.0)
