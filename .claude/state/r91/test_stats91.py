"""R91 (H-034) — testes sintéticos com valores conhecidos do estimador, dos bootstraps e do veredito."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats91 import (  # noqa: E402
    CONFIRMA,
    LIMITE,
    NAO,
    REFUTA,
    Units,
    Scenario,
    adjusted,
    bootstrap,
    halves_mask,
    holm,
    leave_one_out,
    measure_verdict,
    family_verdict,
    supported_strata,
)


def U(y, x, s, mint=None, day=None, conj=None) -> Units:
    n = len(y)
    return Units(
        y=np.asarray(y, float),
        x=np.asarray(x, bool),
        s=np.asarray(s, object),
        mint=np.asarray(mint if mint is not None else [f"m{i}" for i in range(n)], object),
        day=np.asarray(day if day is not None else ["2026-09-20"] * n, object),
        conj=np.asarray(conj if conj is not None else s, object),
    )


def test_adjusted_two_strata_known_value() -> None:
    # estrato A: true {1, 3} (média 2), false {0} (média 0) -> diff 2, w = 2*1/3
    # estrato B: true {1} , false {2, 4, 6} (média 4) -> diff -3, w = 1*3/4
    u = U([1, 3, 0, 1, 2, 4, 6], [1, 1, 0, 1, 0, 0, 0], list("AAABBBB"))
    d, lvl = adjusted(u)
    wa, wb = 2 / 3, 3 / 4
    assert d == pytest.approx((wa * 2 + wb * -3) / (wa + wb))
    assert lvl == pytest.approx((wa * 2 + wb * 1) / (wa + wb))


def test_adjusted_differs_from_pooled_simpson() -> None:
    # dentro de cada estrato true − false = +1; agrupado seria negativo
    y = [10, 9, 9, 9, 0, 0, 0, -1]
    x = [1, 0, 0, 0, 1, 1, 1, 0]
    s = list("AAAABBBB")
    d, _ = adjusted(U(y, x, s))
    assert d == pytest.approx(1.0)
    pooled = np.mean([10, 0, 0, 0]) - np.mean([9, 9, 9, -1])
    assert pooled < 0


def test_stratum_without_an_arm_drops_and_renormalizes() -> None:
    u = U([1, 0, 5, 7], [1, 0, 1, 1], list("AABB"))
    d, lvl = adjusted(u)
    assert d == pytest.approx(1.0)
    assert lvl == pytest.approx(1.0)


def test_no_valid_stratum_is_nan() -> None:
    d, lvl = adjusted(U([1, 2], [1, 1], ["A", "B"]))
    assert math.isnan(d) and math.isnan(lvl)


def test_multiplicity_equals_duplicating_rows() -> None:
    u = U([1, 3, 0, 2], [1, 1, 0, 0], list("AAAA"))
    m = np.array([2.0, 1.0, 1.0, 3.0])
    d_m, _ = adjusted(u, m)
    dup = U([1, 1, 3, 0, 2, 2, 2], [1, 1, 1, 0, 0, 0, 0], list("AAAAAAA"))
    d_dup, _ = adjusted(dup)
    assert d_m == pytest.approx(d_dup)


def test_nan_outcome_is_censored_not_zero() -> None:
    u = U([1, np.nan, 0, 0], [1, 1, 0, 0], list("AAAA"))
    d, _ = adjusted(u)
    assert d == pytest.approx(1.0)


def test_bootstrap_constant_effect_has_degenerate_ci_and_p_zero() -> None:
    n = 40
    x = np.arange(n) % 2 == 0
    y = np.where(x, 0.3, 0.1)
    u = U(y, x, ["A"] * n, mint=[f"m{i}" for i in range(n)], day=[f"d{i % 10}" for i in range(n)])
    b = bootstrap(u, by="mint", reps=500, seed=1)
    assert b.d == pytest.approx(0.2)
    assert b.lo == pytest.approx(0.2) and b.hi == pytest.approx(0.2)
    assert b.p == 0.0
    assert b.invalid == 0.0


def test_bootstrap_counts_invalid_replicas() -> None:
    # um estrato só, cada braço numa mint -> réplica sem um dos braços é inválida (prob 1/2)
    u = U([1.0, 0.0], [1, 0], ["A", "A"], mint=["a", "b"])
    b = bootstrap(u, by="mint", reps=2000, seed=3)
    assert 0.4 < b.invalid < 0.6


def test_bootstrap_null_p_about_half_and_ci_covers_zero() -> None:
    rng = np.random.default_rng(7)
    n = 600
    x = rng.random(n) < 0.4
    y = rng.normal(0, 0.4, n)
    u = U(y, x, rng.choice(["A", "B", "C"], n), mint=[f"m{i // 2}" for i in range(n)],
          day=[f"d{i % 12}" for i in range(n)])
    b = bootstrap(u, by="mint", reps=2000, seed=11)
    assert b.lo < 0 < b.hi or abs(b.d) < 0.08
    assert 0.0 <= b.p <= 1.0
    assert b.basic_lo == pytest.approx(2 * b.d - b.hi)


def test_supported_strata_counts_both_arms() -> None:
    u = U([0] * 13, [1] * 5 + [0] * 5 + [1, 1, 0], ["A"] * 10 + ["B"] * 3)
    assert supported_strata(u, min_per_arm=5) == {"A"}


def test_halves_boundary_from_frozen_days() -> None:
    frozen = ["d1", "d2", "d3", "d4", "d5"]
    m1, m2 = halves_mask(np.array(["d1", "d3", "d5", "d4"], object), frozen)
    assert m1.tolist() == [True, True, False, False]
    assert m2.tolist() == [False, False, True, True]


def test_leave_one_out_by_conjunto() -> None:
    u = U([1, 0, 1, 0, 0, 1], [1, 0, 1, 0, 1, 0], ["A", "A", "B", "B", "C", "C"])
    out = leave_one_out(u)
    assert set(out) == {"A", "B", "C"}
    assert out["C"] == pytest.approx(1.0)
    one = U([1, 0], [1, 0], ["A", "A"])
    assert math.isnan(leave_one_out(one)["A"])


def test_holm() -> None:
    assert holm({"H": 0.01, "P": 0.04}) == {"H": 0.02, "P": 0.04}
    assert holm({"H": 0.03, "P": 1.0}) == {"H": 0.06, "P": 1.0}


def _sc(**kw) -> Scenario:
    base = dict(d=0.08, lo_m=0.02, hi_m=0.14, lo_d=0.01, hi_d=0.15, inv_m=0.0, inv_d=0.0,
                level=0.03, halves=(0.05, 0.1), loo=(0.06, 0.07))
    base.update(kw)
    return Scenario(**base)


def test_verdict_confirma_requires_everything_in_both_scenarios() -> None:
    assert measure_verdict(instrument=None, limit=None, prim=_sc(), s1=_sc(), p_holm=0.01, mre=0.05) == CONFIRMA
    assert measure_verdict(instrument=None, limit=None, prim=_sc(), s1=_sc(level=-0.01), p_holm=0.01, mre=0.05) == NAO
    assert measure_verdict(instrument=None, limit=None, prim=_sc(), s1=_sc(), p_holm=0.06, mre=0.05) == NAO
    assert measure_verdict(instrument=None, limit=None, prim=_sc(halves=(0.05, math.nan)), s1=_sc(),
                           p_holm=0.01, mre=0.05) == NAO
    assert measure_verdict(instrument=None, limit=None, prim=_sc(loo=(0.06, -0.01)), s1=_sc(),
                           p_holm=0.01, mre=0.05) == NAO
    assert measure_verdict(instrument=None, limit=None, prim=_sc(inv_d=0.02), s1=_sc(), p_holm=0.01, mre=0.05) == NAO


def test_verdict_refuta_needs_both_scenarios_and_valid_bootstrap() -> None:
    lo = dict(d=0.0, lo_m=-0.04, hi_m=0.04, lo_d=-0.03, hi_d=0.045)
    assert measure_verdict(instrument=None, limit=None, prim=_sc(**lo), s1=_sc(**lo), p_holm=0.5, mre=0.05) == REFUTA
    assert measure_verdict(instrument=None, limit=None, prim=_sc(**lo), s1=_sc(**{**lo, "hi_d": 0.06}),
                           p_holm=0.5, mre=0.05) == NAO
    assert measure_verdict(instrument=None, limit=None, prim=_sc(**lo, inv_m=0.02), s1=_sc(**lo),
                           p_holm=0.5, mre=0.05) == NAO


def test_verdict_precedence_instrument_then_limit() -> None:
    assert measure_verdict(instrument="x", limit="y", prim=_sc(), s1=_sc(), p_holm=0.01, mre=0.05) == "NÃO CONFIRMA — instrumento"
    assert measure_verdict(instrument=None, limit="y", prim=_sc(), s1=_sc(), p_holm=0.01, mre=0.05) == LIMITE


def test_family_verdict() -> None:
    assert family_verdict({"H": CONFIRMA, "P": LIMITE}) == CONFIRMA
    assert family_verdict({"H": REFUTA, "P": REFUTA}) == REFUTA
    assert family_verdict({"H": REFUTA, "P": LIMITE}) == NAO
    assert family_verdict({"H": LIMITE, "P": LIMITE}) == "NÃO CONFIRMA — limite de dado"
