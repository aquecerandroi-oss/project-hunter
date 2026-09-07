"""T3.5b items 4, 5 and 6 — what the loops say, and when they run. Unit only.

Three things that need no database and no Docker, because none of them is about
the wallet:

- an unreadable filed request is **named once**, not once per second;
- a degraded protection's backoff doubles from 1 s and stops at 60 s;
- the mark-to-market runs on the minute grid **and** just before the São Paulo
  turn, so ``day_opening_observation`` always finds a point within the 60 s the
  daily reference accepts.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from structlog.testing import capture_logs

from hunter_core.risk.daily import DAY_OPENING_MAX_LAG_S
from hunter_execution_worker.admission_cycle import PendingRow, report_unreadable
from hunter_execution_worker.schedule import (
    TURN_MARGIN_S,
    next_grid_tick,
    next_mtm_tick,
    next_sao_paulo_turn,
)
from hunter_execution_worker.triggering import BACKOFF_MAX_S, BACKOFF_START_S, DegradedRetries
from hunter_execution_worker.wallet import WalletRef

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)
TURN = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
"""Midnight of 2026-09-07 in America/Sao_Paulo, which is UTC-3 all year."""

WORK_S = 1.5
"""How long one MTM pass takes, database included. It is the number that turns
a 60 s cadence into a 61,5 s period when the sleep comes *after* the work."""


def _wallet() -> WalletRef:
    return WalletRef(uuid.uuid4(), uuid.uuid4())


def _pending(created_at: datetime = NOW) -> PendingRow:
    proposal_id = uuid.uuid4()
    return PendingRow(
        proposal_id=proposal_id,
        market_id=uuid.uuid4(),
        idempotency_key=f"manual:{proposal_id}",
        request_digest=None,
        created_at=created_at,
    )


def _geometry_lines(logs: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return [line for line in logs if line.get("event") == "pending_request_without_geometry"]


class TestAnUnreadableRequestIsNamedOncePerRow:
    def test_a_thousand_cycles_over_the_same_row_write_one_line(self) -> None:
        wallet, row = _wallet(), _pending()
        reported: set[uuid.UUID] = set()

        with capture_logs() as logs:
            for _ in range(1000):
                assert report_unreadable(wallet, [row], reported=reported) == 1

        assert len(_geometry_lines(logs)) == 1
        assert _geometry_lines(logs)[0]["proposal_id"] == str(row.proposal_id)

    def test_a_new_filed_row_is_named_when_it_appears(self) -> None:
        wallet, first = _wallet(), _pending()
        second = _pending(NOW + timedelta(seconds=10))
        reported: set[uuid.UUID] = set()

        with capture_logs() as logs:
            report_unreadable(wallet, [first], reported=reported)
            report_unreadable(wallet, [first], reported=reported)
            report_unreadable(wallet, [first, second], reported=reported)
            report_unreadable(wallet, [first, second], reported=reported)

        named = [line["proposal_id"] for line in _geometry_lines(logs)]
        assert named == [str(first.proposal_id), str(second.proposal_id)]

    def test_a_row_that_stopped_being_pending_is_forgotten(self) -> None:
        """The set is pruned to what is still filed, so it cannot grow for ever."""
        wallet, row = _wallet(), _pending()
        reported: set[uuid.UUID] = set()

        with capture_logs() as logs:
            report_unreadable(wallet, [row], reported=reported)
            report_unreadable(wallet, [], reported=reported)
            report_unreadable(wallet, [row], reported=reported)

        assert len(_geometry_lines(logs)) == 2
        assert reported == {row.proposal_id}

    def test_without_a_set_every_call_names_every_row(self) -> None:
        wallet, row = _wallet(), _pending()

        with capture_logs() as logs:
            report_unreadable(wallet, [row])
            report_unreadable(wallet, [row])

        assert len(_geometry_lines(logs)) == 2


class TestTheDegradedBackoff:
    def test_it_doubles_from_one_second_and_stops_at_sixty(self) -> None:
        retries, intent_id = DegradedRetries(), uuid.uuid4()

        delays = [retries.defer(intent_id, NOW) for _ in range(10)]

        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0, 60.0]
        assert delays[0] == BACKOFF_START_S
        assert max(delays) == BACKOFF_MAX_S

    def test_a_protection_that_never_failed_is_ready_now(self) -> None:
        assert DegradedRetries().ready(uuid.uuid4(), NOW) is True

    def test_the_first_refusal_holds_it_for_exactly_one_second(self) -> None:
        retries, intent_id = DegradedRetries(), uuid.uuid4()
        retries.defer(intent_id, NOW)

        assert retries.ready(intent_id, NOW + timedelta(milliseconds=999)) is False
        assert retries.ready(intent_id, NOW + timedelta(seconds=1)) is True

    def test_a_fill_forgets_the_backoff(self) -> None:
        retries, intent_id = DegradedRetries(), uuid.uuid4()
        retries.defer(intent_id, NOW)

        retries.clear(intent_id)

        assert retries.ready(intent_id, NOW) is True
        assert retries.delay_s == {}


class TestTheMarkToMarketSchedule:
    def test_the_grid_is_whole_minutes_and_never_returns_now(self) -> None:
        assert next_grid_tick(NOW, 60.0) == NOW + timedelta(minutes=1)
        assert next_grid_tick(NOW + timedelta(seconds=1.5), 60.0) == NOW + timedelta(minutes=1)
        assert next_grid_tick(NOW + timedelta(seconds=59.999), 60.0) == NOW + timedelta(minutes=1)

    def test_the_next_sao_paulo_turn_is_three_in_the_morning_utc(self) -> None:
        assert next_sao_paulo_turn(NOW) == TURN
        assert next_sao_paulo_turn(TURN - timedelta(seconds=1)) == TURN
        assert next_sao_paulo_turn(TURN) == TURN + timedelta(days=1)

    def test_the_pass_before_the_turn_is_pulled_back_to_the_margin(self) -> None:
        margin = TURN - timedelta(seconds=TURN_MARGIN_S)

        assert next_mtm_tick(TURN - timedelta(seconds=60), period_s=60.0) == margin
        # And the one after the margin goes back to the grid, which is the turn.
        assert next_mtm_tick(margin, period_s=60.0) == TURN

    @pytest.mark.parametrize("offset_s", list(range(60)))
    def test_the_day_always_has_a_point_inside_its_sixty_second_budget(self, offset_s: int) -> None:
        """Whatever second of the minute the worker started on, and however long
        each pass takes, there is a point at or before the turn within 60 s of it.

        Before the fix the loop slept 60 s **after** the work, so the real period
        was 61,5 s: for the starts where the first point after midnight lands in
        the first 1,5 s of the day, the newest point at or before the turn was
        61,5 s old and ``resolve_day_reference`` refused it — the daily reference
        unavailable for the whole day, entries blocked, protections preserved.
        """
        moment = TURN - timedelta(minutes=20) + timedelta(seconds=offset_s)
        instants: list[datetime] = []
        while moment <= TURN + timedelta(minutes=5):
            instants.append(moment)
            moment = next_mtm_tick(moment + timedelta(seconds=WORK_S), period_s=60.0)

        anchor = max(point for point in instants if point <= TURN)
        assert (TURN - anchor).total_seconds() <= DAY_OPENING_MAX_LAG_S
        # And with real margin, not by a hair: the extra point is the anchor.
        assert (TURN - anchor).total_seconds() <= TURN_MARGIN_S
