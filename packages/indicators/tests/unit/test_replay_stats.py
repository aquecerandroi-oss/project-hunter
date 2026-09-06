"""Paired contrasts: the estimand, the time-block resampling, Holm, and the
Lab's named metrics. Pure and deterministic by seed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from hunter_indicators.replay.metrics import lab_metrics
from hunter_indicators.replay.stats import (
    Pair,
    blocks_of,
    contrast,
    holm,
    paired_estimate,
    sign_flip_p,
)

pytestmark = pytest.mark.unit


def _pairs(*items: tuple[str, str]) -> list[Pair]:
    return [Pair(block=day, delta=Decimal(delta)) for day, delta in items]


def test_the_estimand_is_the_mean_per_signal_not_the_mean_of_daily_means() -> None:
    """Astra, design review: ``ΣS_b / Σn_b``. Two pairs on one day and one on
    another must not weigh the same as one day against one day."""
    pairs = _pairs(("2026-09-05", "1"), ("2026-09-05", "1"), ("2026-09-06", "-1"))
    assert paired_estimate(pairs) == Decimal("1") / Decimal("3")


def test_blocks_are_utc_days_of_the_entry() -> None:
    entry = datetime(2026, 9, 5, 23, 59, tzinfo=UTC)
    assert blocks_of(entry) == "2026-09-05"
    assert blocks_of(datetime(2026, 9, 6, 0, 1, tzinfo=UTC)) == "2026-09-06"
    assert date.fromisoformat(blocks_of(entry)).day == 5


def test_sign_flip_is_exact_and_bounded_below_by_two_over_two_to_the_b() -> None:
    """With three blocks all positive the smallest attainable two-sided p is
    ``2/8``; no amount of effect size can beat the block count."""
    pairs = _pairs(("d1", "5"), ("d2", "5"), ("d3", "5"))
    p, method, blocks = sign_flip_p(pairs)
    assert blocks == 3
    assert method == "sign_flip_exact"
    assert p == pytest.approx(0.25)


def test_sign_flip_with_one_block_cannot_reject_anything() -> None:
    p, _method, blocks = sign_flip_p(_pairs(("d1", "5"), ("d1", "7")))
    assert blocks == 1
    assert p == pytest.approx(1.0)


def test_holm_matches_the_textbook_case() -> None:
    raw = {"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.04, "e": 0.05}
    adjusted = holm(raw, family_size=5)
    assert adjusted["a"] == pytest.approx(0.05)
    assert adjusted["b"] == pytest.approx(0.08)
    assert adjusted["c"] == pytest.approx(0.09)
    assert adjusted["d"] == pytest.approx(0.09)
    assert adjusted["e"] == pytest.approx(0.09)


def test_holm_keeps_the_declared_family_size_even_when_fewer_tests_ran() -> None:
    """A partial ``--policies`` run must not silently lighten the penalty."""
    assert holm({"a": 0.01}, family_size=7)["a"] == pytest.approx(0.07)


def test_contrast_is_deterministic_for_a_seed_and_reports_its_blocks() -> None:
    pairs = _pairs(("d1", "0.2"), ("d2", "-0.1"), ("d3", "0.4"), ("d4", "0.1"))
    first = contrast("INV-B - base", pairs, seed=20260906, resamples=2000)
    second = contrast("INV-B - base", pairs, seed=20260906, resamples=2000)
    assert first == second
    assert first.n_pairs == 4
    assert first.blocks == 4
    assert first.estimate == paired_estimate(pairs)
    assert first.ci_low is not None and first.ci_high is not None
    assert first.estimate is not None
    assert first.ci_low <= float(first.estimate) <= first.ci_high


def test_contrast_refuses_an_interval_it_cannot_estimate() -> None:
    """One block is no replication: ``[effect, effect]`` would be fake precision."""
    single = contrast("x", _pairs(("d1", "0.2"), ("d1", "0.4")), seed=1, resamples=100)
    assert single.ci_low is None
    assert single.ci_reason == "single_block"
    empty = contrast("x", [], seed=1, resamples=100)
    assert empty.n_pairs == 0
    assert empty.estimate is None
    assert empty.ci_reason == "no_pairs"


def test_lab_metrics_use_the_names_of_the_plan() -> None:
    outcomes = [
        ("target", Decimal("1.4")),
        ("target", Decimal("1.3")),
        ("stop", Decimal("-1.05")),
        ("invalidated", Decimal("-0.2")),
        ("expired", None),
    ]
    m = lab_metrics(outcomes)
    assert m.target_rate_among_resolved == Decimal(2) / Decimal(3)
    assert m.resolved_touches == 3
    assert m.evaluable == 4
    assert m.net_win_rate == Decimal(2) / Decimal(4)
    assert m.expectancy_r == (
        Decimal("1.4") + Decimal("1.3") + Decimal("-1.05") + Decimal("-0.2")
    ) / Decimal(4)
    assert m.profit_factor_denominator == Decimal("1.25")
    assert m.profit_factor == Decimal("2.7") / Decimal("1.25")
    assert m.unevaluable == 1


def test_profit_factor_is_null_with_a_reason_when_nothing_lost() -> None:
    m = lab_metrics([("target", Decimal("1.4"))])
    assert m.profit_factor is None
    assert m.profit_factor_reason == "no_losses"
