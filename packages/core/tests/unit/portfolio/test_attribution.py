"""The BRL attribution and the opening conversion — pure arithmetic, no database.

Two things are proved here and nowhere else:

- the attribution's **currency-translation term is measured on the patrimony**,
  not on the cash. Astra's arithmetic check of 2026-09-06
  (``.claude/state/dialogue-M3.md``, "Astra (rodada 1)") put R$8.200 of the
  identity on the floor with cash in that term, and the reconstruction of that
  scenario is a test rather than a memory;
- the opening conversion satisfies the schema's own money identity
  (``portfolio_currency_anchor.conversion_is_exact``) **after** Postgres rounds
  the stored scale, which is a stronger statement than "the division was
  floored".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.portfolio.attribution import (
    OPENING_ROUNDING_POLICY,
    QUANTUM,
    attribute_brl,
    convert_opening,
)

pytestmark = pytest.mark.unit


class TestTheAstraScenario:
    """Capital 20.000, equity 20.200, cash 12.000, F0 = 5, Ft = 6."""

    def _attribution(self) -> object:
        return attribute_brl(
            equity=Decimal(20200),
            credited=Decimal(20000),
            opening_rate=Decimal(5),
            current_rate=Decimal(6),
        )

    def test_operational_is_the_usdt_result_at_the_opening_rate(self) -> None:
        assert attribute_brl(
            equity=Decimal(20200),
            credited=Decimal(20000),
            opening_rate=Decimal(5),
            current_rate=Decimal(6),
        ).operational_brl == Decimal(1000)

    def test_currency_term_is_measured_on_the_whole_patrimony(self) -> None:
        assert attribute_brl(
            equity=Decimal(20200),
            credited=Decimal(20000),
            opening_rate=Decimal(5),
            current_rate=Decimal(6),
        ).currency_brl == Decimal(20200)

    def test_the_identity_closes_exactly(self) -> None:
        result = attribute_brl(
            equity=Decimal(20200),
            credited=Decimal(20000),
            opening_rate=Decimal(5),
            current_rate=Decimal(6),
        )
        assert result.equity_brl == Decimal(121200)
        assert result.total_brl == result.equity_brl - Decimal(100000)
        assert result.opening_brl + result.total_brl == result.equity_brl

    def test_using_cash_in_the_currency_term_loses_8200_reais(self) -> None:
        """The number Astra measured. Reproduced, so nobody re-derives it."""
        result = attribute_brl(
            equity=Decimal(20200),
            credited=Decimal(20000),
            opening_rate=Decimal(5),
            current_rate=Decimal(6),
        )
        cash = Decimal(12000)
        wrong = result.opening_brl + result.operational_brl + cash * (Decimal(6) - Decimal(5))
        assert wrong - result.equity_brl == Decimal(-8200)


class TestTheAttributionIdentity:
    @pytest.mark.parametrize(
        ("equity", "credited", "opening_rate", "current_rate"),
        [
            (Decimal("19999.9999999999"), Decimal("19999.9999999999"), Decimal(5), Decimal(5)),
            (Decimal("18321.4400000000"), Decimal("20000"), Decimal("5.4321"), Decimal("5.1")),
            (Decimal("31000.5"), Decimal("20000"), Decimal("5.4321"), Decimal("6.9999999999")),
        ],
    )
    def test_total_is_always_equity_now_minus_capital_then(
        self, equity: Decimal, credited: Decimal, opening_rate: Decimal, current_rate: Decimal
    ) -> None:
        result = attribute_brl(
            equity=equity,
            credited=credited,
            opening_rate=opening_rate,
            current_rate=current_rate,
        )
        assert result.total_brl == equity * current_rate - credited * opening_rate
        assert result.operational_brl + result.currency_brl == result.total_brl

    def test_a_flat_rate_puts_the_whole_result_in_the_operational_term(self) -> None:
        result = attribute_brl(
            equity=Decimal(21000),
            credited=Decimal(20000),
            opening_rate=Decimal("5.4321"),
            current_rate=Decimal("5.4321"),
        )
        assert result.currency_brl == Decimal(0)
        assert result.operational_brl == Decimal(1000) * Decimal("5.4321")

    def test_a_loss_with_a_rising_rate_keeps_the_two_terms_apart(self) -> None:
        result = attribute_brl(
            equity=Decimal(19000),
            credited=Decimal(20000),
            opening_rate=Decimal(5),
            current_rate=Decimal(6),
        )
        assert result.operational_brl == Decimal(-5000)
        assert result.currency_brl == Decimal(19000)
        assert result.equity_brl == Decimal(114000)

    def test_a_non_positive_rate_is_refused(self) -> None:
        with pytest.raises(ValueError, match="rate"):
            attribute_brl(
                equity=Decimal(1),
                credited=Decimal(1),
                opening_rate=Decimal(0),
                current_rate=Decimal(1),
            )


class TestTheOpeningConversion:
    def test_the_directive_number_at_a_clean_rate(self) -> None:
        conversion = convert_opening(Decimal(100000), Decimal(5))
        assert conversion.credited_amount == Decimal("20000.0000000000")
        assert conversion.conversion_residual == Decimal(0)
        assert conversion.rounding_policy == OPENING_ROUNDING_POLICY

    def test_the_credit_is_floored_never_rounded_up(self) -> None:
        """R$100.000 at 3.5 is 28571,428571428571...; the wallet gets the floor."""
        conversion = convert_opening(Decimal(100000), Decimal("3.5"))
        assert conversion.credited_amount == Decimal("28571.4285714285")
        assert conversion.credited_amount * Decimal("3.5") < Decimal(100000)

    @pytest.mark.parametrize(
        "rate",
        [
            Decimal(5),
            Decimal("3.5"),
            Decimal("5.4321"),
            Decimal("5.4823000001"),
            Decimal("0.0000000007"),
            Decimal("6.1803398875"),
        ],
    )
    def test_the_stored_identity_closes_under_postgres_rounding(self, rate: Decimal) -> None:
        """``round(credited * rate + residual, 10) = round(origin, 10)``.

        Postgres rounds ``numeric`` halves *away from zero*, and the anchor's
        CHECK is written on the rounded sum, so this is the only formulation
        that decides whether the INSERT is accepted.
        """
        origin = Decimal(100000)
        conversion = convert_opening(origin, rate)
        total = conversion.credited_amount * rate + conversion.conversion_residual
        assert _round_half_up(total, 10) == _round_half_up(origin, 10)

    def test_the_residual_is_never_negative_and_stays_inside_one_quantum(self) -> None:
        conversion = convert_opening(Decimal(100000), Decimal("3.5"))
        exact = Decimal(100000) - conversion.credited_amount * Decimal("3.5")
        assert conversion.conversion_residual >= 0
        assert abs(conversion.conversion_residual - exact) <= QUANTUM / 2

    def test_a_rate_so_large_it_credits_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="credits nothing"):
            convert_opening(Decimal(100000), Decimal("1e16"))

    @pytest.mark.parametrize(
        ("origin", "rate"), [(Decimal(0), Decimal(5)), (Decimal(1), Decimal(0))]
    )
    def test_non_positive_inputs_are_refused(self, origin: Decimal, rate: Decimal) -> None:
        with pytest.raises(ValueError):
            convert_opening(origin, rate)


def _round_half_up(value: Decimal, places: int) -> Decimal:
    """Postgres' ``round(numeric, int)``: ties go away from zero."""
    from decimal import ROUND_HALF_UP

    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
