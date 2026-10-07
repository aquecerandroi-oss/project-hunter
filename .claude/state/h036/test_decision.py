"""h036 — testes da função de decisão única (análise e simulação usam a mesma; escritos antes de decision.py).

Rodar: uv run --no-sync pytest .claude/state/h036/test_decision.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import decision as dc  # noqa: E402

pytestmark = pytest.mark.unit


def _days(g: int, per_day: int, mean: float, spread: float, stress_shift: float = 0.0,
          first_half_mean: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """g dias com ``per_day`` trades; médias por dia alternando mean ± spread a cada semana (EP controlado)."""
    c = np.full((1, g), float(per_day))
    dev = np.where(dc.week_index(g) % 2 == 0, spread, -spread)  # alterna por SEMANA ISO: o EP agrupado por semana vê
    dev = dev - dev.mean()  # média exata (mesmo número de trades por dia)
    m = np.full(g, mean)
    if first_half_mean is not None:
        m[: (g + 1) // 2] = first_half_mean
        m[(g + 1) // 2:] = 2 * mean - first_half_mean
    s = ((m + dev) * per_day)[None, :]
    t = s - stress_shift * c
    return c, s, t


def test_final_look_with_too_few_days_is_data_limit_and_interim_continues() -> None:
    c, s, t = _days(10, 10, 0.5, 0.1)
    assert dc.decide(c, s, t, look=2, coverage_ok=np.array([True]))[0] == dc.LIMITE
    assert dc.decide(c, s, t, look=0, coverage_ok=np.array([True]))[0] == dc.CONTINUA


def test_coverage_failure_blocks_any_label() -> None:
    c, s, t = _days(60, 10, 0.5, 0.1)
    assert dc.decide(c, s, t, look=2, coverage_ok=np.array([False]))[0] == dc.LIMITE
    assert dc.decide(c, s, t, look=1, coverage_ok=np.array([False]))[0] == dc.CONTINUA


def test_confirm_takes_precedence_over_size_refutation() -> None:
    # média 0,075 com EP minúsculo: confirma positividade E exclui +0,10 — o rótulo é CONFIRMA (Astra must-fix 3)
    c, s, t = _days(60, 10, 0.075, 0.01)
    assert dc.decide(c, s, t, look=2, coverage_ok=np.array([True]))[0] == dc.CONFIRMA


def test_confirm_needs_economic_floor_halves_and_stress() -> None:
    ok = np.array([True])
    c, s, t = _days(60, 10, 0.04, 0.01)  # significativo mas abaixo do piso de +0,05
    assert dc.decide(c, s, t, look=2, coverage_ok=ok)[0] != dc.CONFIRMA
    c, s, t = _days(60, 10, 0.20, 0.01, first_half_mean=-0.05)  # uma metade negativa
    assert dc.decide(c, s, t, look=2, coverage_ok=ok)[0] != dc.CONFIRMA
    c, s, t = _days(60, 10, 0.20, 0.01, stress_shift=0.25)  # estresse leva a média abaixo de zero
    assert dc.decide(c, s, t, look=2, coverage_ok=ok)[0] != dc.CONFIRMA


def test_interim_futility_and_final_refutation() -> None:
    ok = np.array([True])
    c, s, t = _days(40, 10, -0.05, 0.01)  # intermediária, média ≤ 0, IC superior bem abaixo de +0,10 → REFUTA
    assert dc.decide(c, s, t, look=0, coverage_ok=ok)[0] == dc.REFUTA
    c, s, t = _days(40, 10, -0.05, 3.0)  # média ≤ 0 mas IC largo → NÃO CONFIRMA (futilidade, sem refutar o tamanho)
    assert dc.decide(c, s, t, look=0, coverage_ok=ok)[0] == dc.NAO_CONFIRMA
    c, s, t = _days(40, 10, 0.03, 3.0)  # intermediária, média > 0, sem fronteira → continua
    assert dc.decide(c, s, t, look=0, coverage_ok=ok)[0] == dc.CONTINUA


def test_inactive_days_do_not_count_as_clusters() -> None:
    c, s, t = _days(60, 10, 0.075, 0.01)
    zeros = np.zeros((1, 40))
    c2, s2, t2 = (np.concatenate([x, zeros], axis=1) for x in (c, s, t))
    assert dc.decide(c2, s2, t2, look=2, coverage_ok=np.array([True]))[0] == dc.CONFIRMA
    m, se, g = dc.stats(c2, s2)
    assert g[0] == 9  # semanas com trade: dias 0-59 a partir de uma quarta cobrem 9 semanas ISO; os vazios não contam


def test_vectorized_t_quantile_equals_scalar() -> None:
    import design
    df = np.array([5, 30, 59, 200])
    for p in (0.975, 0.9995, 0.99):
        assert dc.tq(p, df) == pytest.approx([design.t_quantile(p, int(x)) for x in df])


def test_standard_error_is_clustered_by_week_not_by_day() -> None:
    # 28 dias, 1 trade/dia: dentro de cada semana os dias alternam ±1 (somas semanais iguais) → EP semanal ~0;
    # semanas alternando ±1 por inteiro → EP semanal grande. Agrupar por dia não distinguiria os dois.
    c = np.ones((1, 28))
    within = np.tile([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 0.0], 4)[None, :] + 0.5  # toda semana soma 3,5
    across = np.where((np.arange(28) // 7) % 2 == 0, 1.0, -1.0)[None, :] + 0.5
    _, se_w, _ = dc.stats(c, within, week_offset=0)
    _, se_a, _ = dc.stats(c, across, week_offset=0)
    assert se_w[0] < 0.05 < se_a[0]


def test_week_offset_aligns_clusters_to_monday() -> None:
    # T0 numa quarta: dias 0–4 (qua–dom) são a semana 0, o dia 5 (segunda) abre a semana 1
    assert list(dc.week_index(7, week_offset=2)) == [0, 0, 0, 0, 0, 1, 1]


def test_halves_put_the_median_day_in_the_second_half() -> None:
    # Astra rodada 2: 181 dias, 90 primeiros −0,001, o mediano +0,1, 90 últimos +0,2 — "antes × a partir da mediana":
    # a primeira metade é negativa e CONFIRMA não pode sair
    g = 181
    c = np.full((1, g), 10.0)
    m = np.concatenate([np.full(90, -0.001), [0.1], np.full(90, 0.2)])
    dev = np.where(dc.week_index(g) % 2 == 0, 0.001, -0.001)
    s = ((m + dev) * 10)[None, :]
    assert dc.decide(c, s, s.copy(), look=2, coverage_ok=np.array([True]))[0] != dc.CONFIRMA
