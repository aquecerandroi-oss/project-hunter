"""PortfolioState: aggregates, the São Paulo day and the monotonic peak."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hunter_risk.exposure import advance_peak, sao_paulo_day_start_utc

from .factories import NOW, market, pending, portfolio, position

pytestmark = pytest.mark.unit


class TestSaoPauloDay:
    def test_returns_midnight_in_sao_paulo_expressed_in_utc(self) -> None:
        assert sao_paulo_day_start_utc(NOW) == datetime(2026, 9, 6, 3, 0, tzinfo=UTC)

    def test_an_instant_before_local_midnight_belongs_to_the_previous_day(self) -> None:
        # 02:00 UTC is 23:00 of the previous day in São Paulo.
        assert sao_paulo_day_start_utc(datetime(2026, 9, 6, 2, 0, tzinfo=UTC)) == datetime(
            2026, 9, 5, 3, 0, tzinfo=UTC
        )

    def test_local_midnight_is_its_own_day_start(self) -> None:
        start = datetime(2026, 9, 6, 3, 0, tzinfo=UTC)
        assert sao_paulo_day_start_utc(start) == start

    def test_a_naive_instant_is_refused_rather_than_assumed_utc(self) -> None:
        with pytest.raises(ValueError, match="naive"):
            sao_paulo_day_start_utc(datetime(2026, 9, 6, 3, 0))  # noqa: DTZ001

    def test_it_reads_no_clock(self) -> None:
        # Same argument, same answer, whenever it is called.
        assert sao_paulo_day_start_utc(NOW) == sao_paulo_day_start_utc(NOW)


class TestPeak:
    def test_peak_never_goes_down(self) -> None:
        assert advance_peak(Decimal("100"), Decimal("90")) == Decimal("100")

    def test_peak_follows_a_new_high(self) -> None:
        assert advance_peak(Decimal("100"), Decimal("110")) == Decimal("110")

    def test_a_state_whose_peak_is_below_its_equity_is_a_bug_not_a_state(self) -> None:
        with pytest.raises(ValidationError, match="peak_equity"):
            portfolio(equity=Decimal("100"), peak_equity=Decimal("90"))


class TestAggregates:
    def test_exposure_counts_open_positions_and_pending_entries(self) -> None:
        state = portfolio(
            open_positions=(position(notional=Decimal("1000")),),
            pending_entries=(pending(reserved_notional=Decimal("500")),),
        )
        assert state.total_exposure == Decimal("1500")
        assert state.exposure_for_asset("SOL") == Decimal("1500")
        assert state.exposure_for_asset("ETH") == Decimal("0")

    def test_slots_count_pending_entries_too(self) -> None:
        state = portfolio(
            open_positions=(position(), position(market=market("ETHUSDT", "ETH"))),
            pending_entries=(pending(market=market("BTCUSDT", "BTC")),),
        )
        assert state.slots_used == 3

    def test_committed_planned_risk_sums_open_and_pending(self) -> None:
        state = portfolio(
            open_positions=(position(planned_risk_quote=Decimal("50")),),
            pending_entries=(pending(planned_risk_quote=Decimal("25")),),
        )
        assert state.committed_planned_risk == Decimal("75")

    def test_beta_exposure_uses_the_absolute_beta(self) -> None:
        state = portfolio(
            open_positions=(
                position(notional=Decimal("1000"), beta_btc=Decimal("-1.2")),
                position(
                    market=market("ETHUSDT", "ETH"),
                    notional=Decimal("500"),
                    beta_btc=Decimal("0.8"),
                ),
            )
        )
        assert state.beta_exposure() == Decimal("1600")

    def test_a_position_without_a_validated_beta_makes_the_aggregate_unknown(self) -> None:
        state = portfolio(open_positions=(position(beta_btc=None),))
        assert state.beta_exposure() is None

    def test_assets_held_covers_open_and_pending(self) -> None:
        state = portfolio(
            open_positions=(position(),),
            pending_entries=(pending(market=market("ETHUSDT", "ETH")),),
        )
        assert state.assets_held == frozenset({"SOL", "ETH"})


class TestDailyResult:
    def test_daily_pnl_is_realised_plus_unrealised_minus_costs(self) -> None:
        state = portfolio(
            daily_realized_pnl=Decimal("-100"),
            daily_unrealized_pnl=Decimal("-50"),
            daily_costs=Decimal("20"),
        )
        assert state.daily_pnl == Decimal("-170")

    def test_daily_loss_pct_is_measured_against_the_equity_at_the_day_start(self) -> None:
        state = portfolio(equity=Decimal("19830"), daily_realized_pnl=Decimal("-170"))
        # day_start_equity defaults to the same 19830 in the factory; set it explicitly.
        state = state.model_copy(update={"day_start_equity": Decimal("20000")})
        assert state.daily_loss_pct == Decimal("0.0085")

    def test_a_profitable_day_is_a_loss_of_zero_never_a_negative_loss(self) -> None:
        state = portfolio(daily_realized_pnl=Decimal("500"))
        assert state.daily_loss_pct == Decimal("0")

    def test_drawdown_is_measured_from_the_historical_peak(self) -> None:
        state = portfolio(equity=Decimal("18400"), peak_equity=Decimal("20000"))
        assert state.drawdown_pct == Decimal("0.08")

    def test_at_the_peak_the_drawdown_is_zero(self) -> None:
        assert portfolio().drawdown_pct == Decimal("0")


class TestConsistency:
    def test_the_day_anchor_must_be_the_sao_paulo_day_of_as_of(self) -> None:
        with pytest.raises(ValidationError, match="day_start_utc"):
            portfolio(day_start_utc=NOW - timedelta(days=2))

    def test_a_float_never_becomes_equity(self) -> None:
        with pytest.raises((ValidationError, TypeError), match="float"):
            portfolio(equity=20000.0)
