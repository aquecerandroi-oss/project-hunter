"""Bloco 4 — bootstrap, bootstrap por dias e teste de sinal (REPLICATION.md §3.4).

Três provas que o protocolo depende: uma moeda honesta **não** passa, uma
distribuição deslocada passa, e abaixo de 30 observações a função recusa com o
motivo escrito em vez de devolver um intervalo que alguém citaria.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np

from hunter_indicators.replication.bootstrap import (
    MIN_SAMPLE,
    bootstrap_mean_ci,
    cluster_bootstrap_mean_ci,
    sign_test,
)


def _coin(seed: int, n: int = 200) -> list[Decimal]:
    """Uma moeda honesta em R: ±1 com a mesma probabilidade, média verdadeira 0."""
    rng = np.random.Generator(np.random.PCG64(seed))
    return [Decimal(1) if bit else Decimal(-1) for bit in rng.integers(0, 2, size=n)]


def _shifted(seed: int, n: int = 200, shift: str = "0.5") -> list[Decimal]:
    """A mesma moeda somada a uma vantagem real de ``shift`` R por operação."""
    return [value + Decimal(shift) for value in _coin(seed, n)]


class TestBootstrapCi:
    def test_it_refuses_below_the_minimum_sample_with_a_reason(self) -> None:
        result = bootstrap_mean_ci([Decimal("1")] * (MIN_SAMPLE - 1), seed=7)
        assert result.ok is False
        assert result.refused_reason == "amostra_insuficiente: 29 < 30"
        assert result.ci_low is None and result.ci_high is None
        assert result.excludes_zero is False

    def test_thirty_observations_are_enough(self) -> None:
        result = bootstrap_mean_ci([Decimal("1")] * MIN_SAMPLE, seed=7)
        assert result.ok is True
        assert result.n == 30

    def test_a_fair_coin_almost_never_passes(self) -> None:
        """Nível nominal 5 %: em 40 amostras honestas, poucas excluem o zero.

        O limite do teste (<= 6) é folgado de propósito — o que ele prova é que
        o bloco 4 **não** é uma passagem automática, não o nível exato.
        """
        passes = sum(
            1 for seed in range(40) if bootstrap_mean_ci(_coin(seed), seed=seed).excludes_zero
        )
        assert passes <= 6, f"moeda honesta passou {passes} de 40 vezes"

    def test_a_shifted_distribution_always_passes(self) -> None:
        for seed in range(20):
            result = bootstrap_mean_ci(_shifted(seed), seed=seed)
            assert result.excludes_zero is True
            assert result.ci_low is not None and result.ci_low > 0
            assert result.mean is not None and abs(result.mean - Decimal("0.5")) < Decimal("0.2")

    def test_a_negative_distribution_excludes_zero_from_below(self) -> None:
        values = [-value for value in _shifted(3)]
        result = bootstrap_mean_ci(values, seed=3)
        assert result.excludes_zero is True
        assert result.ci_high is not None and result.ci_high < 0

    def test_the_same_seed_reproduces_the_interval(self) -> None:
        sample = _shifted(11)
        first = bootstrap_mean_ci(sample, seed=99)
        second = bootstrap_mean_ci(sample, seed=99)
        third = bootstrap_mean_ci(sample, seed=100)
        assert (first.ci_low, first.ci_high) == (second.ci_low, second.ci_high)
        assert (third.ci_low, third.ci_high) != (first.ci_low, first.ci_high)

    def test_the_mean_is_the_sample_mean(self) -> None:
        values = [Decimal("0.5")] * 20 + [Decimal("-0.5")] * 20
        result = bootstrap_mean_ci(values, seed=1)
        assert result.mean == Decimal("0")
        assert result.excludes_zero is False


class TestClusterBootstrap:
    def _days(self, n: int, days: int) -> list[str]:
        return [f"2026-01-{(index % days) + 1:02d}" for index in range(n)]

    def test_it_refuses_when_there_are_too_few_days(self) -> None:
        values = [Decimal("1")] * 60
        result = cluster_bootstrap_mean_ci(values, self._days(60, 3), seed=5)
        assert result.ok is False
        assert result.refused_reason == "grupos_insuficientes: 3 < 5"

    def test_it_is_wider_than_the_iid_interval_when_days_carry_the_signal(self) -> None:
        """Dias inteiros bons e dias inteiros ruins: a dependência é real e o
        intervalo por dias tem de pagar por ela (KB-0051)."""
        values: list[Decimal] = []
        days: list[str] = []
        for day in range(20):
            good = day % 2 == 0
            for _ in range(10):
                values.append(Decimal("1.2") if good else Decimal("-0.8"))
                days.append(f"2026-02-{day + 1:02d}")
        iid = bootstrap_mean_ci(values, seed=4)
        clustered = cluster_bootstrap_mean_ci(values, days, seed=4)
        assert iid.ci_low is not None and clustered.ci_low is not None
        assert iid.ci_high is not None and clustered.ci_high is not None
        assert (clustered.ci_high - clustered.ci_low) > (iid.ci_high - iid.ci_low)
        assert clustered.groups == 20
        assert clustered.mean == iid.mean

    def test_it_refuses_mismatched_lengths(self) -> None:
        try:
            cluster_bootstrap_mean_ci([Decimal("1")] * 30, ["a"] * 29, seed=1)
        except ValueError as exc:
            assert "mesmo comprimento" in str(exc)
        else:  # pragma: no cover - a falha é o próprio teste
            raise AssertionError("aceitou tamanhos diferentes")


class TestSignTest:
    def test_eight_of_ten_positives_has_the_exact_binomial_p(self) -> None:
        # 2 * P(X <= 2 | n = 10, p = 1/2) = 2 * (1 + 10 + 45) / 1024 = 0.109375
        values = [Decimal("1")] * 8 + [Decimal("-1")] * 2
        result = sign_test(values)
        assert (result.positives, result.negatives, result.zeros) == (8, 2, 0)
        assert result.p_value == Decimal("0.1094")
        assert result.method == "exact_binomial_v1"

    def test_zeros_are_excluded_from_the_denominator(self) -> None:
        values = [Decimal("1")] * 8 + [Decimal("-1")] * 2 + [Decimal("0")] * 5
        result = sign_test(values)
        assert (result.positives, result.negatives, result.zeros) == (8, 2, 5)
        assert result.p_value == Decimal("0.1094")

    def test_a_balanced_sample_has_p_one(self) -> None:
        result = sign_test([Decimal("1")] * 10 + [Decimal("-1")] * 10)
        assert result.p_value == Decimal("1")

    def test_a_sample_without_signs_refuses(self) -> None:
        result = sign_test([Decimal("0")] * 5)
        assert result.p_value is None
        assert result.refused_reason == "sem_amostra_com_sinal"
