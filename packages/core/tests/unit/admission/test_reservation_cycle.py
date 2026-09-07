"""One reservation, one cycle — DATABASE.md §18.3 ("invariante da T3.12, com teste").

The schema keeps a single reservation axis per proposal; it does **not** stop a
writer from moving that axis backwards with an ``UPDATE``. Keeping the cycle
single is this service's job, and this is the guard, proved without a database
so the rule is readable in one place.

The reserved amounts and the reservation's own instant are also decided here:
what a purchase holds of the **cash** is the notional plus the fees the sizing
already assumed (``entry_cash_multiplier``), never the bare notional.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.admission.reservation import (
    RESERVATION_TTL,
    ReservationCycleClosed,
    next_state,
    reserved_cash_for,
)
from hunter_core.domain.enums import ReservationState
from hunter_core.strategies.envelope import AssumedCosts

pytestmark = pytest.mark.unit

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)


class TestTheCycleOnlyEverCloses:
    @pytest.mark.parametrize(
        "target",
        [ReservationState.CONSUMED, ReservationState.RELEASED, ReservationState.EXPIRED],
    )
    def test_a_standing_reservation_may_reach_any_terminal_state(
        self, target: ReservationState
    ) -> None:
        assert next_state(ReservationState.HELD, target) is target

    @pytest.mark.parametrize(
        "current",
        [ReservationState.CONSUMED, ReservationState.RELEASED, ReservationState.EXPIRED],
    )
    def test_a_closed_cycle_never_reopens(self, current: ReservationState) -> None:
        with pytest.raises(ReservationCycleClosed, match=current.value):
            next_state(current, ReservationState.HELD)

    def test_a_closed_cycle_does_not_move_sideways_either(self) -> None:
        with pytest.raises(ReservationCycleClosed, match="consumed"):
            next_state(ReservationState.CONSUMED, ReservationState.RELEASED)

    def test_a_proposal_that_never_reserved_has_nothing_to_close(self) -> None:
        with pytest.raises(ReservationCycleClosed, match="none"):
            next_state(ReservationState.NONE, ReservationState.EXPIRED)

    def test_held_to_held_is_refused_rather_than_silently_renewed(self) -> None:
        """Renewing the tenure would be a second 30 s window nobody decided."""
        with pytest.raises(ReservationCycleClosed, match="held"):
            next_state(ReservationState.HELD, ReservationState.HELD)


class TestWhatAReservationHolds:
    def test_the_cash_held_is_the_notional_plus_the_assumed_fees(self) -> None:
        """The mirror of the engine's cash ceiling: (1+deslocamento)(1+fee)."""
        assert reserved_cash_for(Decimal(400), COSTS) == Decimal(400) * Decimal("1.00100024")

    def test_the_cash_held_is_never_below_the_notional(self) -> None:
        free = AssumedCosts(
            spread_bps=Decimal(0),
            slippage_bps=Decimal(0),
            fee_bps=Decimal(0),
            max_entry_delay_s=60,
        )
        assert reserved_cash_for(Decimal(100), free) == Decimal(100)


class TestTheTenureIsThirtySeconds:
    def test_the_reservation_expires_thirty_seconds_after_the_decision(self) -> None:
        """PIPELINE.md §5: an approved proposal with no order dies after 30 s."""
        assert RESERVATION_TTL == timedelta(seconds=30)
        now = datetime(2026, 9, 6, 18, 30, tzinfo=UTC)
        assert now + RESERVATION_TTL == datetime(2026, 9, 6, 18, 30, 30, tzinfo=UTC)
