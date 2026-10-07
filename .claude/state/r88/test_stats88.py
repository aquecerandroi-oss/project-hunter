"""R88 — testes do contraste ajustado por conjunto (valores conhecidos à mão, dado sintético)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stats88 import (  # noqa: E402
    Units,
    adjusted,
    bootstrap,
    halves,
    holm,
    plateau,
    supported_sets,
    verdict,
)


def _units(y, low, s, mint=None, day=None):
    n = len(y)
    return Units(
        y=np.asarray(y, float),
        low=np.asarray(low, bool),
        s=np.asarray(s, object),
        mint=np.asarray(mint if mint is not None else [f"m{i}" for i in range(n)], object),
        day=np.asarray(day if day is not None else ["d0"] * n, object),
    )


def test_support_requires_min_units_in_each_arm() -> None:
    u = _units([0] * 7, [1, 1, 0, 0, 1, 1, 1], ["a", "a", "a", "a", "b", "b", "b"])
    assert supported_sets(u, min_per_arm=2) == {"a": 4}
    assert supported_sets(u, min_per_arm=3) == {}


def test_adjusted_is_weighted_mean_of_within_set_differences() -> None:
    # conjunto a: baixo média 1,0, alto 0,0 (D=1); conjunto b: baixo 0,0, alto 0,0 (D=0), b com o dobro de unidades
    y = [1, 1, 0, 0] + [0, 0, 0, 0, 0, 0, 0, 0]
    low = [1, 1, 0, 0] + [1, 1, 1, 1, 0, 0, 0, 0]
    s = ["a"] * 4 + ["b"] * 8
    u = _units(y, low, s)
    w = supported_sets(u, min_per_arm=2)
    d, level = adjusted(u, w)
    assert d == pytest.approx(1 / 3)  # 4/12·1 + 8/12·0
    assert level == pytest.approx(4 / 12 * 1.0)


def test_pooled_confound_disappears_when_adjusted() -> None:
    # sem efeito dentro de cada conjunto; o conjunto ruim tem mais fatias altas -> D agrupado > 0, D ajustado = 0
    y = [0.0] * 10 + [-1.0] * 10
    low = [1] * 8 + [0] * 2 + [1] * 2 + [0] * 8
    s = ["bom"] * 10 + ["ruim"] * 10
    u = _units(y, low, s)
    pooled = u.y[u.low].mean() - u.y[~u.low].mean()
    assert pooled > 0.5
    d, _ = adjusted(u, supported_sets(u, min_per_arm=2))
    assert d == pytest.approx(0.0)


def test_bootstrap_is_reproducible_and_centered_p_is_large_without_effect() -> None:
    rng = np.random.default_rng(1)
    n = 400
    u = _units(
        rng.normal(0, 1, n),
        rng.random(n) < 0.7,
        np.where(np.arange(n) % 2 == 0, "a", "b"),
        mint=[f"m{i // 2}" for i in range(n)],
        day=[f"d{i % 10}" for i in range(n)],
    )
    w = supported_sets(u, min_per_arm=5)
    r1 = bootstrap(u, w, by="mint", reps=500, seed=7)
    r2 = bootstrap(u, w, by="mint", reps=500, seed=7)
    assert r1 == r2
    assert r1.lo < r1.d < r1.hi
    assert r1.p > 0.05
    assert r1.invalid == 0.0


def test_bootstrap_detects_a_large_effect() -> None:
    rng = np.random.default_rng(2)
    n = 600
    low = rng.random(n) < 0.7
    y = rng.normal(0, 0.3, n) + np.where(low, 0.3, 0.0)
    u = _units(y, low, ["a"] * n, day=[f"d{i % 12}" for i in range(n)])
    w = supported_sets(u, min_per_arm=5)
    r = bootstrap(u, w, by="day", reps=500, seed=3)
    assert r.lo > 0.15 and r.p < 0.01


def test_invalid_replicate_is_counted_not_hidden() -> None:
    # um único mint carrega todo o braço alto do conjunto: muitas réplicas esvaziam o braço
    y = [0.0] * 12
    low = [1] * 10 + [0, 0]
    mint = [f"m{i}" for i in range(10)] + ["X", "X"]
    u = _units(y, low, ["a"] * 12, mint=mint)
    r = bootstrap(u, {"a": 12}, by="mint", reps=400, seed=1)
    assert r.invalid > 0.2


def test_plateau_rules() -> None:
    pts = [(0.02, 0.01, True), (0.03, 0.005, True), (0.04, -0.01, True), (0.01, -0.02, True)]
    assert plateau(pts) == "planalto"
    assert plateau([(0.02, 0.01, True), (-0.01, -0.03, True), (0.03, 0.01, True), (0.02, 0.0, True)]) == "pico"
    assert plateau([(0.02, 0.01, True), (0.02, 0.01, False), (0.03, 0.01, False)]) == "não avaliável"


def test_halves_split_days_ceil() -> None:
    days = np.array(["d1", "d2", "d3", "d1", "d2", "d3"], object)
    first, second = halves(days)
    assert set(days[first]) == {"d1", "d2"} and set(days[second]) == {"d3"}


def test_holm_two_members() -> None:
    assert holm({"A": 0.04, "B": 0.01}) == {"A": 0.04, "B": 0.02}
    assert holm({"A": 1.0, "B": 0.03}) == {"A": 1.0, "B": 0.06}


def test_verdict_order_errata_r76() -> None:
    base = dict(
        limit=None, invalid=0.0, d=0.01, lo_m=-0.05, hi_m=0.04, lo_d=-0.06, hi_d=0.045,
        p_holm=0.5, level=-0.1, shape="pico", halves_pos=False, days_each_arm_ok=True, mre=0.05,
    )
    assert verdict(**base) == "REFUTA"
    assert verdict(**{**base, "hi_d": 0.06}) == "NÃO CONFIRMA"  # o mais largo dos dois manda
    assert verdict(**{**base, "invalid": 0.02}) == "NÃO CONFIRMA"
    assert verdict(**{**base, "limit": "poucos"}) == "LIMITE"
    assert verdict(**{**base, "hi_m": math.nan}) == "NÃO CONFIRMA"
    ok = dict(base, d=0.08, lo_m=0.01, hi_m=0.15, lo_d=0.02, hi_d=0.16, p_holm=0.01, level=0.02,
              shape="planalto", halves_pos=True)
    assert verdict(**ok) == "CONFIRMA"
    assert verdict(**{**ok, "level": -0.01}) == "NÃO CONFIRMA"
    assert verdict(**{**ok, "shape": "não avaliável"}) == "NÃO CONFIRMA"
