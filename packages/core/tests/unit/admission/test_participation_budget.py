"""The 60 s participation budget as arithmetic — RISK_ENGINE.md §4, DATABASE.md §18.5.

The database query only fetches rows; the algebra is here, so the sum that
decides whether a market's minute is already spent can be proved against
Astra's own walk-through of the contract (reserve 80 -> partial fill 30 ->
terminal cancellation of 50 -> new reservation of 70, ceiling 100, everything
inside the window) without a container.

Two properties the schema deliberately does **not** enforce and that are proved
here (``DATABASE.md`` §18.5, "o que não é DDL"): the balance of one reservation
never goes negative, and a negative balance of one reservation never pays for
another.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.admission.participation import ConsumptionRow, participation_used
from hunter_core.domain.enums import ParticipationEntryKind, ReservationState

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 6, 18, 30, tzinfo=UTC)
WINDOW = timedelta(seconds=60)


def row(
    kind: ParticipationEntryKind,
    notional: str,
    *,
    proposal: uuid.UUID,
    age_s: int = 0,
    state: ReservationState = ReservationState.HELD,
) -> ConsumptionRow:
    return ConsumptionRow(
        proposal_id=proposal,
        kind=kind,
        notional=Decimal(notional),
        occurred_at=NOW - timedelta(seconds=age_s),
        reservation_state=state,
    )


class TestTheWalkThroughOfTheContract:
    def test_a_reservation_holds_its_whole_notional(self) -> None:
        first = uuid.uuid4()
        rows = (row(ParticipationEntryKind.RESERVED, "80", proposal=first),)
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(80)

    def test_a_partial_fill_does_not_count_twice(self) -> None:
        """30 executed plus 50 still executable is 80, not 110."""
        first = uuid.uuid4()
        rows = (
            row(ParticipationEntryKind.RESERVED, "80", proposal=first),
            row(ParticipationEntryKind.EXECUTED, "30", proposal=first),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(80)

    def test_a_terminal_cancellation_returns_only_what_was_not_executed(self) -> None:
        first = uuid.uuid4()
        rows = (
            row(ParticipationEntryKind.RESERVED, "80", proposal=first),
            row(ParticipationEntryKind.EXECUTED, "30", proposal=first),
            row(ParticipationEntryKind.RELEASED, "50", proposal=first),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(30)

    def test_the_next_reservation_finds_the_minute_already_spent(self) -> None:
        first, second = uuid.uuid4(), uuid.uuid4()
        rows = (
            row(ParticipationEntryKind.RESERVED, "80", proposal=first),
            row(ParticipationEntryKind.EXECUTED, "30", proposal=first),
            row(ParticipationEntryKind.RELEASED, "50", proposal=first),
            row(ParticipationEntryKind.RESERVED, "70", proposal=second),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(100)


class TestOnlyTheExecutionGetsTheRollingCut:
    def test_an_execution_older_than_the_window_leaves_the_sum(self) -> None:
        spent = uuid.uuid4()
        rows = (
            row(
                ParticipationEntryKind.RESERVED,
                "40",
                proposal=spent,
                state=ReservationState.CONSUMED,
            ),
            row(
                ParticipationEntryKind.EXECUTED,
                "40",
                proposal=spent,
                age_s=61,
                state=ReservationState.CONSUMED,
            ),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(0)

    def test_a_reservation_still_held_does_not_age_out(self) -> None:
        """A commitment that is still executable is not forgiven by the clock."""
        standing = uuid.uuid4()
        rows = (row(ParticipationEntryKind.RESERVED, "40", proposal=standing, age_s=600),)
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(40)

    def test_the_execution_of_a_standing_reservation_is_counted_once(self) -> None:
        """Inside the window it is the executed term; the balance is what is left."""
        standing = uuid.uuid4()
        rows = (
            row(ParticipationEntryKind.RESERVED, "40", proposal=standing),
            row(ParticipationEntryKind.EXECUTED, "10", proposal=standing),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(40)

    def test_a_reservation_that_left_the_held_state_only_leaves_its_executions(self) -> None:
        expired = uuid.uuid4()
        rows = (
            row(
                ParticipationEntryKind.RESERVED,
                "40",
                proposal=expired,
                state=ReservationState.EXPIRED,
            ),
            row(
                ParticipationEntryKind.EXECUTED,
                "10",
                proposal=expired,
                state=ReservationState.EXPIRED,
            ),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(10)


class TestOneReservationNeverPaysForAnother:
    def test_a_balance_never_goes_negative(self) -> None:
        odd = uuid.uuid4()
        rows = (
            row(ParticipationEntryKind.RESERVED, "10", proposal=odd),
            row(ParticipationEntryKind.EXECUTED, "25", proposal=odd),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(25)

    def test_an_over_executed_reservation_does_not_discount_its_neighbour(self) -> None:
        odd, other = uuid.uuid4(), uuid.uuid4()
        rows = (
            row(ParticipationEntryKind.RESERVED, "10", proposal=odd),
            row(ParticipationEntryKind.EXECUTED, "25", proposal=odd),
            row(ParticipationEntryKind.RESERVED, "30", proposal=other),
        )
        assert participation_used(rows, cut=NOW - WINDOW) == Decimal(55)
