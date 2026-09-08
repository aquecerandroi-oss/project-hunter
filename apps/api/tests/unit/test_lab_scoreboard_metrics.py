"""Unit tests: the pure ``Decimal`` math behind ``/lab/shadow/scoreboard`` —
no IO, no Postgres. Brief T3.18.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_api.services.lab_scoreboard_metrics import compute_verdict, max_drawdown_r, worst_streak

pytestmark = pytest.mark.unit


class TestWorstStreak:
    def test_empty_series_is_zero(self) -> None:
        assert worst_streak([]) == 0

    def test_no_losses_is_zero(self) -> None:
        assert worst_streak([Decimal("1"), Decimal("0.5"), Decimal("0")]) == 0

    def test_single_losing_streak(self) -> None:
        assert worst_streak([Decimal("1"), Decimal("-1"), Decimal("-0.5"), Decimal("2")]) == 2

    def test_takes_the_longest_of_several_streaks(self) -> None:
        series = [
            Decimal("-1"),
            Decimal("1"),
            Decimal("-1"),
            Decimal("-1"),
            Decimal("-1"),
            Decimal("1"),
        ]
        assert worst_streak(series) == 3

    def test_a_zero_breaks_the_streak_like_a_win(self) -> None:
        series = [Decimal("-1"), Decimal("-1"), Decimal("0"), Decimal("-1")]
        assert worst_streak(series) == 2

    def test_trailing_streak_counts(self) -> None:
        series = [Decimal("1"), Decimal("-1"), Decimal("-1"), Decimal("-1")]
        assert worst_streak(series) == 3


class TestMaxDrawdownR:
    def test_empty_series_is_zero(self) -> None:
        assert max_drawdown_r([]) == Decimal("0.0000")

    def test_monotonically_rising_curve_has_no_drawdown(self) -> None:
        series = [Decimal("1"), Decimal("1"), Decimal("2")]
        assert max_drawdown_r(series) == Decimal("0.0000")

    def test_drop_from_a_peak_is_measured_from_that_peak(self) -> None:
        # cumulative: 2, 1, 3, 0.5 -> peak 3, trough 0.5 -> drawdown 2.5
        series = [Decimal("2"), Decimal("-1"), Decimal("2"), Decimal("-2.5")]
        assert max_drawdown_r(series) == Decimal("2.5000")

    def test_a_new_peak_after_a_drawdown_does_not_erase_the_earlier_one(self) -> None:
        # cumulative: 3, 1 (dd 2), 5 (new peak), 4 (dd 1) -> worst is still 2
        series = [Decimal("3"), Decimal("-2"), Decimal("4"), Decimal("-1")]
        assert max_drawdown_r(series) == Decimal("2.0000")

    def test_a_losing_series_never_recovering_its_start(self) -> None:
        series = [Decimal("-1"), Decimal("-1")]
        assert max_drawdown_r(series) == Decimal("2.0000")


class TestComputeVerdict:
    def test_not_mature_is_inconclusive_regardless_of_the_numbers(self) -> None:
        verdict = compute_verdict(
            mature=False, expectancy_r=Decimal("5"), profit_factor=Decimal("10"), pf_reason=None
        )
        assert verdict == "inconclusivo"

    def test_mature_positive_expectancy_and_pf_above_one_is_validada(self) -> None:
        verdict = compute_verdict(
            mature=True,
            expectancy_r=Decimal("0.1"),
            profit_factor=Decimal("1.5"),
            pf_reason=None,
        )
        assert verdict == "validada"

    def test_mature_non_positive_expectancy_is_reprovada_even_with_a_good_pf(self) -> None:
        verdict = compute_verdict(
            mature=True, expectancy_r=Decimal("0"), profit_factor=Decimal("5"), pf_reason=None
        )
        assert verdict == "reprovada"

    def test_mature_negative_expectancy_is_reprovada(self) -> None:
        verdict = compute_verdict(
            mature=True, expectancy_r=Decimal("-0.2"), profit_factor=Decimal("5"), pf_reason=None
        )
        assert verdict == "reprovada"

    def test_mature_positive_expectancy_but_pf_at_or_below_one_is_reprovada(self) -> None:
        verdict = compute_verdict(
            mature=True, expectancy_r=Decimal("0.1"), profit_factor=Decimal("1"), pf_reason=None
        )
        assert verdict == "reprovada"

    def test_mature_positive_expectancy_and_null_pf_with_no_losses_is_validada(self) -> None:
        """Zero losing outcomes (Σ losses = 0): the ratio is undefined in the
        strict sense but a losing side of zero cannot fail this rule."""
        verdict = compute_verdict(
            mature=True, expectancy_r=Decimal("0.5"), profit_factor=None, pf_reason="no_losses"
        )
        assert verdict == "validada"

    def test_mature_null_expectancy_is_reprovada_not_a_crash(self) -> None:
        """Declared unreachable in practice (maturity implies a non-empty R
        series) but the function must not raise on it."""
        verdict = compute_verdict(
            mature=True, expectancy_r=None, profit_factor=Decimal("2"), pf_reason=None
        )
        assert verdict == "reprovada"

    @pytest.mark.parametrize(
        ("mature", "expectancy_r", "profit_factor", "pf_reason", "expected"),
        [
            # immature: inconclusivo regardless of how good the numbers look
            pytest.param(
                False,
                Decimal("5"),
                Decimal("10"),
                None,
                "inconclusivo",
                id="immature-great-numbers",
            ),
            pytest.param(
                False, None, None, "no_losses", "inconclusivo", id="immature-null-pf-no-losses"
            ),
            # mature, PF null via no_losses (zero losing outcomes)
            pytest.param(
                True,
                Decimal("0.5"),
                None,
                "no_losses",
                "validada",
                id="mature-null-pf-no-losses-positive",
            ),
            pytest.param(
                True,
                Decimal("0"),
                None,
                "no_losses",
                "reprovada",
                id="mature-null-pf-no-losses-zero-expectancy",
            ),
            # mature, PF exactly at the threshold: the inequality is strict
            pytest.param(
                True, Decimal("0.1"), Decimal("1"), None, "reprovada", id="mature-pf-exactly-one"
            ),
            pytest.param(
                True,
                Decimal("0.1"),
                Decimal("1.0001"),
                None,
                "validada",
                id="mature-pf-just-above-one",
            ),
            # mature, only losses in the population (negative expectancy, no PF null reason applies)
            pytest.param(
                True, Decimal("-2"), Decimal("0"), None, "reprovada", id="mature-only-losses"
            ),
            # mature, positive expectancy and PF above one
            pytest.param(
                True,
                Decimal("0.3"),
                Decimal("2"),
                None,
                "validada",
                id="mature-positive-and-pf-above-one",
            ),
        ],
    )
    def test_borderline_matrix(
        self,
        mature: bool,
        expectancy_r: Decimal | None,
        profit_factor: Decimal | None,
        pf_reason: str | None,
        expected: str,
    ) -> None:
        verdict = compute_verdict(
            mature=mature,
            expectancy_r=expectancy_r,
            profit_factor=profit_factor,
            pf_reason=pf_reason,
        )
        assert verdict == expected
