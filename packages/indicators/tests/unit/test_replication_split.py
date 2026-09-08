"""Bloco 3 — metades de mercado por hash determinístico (REPLICATION.md §3.3)."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from hunter_indicators.replication.split import (
    HALF_A,
    HALF_B,
    MIN_MARKETS_PER_HALF,
    market_half,
    split_by_market,
)

from ..replication_builders import HALF_A_MARKETS, HALF_B_MARKETS, by_half, population


class TestMarketHalf:
    def test_it_is_the_low_bit_of_the_sha256(self) -> None:
        for symbol in (*HALF_A_MARKETS, *HALF_B_MARKETS):
            expected = HALF_A if hashlib.sha256(symbol.encode()).digest()[0] % 2 == 0 else HALF_B
            assert market_half(symbol) == expected

    def test_the_table_the_other_tests_read_is_the_real_one(self) -> None:
        assert {market_half(symbol) for symbol in HALF_A_MARKETS} == {HALF_A}
        assert {market_half(symbol) for symbol in HALF_B_MARKETS} == {HALF_B}

    def test_it_does_not_move_between_calls_or_processes(self) -> None:
        """Estabilidade é o ponto: ``hash()`` do Python é salgado e está proibido."""
        assert market_half("BTCUSDT") == market_half("BTCUSDT") == HALF_B

    def test_it_splits_a_large_universe_into_two_non_empty_halves(self) -> None:
        halves = [market_half(f"MKT{index}USDT") for index in range(200)]
        assert halves.count(HALF_A) > 50
        assert halves.count(HALF_B) > 50


class TestSplitByMarket:
    def test_two_positive_halves_pass(self) -> None:
        rows = population(days=20, per_day=5, r_for=by_half(["1", "-0.5"], ["1", "-0.5"]))
        result = split_by_market(rows)
        assert result.passed is True
        assert result.reason is None
        assert result.a.expectancy_r == Decimal("0.2500")
        assert result.b.expectancy_r == Decimal("0.2500")
        assert result.a.markets == len(HALF_A_MARKETS)
        assert result.b.markets == len(HALF_B_MARKETS)

    def test_a_mature_negative_half_refutes_the_block(self) -> None:
        rows = population(days=20, per_day=5, r_for=by_half(["1", "-0.5"], ["-1", "0.5"]))
        result = split_by_market(rows)
        assert result.passed is False
        assert result.reason == "metade_b_negativa"
        assert result.b.expectancy_r is not None and result.b.expectancy_r < 0

    def test_an_immature_half_waits_instead_of_refuting(self) -> None:
        rows = population(
            days=10,
            per_day=7,
            markets=(*HALF_A_MARKETS, "BTCUSDT"),
            r_for=by_half(["1"], ["1"]),
        )
        result = split_by_market(rows)
        assert result.a.mature is True
        assert result.passed is None
        assert result.reason == "metade_b_imatura"
        assert result.b.markets < MIN_MARKETS_PER_HALF
        assert result.b.mature is False
        assert "de 3 mercados" in (result.b.reason or "")

    def test_an_empty_population_is_immature_not_refuted(self) -> None:
        result = split_by_market([])
        assert result.passed is None
        assert result.a.evaluable == 0
        assert result.a.expectancy_r is None
