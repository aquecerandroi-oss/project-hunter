"""h036 — testes do desenho sequencial (escritos antes de design.py).

Rodar: uv run --no-sync pytest .claude/state/h036/test_design.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import design  # noqa: E402

pytestmark = pytest.mark.unit


def test_obf_spending_spends_everything_at_the_end_and_little_early() -> None:
    assert design.obf_spent(1.0, 0.025) == pytest.approx(0.025)
    assert design.obf_spent(1 / 3, 0.025) == pytest.approx(0.000104, abs=2e-5)  # 2(1 − Φ(2,2414·√3))
    assert design.obf_spent(1e-9, 0.025) == pytest.approx(0.0, abs=1e-12)


def test_lan_demets_obf_boundaries_three_equal_looks() -> None:
    # tabela clássica (Jennison & Turnbull; gsDesign sfLDOF, k=3, unilateral 0,025): 3,710 · 2,511 · 1,993
    b = design.boundaries((1 / 3, 2 / 3, 1.0), alpha=0.025, n_sim=400_000, seed=1)
    assert b == pytest.approx([3.710, 2.511, 1.993], abs=0.04)


def test_boundaries_hold_alpha_under_null() -> None:
    b = design.boundaries((1 / 3, 2 / 3, 1.0), alpha=0.025, n_sim=200_000, seed=2)
    z = design.brownian_z((1 / 3, 2 / 3, 1.0), drift=0.0, n_sim=200_000, seed=3)
    crossed = (z >= np.asarray(b)).any(axis=1).mean()
    assert crossed == pytest.approx(0.025, abs=0.002)


def test_cluster_ratio_z_matches_hand_computation() -> None:
    # 3 dias: somas 3, −1, 2 com 2, 1, 2 trades → média 4/5 = 0,8; resíduos 3−1,6=1,4; −1−0,8=−1,8; 2−1,6=0,4
    # EP CR1 = √(G/(G−1)·Σres²)/Σn = √(1,5·5,36)/5 = 0,5671
    r = np.array([1.0, 2.0, -1.0, 0.5, 1.5])
    day = np.array([0, 0, 1, 2, 2])
    m, se = design.cluster_mean_se(r, day)
    assert m == pytest.approx(0.8)
    assert se == pytest.approx(np.sqrt(1.5 * 5.36) / 5)


def test_t_quantile_matches_known_values() -> None:
    # tabelas: t_{0,975; 30} = 2,0423 · t_{0,975; 60} = 2,0003 · t_{0,999; 50} = 3,2614
    assert design.t_quantile(0.975, 30) == pytest.approx(2.0423, abs=2e-3)
    assert design.t_quantile(0.975, 60) == pytest.approx(2.0003, abs=1e-3)
    assert design.t_quantile(0.999, 50) == pytest.approx(3.2614, abs=1e-2)


def test_t_boundary_keeps_the_same_tail_probability() -> None:
    # fronteira z 1,96 (cauda 0,025) com 30 gl vira 2,0423
    assert design.t_boundary(1.959964, 30) == pytest.approx(2.0423, abs=2e-3)


def test_exact_t_quantile_in_the_far_tail_with_few_degrees_of_freedom() -> None:
    # valores exatos (tabela/scipy.stats.t.ppf): Astra rodada 2 mostrou que Cornish-Fisher dava 8,187 em vez de 8,610
    assert design.t_quantile(0.9995, 4) == pytest.approx(8.6103, abs=2e-3)
    assert design.t_quantile(0.9975, 4) == pytest.approx(5.5976, abs=2e-3)
    assert design.t_quantile(0.9995, 12) == pytest.approx(4.3178, abs=2e-3)
    assert design.t_quantile(0.975, 12) == pytest.approx(2.1788, abs=1e-3)
    assert design.t_cdf(2.0423, 30) == pytest.approx(0.975, abs=1e-4)
