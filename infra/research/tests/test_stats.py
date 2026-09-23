"""Estatística do moinho contra valores conhecidos e famílias sintéticas."""

from __future__ import annotations

import numpy as np
import pytest

from infra.research.stats import (
    adjust_family,
    block_bootstrap,
    bucket_table,
    cluster_bootstrap,
    contrast,
    permutation_p,
    plateau_or_spike,
    quantile,
    quantile_buckets,
    select,
    terciles,
    threshold_curve,
)

# --------------------------------------------------------------------------- básicos


def test_quantile_is_nearest_rank_like_r67() -> None:
    xs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert quantile(xs, 0.0) == 1.0
    assert quantile(xs, 0.5) == 5.0  # round(0.5 * 9) = round(4.5) = 4 (banker's) -> s[4]
    assert quantile(xs, 1.0) == 10.0


def test_contrast_known_value() -> None:
    y = np.array([1.0, 3.0, 10.0, 20.0])
    sel = np.array([True, True, False, False])
    assert contrast(y, sel) == pytest.approx(2.0 - 15.0)


def test_contrast_is_nan_with_an_empty_side() -> None:
    y = np.array([1.0, 2.0])
    assert np.isnan(contrast(y, np.array([True, True])))


def test_quantile_buckets_cut_like_r65() -> None:
    vals = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
    b = quantile_buckets(vals, 3)
    assert [lab for lab, _ in b] == ["10..30", "40..60", "70..90"]
    assert [len(idx) for _, idx in b] == [3, 3, 3]


def test_terciles_known_values() -> None:
    assert terciles([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]) == (3.0, 5.0)


def test_missing_value_is_not_bucket_zero() -> None:
    """O bug que o R69 apanhou: ausente virava percentil zero, não 'indisponível'."""
    vals = [None, 1.0, 5.0, 9.0]
    table = bucket_table(vals, [100.0, 1.0, 2.0, 3.0], [2.0, 6.0])
    assert sum(b.n for b in table) == 3  # a linha ausente ficou de fora, não no balde baixo
    assert table[0].mean == pytest.approx(1.0)


def test_select_never_selects_a_missing_value() -> None:
    assert select([None, 1.0, 9.0], 5.0, "low").tolist() == [False, True, False]
    assert select([None, 1.0, 9.0], 5.0, "high").tolist() == [False, False, True]


def test_select_refuses_an_unknown_direction() -> None:
    with pytest.raises(ValueError, match="direção"):
        select([1.0], 0.5, "para cima")


# ------------------------------------------------------------------------ bootstraps


def _clustered(n_clusters: int, per: int, gap: float) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Clusters inteiros são idênticos: a informação real é `n_clusters`, não `n`."""
    rng = np.random.default_rng(7)
    y: list[float] = []
    sel: list[bool] = []
    cid: list[str] = []
    for c in range(n_clusters):
        hi = c % 2 == 0
        level = rng.normal(gap if hi else 0.0, 1.0)
        y += [level] * per
        sel += [hi] * per
        cid += [f"c{c}"] * per
    return np.array(y), np.array(sel), cid


def test_cluster_bootstrap_is_wider_than_pretending_rows_are_independent() -> None:
    y, sel, cid = _clustered(20, 10, gap=1.0)
    grouped = cluster_bootstrap(y, sel, cid, reps=2000, seed=1)
    as_if_independent = cluster_bootstrap(
        y, sel, [str(i) for i in range(y.size)], reps=2000, seed=1
    )
    assert (grouped.hi - grouped.lo) > 2.0 * (as_if_independent.hi - as_if_independent.lo)
    assert grouped.groups == 20
    assert as_if_independent.groups == 200


def test_cluster_bootstrap_brackets_a_clean_effect() -> None:
    y = np.concatenate([np.full(60, 1.0), np.full(60, 0.0)])
    sel = np.concatenate([np.ones(60, bool), np.zeros(60, bool)])
    cid = [f"c{i}" for i in range(120)]
    ci = cluster_bootstrap(y, sel, cid, reps=2000, seed=2)
    assert ci.lo > 0.5 and ci.hi < 1.5
    assert ci.p_le0 == 0.0


def test_block_bootstrap_by_day_uses_days_as_the_unit() -> None:
    y, sel, day = _clustered(8, 25, gap=0.5)
    ci = block_bootstrap(y, sel, day, reps=2000, seed=3)
    assert ci.groups == 8


# ------------------------------------------------------------------------ permutação


def test_permutation_p_is_tiny_for_a_clean_separation() -> None:
    y = np.concatenate([np.full(40, 1.0), np.full(40, 0.0)])
    sel = np.concatenate([np.ones(40, bool), np.zeros(40, bool)])
    assert permutation_p(y, sel, reps=2000, seed=4) < 0.002


def test_permutation_p_is_large_for_no_effect() -> None:
    rng = np.random.default_rng(5)
    y = rng.normal(size=200)
    sel = np.arange(200) % 2 == 0
    assert permutation_p(y, sel, reps=2000, seed=5) > 0.20


def test_stratified_permutation_kills_a_pure_day_effect() -> None:
    """Todo o 'efeito' é o dia: sem estrato dá p minúsculo, com estrato não dá."""
    day = np.repeat(np.arange(6), 30)
    y = np.where(day % 2 == 0, 1.0, 0.0).astype(np.float64)
    sel = day % 2 == 0  # selecionado exatamente nos dias bons
    naive = permutation_p(y, sel, reps=2000, seed=6)
    stratified = permutation_p(y, sel, [str(d) for d in day], reps=2000, seed=6)
    assert naive < 0.002
    assert stratified == pytest.approx(1.0, abs=1e-9)


# ------------------------------------------------------------- múltiplas comparações


FAMILY = [0.001, 0.008, 0.039, 0.041, 0.042, 0.6, 0.7, 0.8, 0.9, 0.99]


def test_bh_thresholds_and_survivors_on_a_synthetic_family() -> None:
    fam = adjust_family(FAMILY, q=0.05)
    assert fam.bh_threshold[0] == pytest.approx(0.005)
    assert fam.bh_threshold[-1] == pytest.approx(0.05)
    assert fam.bh_adjusted[:5] == pytest.approx((0.01, 0.04, 0.084, 0.084, 0.084))
    assert list(fam.bh_survives) == [True, True] + [False] * 8


def test_holm_is_stricter_than_bh_on_the_same_family() -> None:
    fam = adjust_family(FAMILY, q=0.05, alpha=0.05)
    assert fam.holm_adjusted[:5] == pytest.approx((0.01, 0.072, 0.312, 0.312, 0.312))
    assert list(fam.holm_survives) == [True] + [False] * 9
    assert all(h >= b for h, b in zip(fam.holm_adjusted, fam.bh_adjusted, strict=True))


def test_adjusted_p_is_monotone_in_the_raw_p() -> None:
    fam = adjust_family(FAMILY)
    order = sorted(range(len(FAMILY)), key=lambda i: FAMILY[i])
    for a, b in zip(order, order[1:], strict=False):
        assert fam.bh_adjusted[a] <= fam.bh_adjusted[b] + 1e-12
        assert fam.holm_adjusted[a] <= fam.holm_adjusted[b] + 1e-12


def test_a_single_hypothesis_family_is_unadjusted() -> None:
    fam = adjust_family([0.03], q=0.10, alpha=0.05)
    assert fam.bh_adjusted == (0.03,)
    assert fam.holm_adjusted == (0.03,)


def test_empty_family() -> None:
    assert adjust_family([]).p == ()


# ------------------------------------------------------------------ planalto vs pico


def _curve(values: list[float | None], y: np.ndarray, thresholds: list[float]):
    cid = [f"c{i}" for i in range(len(values))]
    ys = [float(v) for v in y]
    return threshold_curve(values, ys, cid, thresholds, min_per_side=5, reps=800, seed=9)


def test_plateau_is_detected_when_neighbouring_thresholds_agree() -> None:
    rng = np.random.default_rng(10)
    x = rng.uniform(0, 100, 400)
    y = np.where(x <= 50, 1.0, 0.0) + rng.normal(0, 0.05, 400)
    curve = _curve([float(v) for v in x], y, [20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
    shape = plateau_or_spike(curve)
    assert shape.form == "planalto"
    assert shape.longest_run >= 4


def test_spike_is_not_a_plateau() -> None:
    """Efeito não monótono: só o limiar mais baixo é positivo, os vizinhos invertem."""
    rng = np.random.default_rng(11)
    x = np.linspace(0.5, 99.5, 400)
    y = np.where(x <= 10, 1.0, np.where(x <= 40, -1.0, 1.0)) + rng.normal(0, 0.02, 400)
    curve = _curve([float(v) for v in x], y, [10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    shape = plateau_or_spike(curve)
    assert shape.form == "pico"
    assert shape.longest_run == 1


def test_no_effect_curve_is_absent_or_spike() -> None:
    rng = np.random.default_rng(12)
    x = rng.uniform(0, 100, 300)
    y = rng.normal(0, 1.0, 300)
    shape = plateau_or_spike(_curve([float(v) for v in x], y, [20.0, 40.0, 60.0, 80.0]))
    assert shape.form != "planalto"


def test_curve_marks_thresholds_without_sample_as_unevaluable() -> None:
    x: list[float | None] = [float(i) for i in range(100)]
    y = np.zeros(100)
    curve = _curve(x, y, [1.0, 50.0])
    assert curve[0].evaluable is False
    assert curve[1].evaluable is True
