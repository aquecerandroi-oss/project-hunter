"""Statistics of the WIN family — known values and synthetic families (tests only)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from infra.research.b3.stats_b3 import (
    CI_TAIL,
    first_half_mask,
    half_cut,
    holm,
    monthly_bootstrap_ci,
    side_permutation_p,
)

pytestmark = pytest.mark.unit


def test_family_tail_is_bonferroni_over_three() -> None:
    assert CI_TAIL == pytest.approx(0.05 / 3 / 2)


def test_bootstrap_of_a_constant_is_the_constant() -> None:
    lo, hi = monthly_bootstrap_ci(np.full(40, 2.5), np.repeat(np.arange(4), 10), reps=500, seed=1)
    assert lo == pytest.approx(2.5) and hi == pytest.approx(2.5)


def test_bootstrap_resamples_whole_months_trade_weighted() -> None:
    # month 0: one trade of +100; month 1: nine trades of 0 → resampled means live in
    # {0, 10, 100}/… and the CI must contain the trade-weighted mean 10, not the mean of means 50
    values = np.array([100.0] + [0.0] * 9)
    months = np.array([0] + [1] * 9)
    lo, hi = monthly_bootstrap_ci(values, months, reps=4000, seed=3)
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(100.0)
    assert lo <= values.mean() <= hi


def test_bootstrap_with_no_trades_is_not_finite() -> None:
    lo, hi = monthly_bootstrap_ci(np.array([]), np.array([]), reps=10, seed=1)
    assert np.isnan(lo) and np.isnan(hi)


def test_permutation_finds_a_planted_directional_edge() -> None:
    rng = np.random.default_rng(7)
    n = 600
    move = rng.normal(0, 20, n)
    sides_buy = rng.random(n) < 0.5
    # the rule picks the side of the move 60 % of the time → edge
    chose_buy = np.where(rng.random(n) < 0.6, move > 0, move <= 0)
    y_rule = np.where(chose_buy, move, -move)
    strata = np.repeat(np.arange(12), n // 12)
    p = side_permutation_p(y_rule, -y_rule, chose_buy, strata, reps=2000, seed=11)
    assert p < 0.01
    # a rule with no information: sides independent of the move
    y_null = np.where(sides_buy, move, -move)
    p_null = side_permutation_p(y_null, -y_null, sides_buy, strata, reps=2000, seed=11)
    assert p_null > 0.05


def test_permutation_keeps_the_count_of_buys_per_stratum() -> None:
    # all trades in stratum 0 are buys: shuffling inside it cannot change anything → p = 1
    y = np.array([5.0, 6.0, 7.0])
    p = side_permutation_p(
        y, -y, np.array([True, True, True]), np.array([0, 0, 0]), reps=200, seed=1
    )
    assert p == pytest.approx(1.0)


def test_first_half_takes_the_first_ceil_half_of_the_dates() -> None:
    dates = [date(2024, 1, d) for d in (2, 2, 3, 4, 5, 5, 8)]
    # 5 distinct dates → first 3 (02, 03, 04) are the first half
    assert first_half_mask(dates).tolist() == [True, True, True, True, False, False, False]


def test_holm_reuses_the_research_family_adjustment() -> None:
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_bootstrap_keeps_months_with_operations_but_no_outcome_as_empty_blocks() -> None:
    values = np.array([10.0, 10.0])
    months = np.array([1, 2])
    lo, hi = monthly_bootstrap_ci(values, months, blocks=np.array([1, 2, 3]), reps=500, seed=2)
    assert lo == pytest.approx(10.0) and hi == pytest.approx(10.0)
    with pytest.raises(ValueError, match="universe"):
        monthly_bootstrap_ci(values, months, blocks=np.array([1]), reps=10, seed=2)


def test_half_cut_is_shared_between_populations() -> None:
    plan_dates = [date(2024, 1, d) for d in (2, 3, 4, 5, 8)]
    cut = half_cut(plan_dates)
    assert cut == date(2024, 1, 4)
    ok_dates = [date(2024, 1, d) for d in (2, 3, 5)]  # the plan of 04/01 was censored
    assert first_half_mask(ok_dates, cut).tolist() == [True, True, False]
