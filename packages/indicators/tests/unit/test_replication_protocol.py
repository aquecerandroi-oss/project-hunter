"""Os quatro blocos e o veredito (REPLICATION.md §3 e §5).

Cada cenário é aritmético: 40 dias × 5 resultados com o ciclo
``[1, 1, 1, -0.5, -0.5]`` dá expectancy 0,4 e PF 3 — dá para conferir no papel
antes de rodar. O que se prova aqui é a **regra**, não a estatística (essa está
em ``test_replication_bootstrap.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

from hunter_indicators.replication.protocol import (
    SIBLINGS_REQUIRED,
    STATUS_NONE,
    STATUS_PROMISING,
    STATUS_REAL,
    STATUS_REFUTED,
    STATUS_REPLICATING,
    SiblingArm,
    replication_report,
)
from hunter_indicators.replication.stats import (
    VERDICT_INCONCLUSIVE,
    VERDICT_REJECTED,
    VERDICT_VALIDATED,
    Outcome,
    PopulationStats,
    scoreboard_verdict,
)

from ..replication_builders import START, alternating, by_half, population

WINNER = alternating(["1", "1", "1", "-0.5", "-0.5"])
"""Expectancy 0,4 R; PF = 3 / 1 = 3."""

LOSER = alternating(["-1", "-1", "-1", "0.5", "0.5"])

PROMISING_AT = START + timedelta(days=20)
"""A metade da série: 20 dias antes viram a amostra, 20 depois são o bloco 1."""


RFor = Callable[[str, int], Decimal]


def _parent(r_for: RFor = WINNER, *, days: int = 40) -> list[Outcome]:
    return population(days=days, per_day=5, r_for=r_for)


def _sibling(k: int, r_for: RFor = WINNER, *, days: int = 16) -> SiblingArm:
    return SiblingArm(
        k=k, version=f"v{k + 1}", outcomes=population(days=days, per_day=4, r_for=r_for)
    )


def _ten(r_for: RFor = WINNER, *, negative: int = 0, immature: int = 0) -> list[SiblingArm]:
    arms: list[SiblingArm] = []
    for k in range(1, 11):
        if k <= negative:
            arms.append(_sibling(k, LOSER))
        elif k <= negative + immature:
            arms.append(_sibling(k, r_for, days=3))
        else:
            arms.append(_sibling(k, r_for))
    return arms


class TestScoreboardVerdict:
    def test_below_the_ruler_it_is_inconclusive(self) -> None:
        stats = PopulationStats.of(_parent(days=10))
        assert stats.evaluable == 50
        assert scoreboard_verdict(stats) == VERDICT_INCONCLUSIVE

    def test_mature_and_positive_is_validated(self) -> None:
        stats = PopulationStats.of(_parent())
        assert (stats.evaluable, stats.days) == (200, 40)
        assert stats.expectancy_r == Decimal("0.4000")
        assert stats.profit_factor == Decimal("3.0000")
        assert scoreboard_verdict(stats) == VERDICT_VALIDATED

    def test_mature_and_negative_is_rejected(self) -> None:
        stats = PopulationStats.of(_parent(LOSER))
        assert stats.expectancy_r == Decimal("-0.4000")
        assert scoreboard_verdict(stats) == VERDICT_REJECTED

    def test_a_null_profit_factor_is_not_greater_than_one(self) -> None:
        rows = population(days=40, per_day=5, r_for=alternating(["1"]))
        stats = PopulationStats.of(rows)
        assert stats.profit_factor is None
        assert stats.profit_factor_reason == "sem_perdas"
        assert scoreboard_verdict(stats) == VERDICT_REJECTED

    def test_three_hundred_outcomes_in_three_days_are_not_mature(self) -> None:
        rows = population(days=3, per_day=100, r_for=WINNER)
        stats = PopulationStats.of(rows)
        assert stats.evaluable == 300
        assert stats.mature() is False


class TestReplicationVerdict:
    def test_without_promising_at_there_is_no_protocol(self) -> None:
        report = replication_report(parent_outcomes=_parent(), promising_at=None, seed=1)
        assert report.status == STATUS_NONE
        assert report.parent_verdict == VERDICT_VALIDATED
        assert report.out_of_sample.reason == "sem_promising_at"

    def test_promising_without_siblings_is_promising(self) -> None:
        report = replication_report(parent_outcomes=_parent(), promising_at=PROMISING_AT, seed=1)
        assert report.status == STATUS_PROMISING
        assert report.out_of_sample.passed is True
        assert report.siblings.reason == "sem_irmas"

    def test_four_blocks_agreeing_make_it_real(self) -> None:
        report = replication_report(
            parent_outcomes=_parent(), promising_at=PROMISING_AT, siblings=_ten(), seed=11
        )
        assert report.status == STATUS_REAL
        assert report.reason is None
        assert report.out_of_sample.passed is True
        assert report.siblings.passed is True
        assert report.market_halves.passed is True
        assert report.bootstrap.passed is True
        assert report.siblings.detail["positive"] == 10

    def test_a_negative_out_of_sample_refutes(self) -> None:
        rows = _parent(days=20) + population(
            days=20, per_day=5, r_for=LOSER, start=PROMISING_AT + timedelta(days=1)
        )
        report = replication_report(
            parent_outcomes=rows, promising_at=PROMISING_AT, siblings=_ten(), seed=3
        )
        assert report.status == STATUS_REFUTED
        assert report.reason is not None and report.reason.startswith("out_of_sample:")

    def test_an_immature_out_of_sample_only_waits(self) -> None:
        late = START + timedelta(days=38)
        report = replication_report(
            parent_outcomes=_parent(), promising_at=late, siblings=_ten(), seed=3
        )
        assert report.status == STATUS_REPLICATING
        assert report.out_of_sample.passed is None
        assert "de 50 resultados" in (report.out_of_sample.reason or "")

    def test_four_mature_negative_siblings_make_the_majority_impossible(self) -> None:
        report = replication_report(
            parent_outcomes=_parent(),
            promising_at=PROMISING_AT,
            siblings=_ten(negative=4),
            seed=5,
        )
        assert report.status == STATUS_REFUTED
        assert "maioria_impossivel" in (report.siblings.reason or "")

    def test_three_negative_siblings_still_pass_with_seven_positive(self) -> None:
        report = replication_report(
            parent_outcomes=_parent(),
            promising_at=PROMISING_AT,
            siblings=_ten(negative=3),
            seed=5,
        )
        assert report.siblings.detail["positive"] == SIBLINGS_REQUIRED
        assert report.siblings.passed is True
        assert report.status == STATUS_REAL

    def test_immature_siblings_wait_instead_of_refuting(self) -> None:
        report = replication_report(
            parent_outcomes=_parent(),
            promising_at=PROMISING_AT,
            siblings=_ten(immature=5),
            seed=5,
        )
        assert report.siblings.passed is None
        assert report.status == STATUS_REPLICATING

    def test_a_negative_market_half_refutes(self) -> None:
        rows = population(days=40, per_day=5, r_for=by_half(["1", "1", "-0.5"], ["-1", "0.5"]))
        report = replication_report(
            parent_outcomes=rows, promising_at=PROMISING_AT, siblings=_ten(), seed=7
        )
        assert report.status == STATUS_REFUTED
        assert report.reason == "market_halves: metade_b_negativa"

    def test_a_small_population_refuses_the_bootstrap_and_waits(self) -> None:
        rows = population(days=16, per_day=1, r_for=alternating(["1", "-0.5"]))
        report = replication_report(
            parent_outcomes=rows,
            promising_at=START - timedelta(days=1),
            siblings=_ten(),
            seed=7,
        )
        assert report.bootstrap.passed is None
        assert report.bootstrap.reason == "amostra_insuficiente: 16 < 30"
        assert report.status == STATUS_REPLICATING

    def test_the_payload_carries_every_threshold_and_null_reason(self) -> None:
        report = replication_report(
            parent_outcomes=_parent(), promising_at=PROMISING_AT, siblings=_ten(), seed=11
        )
        payload = report.to_jsonable()
        assert payload["status"] == STATUS_REAL
        assert payload["promising_at"] == PROMISING_AT.isoformat()
        assert payload["siblings"]["required"] == SIBLINGS_REQUIRED
        assert payload["bootstrap"]["resamples"] == 1000
        assert payload["bootstrap"]["sign_test"]["method"] == "exact_binomial_v1"
        assert payload["market_halves"]["a"]["markets"] == 6
        assert isinstance(payload["parent"]["expectancy_r"], str)
