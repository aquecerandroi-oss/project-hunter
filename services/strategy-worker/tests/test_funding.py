"""Funding per unit, and the honest ``null`` when it cannot be established.

SHADOW-LAB.md §3: funding is signed and charged per unit; *applicable but not
establishable* funding makes ``R_net`` null with a reason, and ``r_ex_funding``
is kept as a separate metric with its own coverage — never a silent zero.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_strategy_worker.funding import Settlement, resolve_funding

pytestmark = pytest.mark.unit

EIGHT_HOURS = 8 * 3600


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 5, hour, minute, tzinfo=UTC)


def _settlement(hour: int, rate: str, price: str | None = "100") -> Settlement:
    return Settlement(
        funding_time=_at(hour),
        rate=Decimal(rate),
        mark_price=None if price is None else Decimal(price),
    )


HISTORY = [_settlement(0, "0.0001"), _settlement(8, "0.0001"), _settlement(16, "0.0001")]


class TestResolveFunding:
    def test_a_trade_that_crosses_no_settlement_pays_nothing_and_is_available(self) -> None:
        reading = resolve_funding(HISTORY, entry_ts=_at(9), exit_ts=_at(11))
        assert reading.per_unit == Decimal("0")
        assert reading.reason is None
        assert reading.settlements == 0

    def test_a_crossed_settlement_is_charged_signed_per_unit(self) -> None:
        """rate 0.0001 x mark 100 = 0.01 paid by the long, per unit."""
        reading = resolve_funding(HISTORY, entry_ts=_at(15), exit_ts=_at(17))
        assert reading.per_unit == Decimal("0.01")
        assert reading.settlements == 1

    def test_a_negative_rate_is_received_by_the_long(self) -> None:
        history = [_settlement(0, "0.0001"), _settlement(8, "-0.0002"), _settlement(16, "0.0001")]
        reading = resolve_funding(history, entry_ts=_at(7), exit_ts=_at(9))
        assert reading.per_unit == Decimal("-0.02")

    def test_the_settlement_exactly_at_the_entry_is_not_charged(self) -> None:
        """The position is taken at that instant; the interval is ``(entry, exit]``."""
        reading = resolve_funding(HISTORY, entry_ts=_at(8), exit_ts=_at(9))
        assert reading.per_unit == Decimal("0")

    def test_a_settlement_the_schedule_expects_but_the_data_lacks_is_unavailable(self) -> None:
        """16:00 is due by the market's own 8h cadence and simply is not there."""
        history = [_settlement(0, "0.0001"), _settlement(8, "0.0001")]
        reading = resolve_funding(history, entry_ts=_at(15), exit_ts=_at(17))
        assert reading.per_unit is None
        assert reading.reason is not None
        assert reading.reason.startswith("funding_missing")

    def test_a_settlement_without_a_mark_price_cannot_be_valued(self) -> None:
        history = [_settlement(0, "0.0001"), _settlement(8, "0.0001"), _settlement(16, "1", None)]
        reading = resolve_funding(history, entry_ts=_at(15), exit_ts=_at(17))
        assert reading.per_unit is None
        assert reading.reason == "funding_price_missing"

    def test_without_two_observations_the_schedule_itself_is_unknown(self) -> None:
        reading = resolve_funding([_settlement(0, "0.0001")], entry_ts=_at(15), exit_ts=_at(17))
        assert reading.per_unit is None
        assert reading.reason == "funding_schedule_unknown"

    def test_an_empty_history_over_a_short_trade_is_still_unknown_not_zero(self) -> None:
        reading = resolve_funding([], entry_ts=_at(9), exit_ts=_at(11))
        assert reading.per_unit is None
        assert reading.reason == "funding_schedule_unknown"

    def test_the_cadence_comes_from_the_market_not_from_a_hardcoded_eight_hours(self) -> None:
        """A 4h-funding market: 12:00 is due and present, so the trade is valued."""
        history = [
            Settlement(_at(4), Decimal("0.0001"), Decimal("100")),
            Settlement(_at(8), Decimal("0.0001"), Decimal("100")),
            Settlement(_at(12), Decimal("0.0003"), Decimal("100")),
        ]
        reading = resolve_funding(history, entry_ts=_at(11), exit_ts=_at(13))
        assert reading.per_unit == Decimal("0.03")
        assert reading.interval_s == 4 * 3600

    def test_the_eight_hour_cadence_is_read_back(self) -> None:
        reading = resolve_funding(HISTORY, entry_ts=_at(9), exit_ts=_at(11))
        assert reading.interval_s == EIGHT_HOURS

    def test_a_settlement_off_the_grid_is_still_charged(self) -> None:
        """An exchange that settled at 20:00 outside its usual 8h cadence really
        charged the position; the estimated grid must not hide it (Astra, S2
        diff review, must-fix 5)."""
        history = [*HISTORY, _settlement(20, "0.0002")]
        reading = resolve_funding(history, entry_ts=_at(17), exit_ts=_at(21))
        assert reading.per_unit == Decimal("0.02")
        assert reading.settlements == 1

    def test_a_settlement_inside_an_ambiguous_exit_bar_is_not_establishable(self) -> None:
        """The exit is only known to be somewhere in its bar, so a settlement in
        that window may or may not have been paid."""
        reading = resolve_funding(
            HISTORY,
            entry_ts=_at(15),
            exit_ts=_at(16, 1),
            ambiguous_from=_at(16, 0) - timedelta(minutes=1),
        )
        assert reading.per_unit is None
        assert reading.reason == "funding_ambiguous_exit"

    def test_a_settlement_before_the_ambiguous_window_is_charged_normally(self) -> None:
        reading = resolve_funding(
            HISTORY, entry_ts=_at(15), exit_ts=_at(17), ambiguous_from=_at(16, 30)
        )
        assert reading.per_unit == Decimal("0.01")
