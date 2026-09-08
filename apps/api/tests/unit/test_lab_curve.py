"""Unit tests: ``GET /lab/shadow/curve`` — T3.18c, item 10.

A curva ecoa a coorte que desenhou, e o coringa ``replay`` **recusa** somar
corridas cujas janelas se sobrepõem em vez de contar o mesmo R duas vezes.
Sem IO: ``ReplayRunWindow``/``OutcomeRow`` montados à mão.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.repositories.lab_scoreboard import ReplayRunWindow
from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_api.services.lab_curve import OVERLAP_REASON, build_curve, overlapping_runs
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)
RUN_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
RUN_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _window(run_id: uuid.UUID, *, start: datetime, end: datetime) -> ReplayRunWindow:
    return ReplayRunWindow(run_id=run_id, window_from=start, window_to=end)


def _row(*, exit_ts: datetime, r_multiple: Decimal) -> OutcomeRow:
    return OutcomeRow(
        tracking_state=ShadowTrackingState.TERMINAL,
        result=OutcomeResult.TARGET if r_multiple > 0 else OutcomeResult.STOP,
        no_entry_reason=None,
        censored_reason=None,
        entry_ts=exit_ts - timedelta(hours=1),
        exit_ts=exit_ts,
        r_multiple=r_multiple,
        meta={},
        market_id=uuid.uuid4(),
        decision_at=exit_ts - timedelta(hours=2),
    )


class TestOverlappingRuns:
    def test_adjacent_half_open_windows_do_not_overlap(self) -> None:
        """``[from, to)``: a corrida que começa onde a outra termina não repete
        uma única barra (``replay_runs``, DATABASE.md §25.1)."""
        windows = [
            _window(RUN_A, start=AS_OF - 10 * DAY, end=AS_OF - 5 * DAY),
            _window(RUN_B, start=AS_OF - 5 * DAY, end=AS_OF),
        ]
        assert overlapping_runs(windows) == []

    def test_two_runs_over_the_same_month_are_reported_as_a_clash(self) -> None:
        windows = [
            _window(RUN_A, start=AS_OF - 31 * DAY, end=AS_OF),
            _window(RUN_B, start=AS_OF - 31 * DAY, end=AS_OF),
        ]
        assert overlapping_runs(windows) == [(str(RUN_A), str(RUN_B))]

    def test_a_partial_overlap_is_still_an_overlap(self) -> None:
        windows = [
            _window(RUN_A, start=AS_OF - 10 * DAY, end=AS_OF - 4 * DAY),
            _window(RUN_B, start=AS_OF - 5 * DAY, end=AS_OF),
        ]
        assert overlapping_runs(windows) == [(str(RUN_A), str(RUN_B))]

    def test_a_single_run_never_clashes_with_itself(self) -> None:
        assert overlapping_runs([_window(RUN_A, start=AS_OF - DAY, end=AS_OF)]) == []

    def test_the_reason_is_the_documented_one(self) -> None:
        assert OVERLAP_REASON == "janelas_sobrepostas"


class TestCurveEchoesItsCohort:
    def test_the_cohort_it_drew_comes_back_in_the_payload(self) -> None:
        rows = [
            _row(exit_ts=AS_OF - 2 * DAY, r_multiple=Decimal("1")),
            _row(exit_ts=AS_OF - DAY, r_multiple=Decimal("-0.5")),
        ]
        curve = build_curve(
            strategy_version_id=uuid.uuid4(), rows=rows, as_of=AS_OF, cohort="replay"
        )
        assert curve.cohort == "replay"
        assert [point.cum_r for point in curve.points] == [Decimal("1.0000"), Decimal("0.5000")]
