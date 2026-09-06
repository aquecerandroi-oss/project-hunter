"""The anomaly state machine: open, hold, resolve, expire — and never by absence.

Pure transitions driven by the observation timestamp, so a watchdog and a replay
walk the same path. Each test is one row of the transition table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus, AnomalyType
from hunter_indicators.anomalies import (
    AnomalyAction,
    AnomalyDirection,
    AnomalyEvaluation,
    AnomalyState,
    advance,
    advance_all,
    detector_for,
    no_data,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
START = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
DETECTOR = detector_for(AnomalyType.VOLUME_SPIKE)


def evaluation(
    severity: str,
    *,
    at: datetime,
    state: AnomalyEvaluationState = AnomalyEvaluationState.OK,
    reason: str | None = None,
) -> AnomalyEvaluation:
    return AnomalyEvaluation(
        market_id=MARKET,
        type=AnomalyType.VOLUME_SPIKE,
        observation_ts=at,
        evaluation_state=state,
        detector_version=DETECTOR.identity,
        normalization_version="mad_piecewise_v1@v2",
        feature=DETECTOR.feature,
        feature_version=DETECTOR.feature_version,
        unit=DETECTOR.unit,
        severity=Decimal(severity),
        confidence=Decimal("0.9524"),
        baseline=Decimal("1"),
        current_value=Decimal("2"),
        deviation=Decimal("4"),
        direction=AnomalyDirection.UP,
        reason=reason,
        baseline_ids=(uuid.UUID("0199a1d0-0000-7000-8000-0000000000aa"),),
    )


def opened(at: datetime = START, severity: str = "60") -> AnomalyState:
    transition = advance(None, evaluation(severity, at=at), DETECTOR)
    assert transition.state is not None
    return transition.state


class TestOpening:
    def test_a_severity_over_the_firing_line_opens_an_anomaly(self) -> None:
        transition = advance(None, evaluation("60", at=START), DETECTOR)
        assert transition.action is AnomalyAction.OPEN
        assert transition.state is not None
        assert transition.state.status is AnomalyStatus.ACTIVE
        assert transition.state.detected_at == START
        assert transition.state.severity == Decimal("60")
        assert transition.state.evaluation_state is AnomalyEvaluationState.OK

    def test_a_severity_under_the_firing_line_opens_nothing(self) -> None:
        transition = advance(None, evaluation("39.99", at=START), DETECTOR)
        assert transition.action is AnomalyAction.NONE
        assert transition.state is None

    def test_an_ineligible_evaluation_never_opens_an_anomaly(self) -> None:
        transition = advance(
            None,
            evaluation("95", at=START, state=AnomalyEvaluationState.STALE, reason="stale_input"),
            DETECTOR,
        )
        assert transition.action is AnomalyAction.NONE

    def test_no_data_opens_nothing(self) -> None:
        transition = advance(
            None, no_data(MARKET, DETECTOR, observation_ts=START, reason="no_sample"), DETECTOR
        )
        assert transition.action is AnomalyAction.NONE


class TestHoldingAndUpdating:
    def test_a_still_unusual_reading_updates_the_severity(self) -> None:
        state = opened()
        transition = advance(state, evaluation("80", at=START + timedelta(minutes=1)), DETECTOR)
        assert transition.action is AnomalyAction.UPDATE
        assert transition.state is not None
        assert transition.state.severity == Decimal("80")
        assert transition.state.detected_at == START
        assert transition.state.below_hold_since is None

    def test_a_reading_between_hold_and_fire_keeps_the_anomaly_open(self) -> None:
        state = opened()
        transition = advance(state, evaluation("25", at=START + timedelta(minutes=1)), DETECTOR)
        assert transition.action is AnomalyAction.UPDATE
        assert transition.state is not None
        assert transition.state.status is AnomalyStatus.ACTIVE
        assert transition.state.below_hold_since is None

    def test_a_reading_below_hold_starts_the_resolution_clock(self) -> None:
        state = opened()
        at = START + timedelta(minutes=1)
        transition = advance(state, evaluation("10", at=at), DETECTOR)
        assert transition.action is AnomalyAction.HOLD
        assert transition.state is not None
        assert transition.state.below_hold_since == at
        assert transition.state.status is AnomalyStatus.ACTIVE


class TestResolving:
    def test_five_minutes_below_the_holding_line_resolves(self) -> None:
        # Five *proven* minutes: one reading a minute, none of them missing.
        state = opened()
        for minute in range(1, 6):
            state = advance(
                state, evaluation("10", at=START + timedelta(minutes=minute)), DETECTOR
            ).state
            assert state is not None
        transition = advance(state, evaluation("10", at=START + timedelta(minutes=6)), DETECTOR)
        assert transition.action is AnomalyAction.RESOLVE
        assert transition.state is not None
        assert transition.state.status is AnomalyStatus.RESOLVED
        assert transition.state.resolved_at == START + timedelta(minutes=6)

    def test_four_minutes_below_then_a_spike_again_does_not_resolve(self) -> None:
        state = opened()
        state = advance(state, evaluation("10", at=START + timedelta(minutes=1)), DETECTOR).state
        assert state is not None
        state = advance(state, evaluation("70", at=START + timedelta(minutes=4)), DETECTOR).state
        assert state is not None
        assert state.below_hold_since is None
        transition = advance(state, evaluation("10", at=START + timedelta(minutes=10)), DETECTOR)
        assert transition.action is AnomalyAction.HOLD

    def test_absence_breaks_the_streak_instead_of_joining_two_halves(self) -> None:
        # Four minutes below, ten minutes with no data, one more minute below:
        # fifteen minutes elapsed, but never five *consecutive* proven minutes
        # (Astra, T2.3 design review, item 7).
        state = opened()
        state = advance(state, evaluation("10", at=START + timedelta(minutes=1)), DETECTOR).state
        assert state is not None
        state = advance(
            state,
            no_data(MARKET, DETECTOR, observation_ts=START + timedelta(minutes=5), reason="gap"),
            DETECTOR,
        ).state
        assert state is not None
        assert state.below_hold_since is None
        transition = advance(state, evaluation("10", at=START + timedelta(minutes=15)), DETECTOR)
        assert transition.action is AnomalyAction.HOLD
        assert transition.state is not None
        assert transition.state.below_hold_since == START + timedelta(minutes=15)


class TestUnknownAndStale:
    def test_an_anomaly_whose_feed_went_away_stays_active_and_unknown(self) -> None:
        state = opened()
        transition = advance(
            state,
            no_data(
                MARKET, DETECTOR, observation_ts=START + timedelta(minutes=2), reason="no_sample"
            ),
            DETECTOR,
        )
        assert transition.action is AnomalyAction.HOLD
        assert transition.state is not None
        assert transition.state.status is AnomalyStatus.ACTIVE
        assert transition.state.evaluation_state is AnomalyEvaluationState.UNKNOWN
        assert transition.state.severity == Decimal("60")  # the last believed value

    def test_a_stale_reading_does_not_update_the_severity(self) -> None:
        state = opened()
        transition = advance(
            state,
            evaluation(
                "95",
                at=START + timedelta(minutes=2),
                state=AnomalyEvaluationState.STALE,
                reason="stale_input",
            ),
            DETECTOR,
        )
        assert transition.state is not None
        assert transition.state.severity == Decimal("60")
        assert transition.state.evaluation_state is AnomalyEvaluationState.STALE

    def test_recovery_keeps_the_identity_of_the_episode(self) -> None:
        state = opened()
        state = advance(
            state,
            no_data(
                MARKET, DETECTOR, observation_ts=START + timedelta(minutes=2), reason="no_sample"
            ),
            DETECTOR,
        ).state
        assert state is not None
        transition = advance(state, evaluation("70", at=START + timedelta(minutes=3)), DETECTOR)
        assert transition.state is not None
        assert transition.state.detected_at == START
        assert transition.state.evaluation_state is AnomalyEvaluationState.OK


class TestExpiring:
    def test_four_hours_expire_an_anomaly_even_without_data(self) -> None:
        state = opened()
        transition = advance(
            state,
            no_data(
                MARKET, DETECTOR, observation_ts=START + timedelta(hours=4), reason="no_sample"
            ),
            DETECTOR,
        )
        assert transition.action is AnomalyAction.EXPIRE
        assert transition.state is not None
        assert transition.state.status is AnomalyStatus.EXPIRED
        assert transition.state.resolved_at == START + timedelta(hours=4)

    def test_expiry_wins_over_a_still_severe_reading(self) -> None:
        state = opened()
        transition = advance(
            state, evaluation("95", at=START + timedelta(hours=4, minutes=1)), DETECTOR
        )
        assert transition.action is AnomalyAction.EXPIRE


class TestOrderingAndDedupe:
    def test_a_replayed_observation_changes_nothing(self) -> None:
        state = opened()
        state = advance(state, evaluation("80", at=START + timedelta(minutes=2)), DETECTOR).state
        assert state is not None
        transition = advance(state, evaluation("10", at=START + timedelta(minutes=1)), DETECTOR)
        assert transition.action is AnomalyAction.NONE
        assert transition.state is None

    def test_the_same_observation_twice_changes_nothing(self) -> None:
        state = opened()
        transition = advance(state, evaluation("80", at=START), DETECTOR)
        assert transition.action is AnomalyAction.NONE

    def test_a_closed_anomaly_lets_a_new_episode_start(self) -> None:
        state = opened()
        for minute in range(1, 6):  # five proven readings below the holding line
            state = advance(
                state, evaluation("10", at=START + timedelta(minutes=minute)), DETECTOR
            ).state
            assert state is not None
        resolved = advance(state, evaluation("10", at=START + timedelta(minutes=6)), DETECTOR).state
        assert resolved is not None
        assert resolved.status is AnomalyStatus.RESOLVED
        transition = advance(resolved, evaluation("90", at=START + timedelta(minutes=20)), DETECTOR)
        assert transition.action is AnomalyAction.OPEN
        assert transition.state is not None
        assert transition.state.detected_at == START + timedelta(minutes=20)

    def test_one_active_anomaly_per_market_and_type(self) -> None:
        state = opened()
        with pytest.raises(ValueError, match="one evaluation per"):
            advance_all(
                [state],
                [
                    evaluation("70", at=START + timedelta(minutes=1)),
                    evaluation("80", at=START + timedelta(minutes=1)),
                ],
                [DETECTOR],
            )

    def test_a_batch_pairs_each_state_with_its_evaluation(self) -> None:
        state = opened()
        transitions = advance_all(
            [state], [evaluation("80", at=START + timedelta(minutes=1))], [DETECTOR]
        )
        assert [transition.action for transition in transitions] == [AnomalyAction.UPDATE]


class TestAstraDiffReview:
    """Regressions for the findings of ``astra-review-T2.3-diff.md``."""

    def test_an_old_event_does_not_reopen_a_closed_anomaly(self) -> None:
        # Finding 1: the ordering guard only ran for *open* states, so replaying
        # the 10:00 evaluation after the episode expired at 14:00 opened a new
        # one dated 10:00.
        state = opened()
        expired = advance(
            state,
            no_data(MARKET, DETECTOR, observation_ts=START + timedelta(hours=4), reason="gap"),
            DETECTOR,
        ).state
        assert expired is not None
        assert expired.status is AnomalyStatus.EXPIRED
        transition = advance(expired, evaluation("90", at=START), DETECTOR)
        assert transition.action is AnomalyAction.NONE
        assert transition.state is None

    def test_every_eligible_evaluation_replaces_the_whole_evidence(self) -> None:
        # Finding 2: a below-hold reading updated severity/current_value but kept
        # the previous baseline and baseline_ids, so the stored explanation
        # mixed a deviation against B with the baseline of A.
        other_baseline = uuid.UUID("0199a1d0-0000-7000-8000-0000000000bb")
        state = opened()
        moved = AnomalyEvaluation(
            market_id=MARKET,
            type=AnomalyType.VOLUME_SPIKE,
            observation_ts=START + timedelta(minutes=1),
            evaluation_state=AnomalyEvaluationState.OK,
            detector_version=DETECTOR.identity,
            normalization_version="mad_piecewise_v1@v3",
            feature=DETECTOR.feature,
            feature_version=DETECTOR.feature_version,
            unit=DETECTOR.unit,
            severity=Decimal("10"),
            confidence=Decimal("0.5000"),
            baseline=Decimal("2"),
            current_value=Decimal("2.5"),
            deviation=Decimal("0.5"),
            direction=AnomalyDirection.UP,
            baseline_ids=(other_baseline,),
        )
        transition = advance(state, moved, DETECTOR)
        assert transition.state is not None
        assert transition.state.baseline == Decimal("2")
        assert transition.state.baseline_ids == (other_baseline,)
        assert transition.state.confidence == Decimal("0.5000")
        assert transition.state.normalization_version == "mad_piecewise_v1@v3"

    def test_silence_inside_the_resolution_window_restarts_the_streak(self) -> None:
        # Nice-to-have from the review: the watchdog has to feed ``no_data``, and
        # when it does the five minutes start again.
        state = opened()
        state = advance(state, evaluation("10", at=START + timedelta(minutes=1)), DETECTOR).state
        assert state is not None
        for minute in (2, 3, 4):
            nxt = advance(
                state,
                no_data(
                    MARKET,
                    DETECTOR,
                    observation_ts=START + timedelta(minutes=minute),
                    reason="no_sample",
                ),
                DETECTOR,
            ).state
            assert nxt is not None
            state = nxt
        transition = advance(state, evaluation("10", at=START + timedelta(minutes=6)), DETECTOR)
        assert transition.action is AnomalyAction.HOLD


class TestCrossReviewProvenReadings:
    """Resolution needs readings, not only a clock (cross review, nice-to-have d).

    ``below_hold_since`` alone measures *elapsed time*: two readings seven
    minutes apart satisfied it, and an anomaly was declared over on the strength
    of two samples. Five minutes of calm has to mean five distinct readings that
    were actually below the holding line, which is the same evidence rule the
    ``no_data``/``stale`` zeroing already applies — a market that went quiet and
    a market whose scanner skipped it are the same absence of proof.
    """

    def test_ten_hundred_and_two_then_silence_until_ten_oh_seven_does_not_resolve(self) -> None:
        # 10:00 below, 10:02 below, nothing until 10:07. Seven minutes elapsed,
        # three readings: not five proven minutes.
        state = opened(at=START - timedelta(minutes=5))
        for minute in (0, 2, 7):
            transition = advance(
                state, evaluation("10", at=START + timedelta(minutes=minute)), DETECTOR
            )
            assert transition.state is not None
            state = transition.state
        assert transition.action is AnomalyAction.HOLD
        assert state.status is AnomalyStatus.ACTIVE
        assert state.below_hold_since == START
        assert state.below_hold_readings == 3

    def test_the_readings_are_counted_and_carried_in_the_wire(self) -> None:
        state = opened()
        for minute in (1, 2, 3):
            transition = advance(
                state, evaluation("10", at=START + timedelta(minutes=minute)), DETECTOR
            )
            assert transition.state is not None
            state = transition.state
        assert state.below_hold_readings == 3
        assert state.as_wire()["below_hold_readings"] == 3

    def test_an_update_clears_the_count(self) -> None:
        state = opened()
        state = advance(state, evaluation("10", at=START + timedelta(minutes=1)), DETECTOR).state
        assert state is not None and state.below_hold_readings == 1
        state = advance(state, evaluation("70", at=START + timedelta(minutes=2)), DETECTOR).state
        assert state is not None
        assert state.below_hold_readings == 0
        assert state.below_hold_since is None

    def test_no_data_zeroes_the_count(self) -> None:
        state = opened()
        for minute in (1, 2, 3, 4):
            state = advance(
                state, evaluation("10", at=START + timedelta(minutes=minute)), DETECTOR
            ).state
            assert state is not None
        assert state.below_hold_readings == 4
        state = advance(
            state,
            no_data(MARKET, DETECTOR, observation_ts=START + timedelta(minutes=5), reason="gap"),
            DETECTOR,
        ).state
        assert state is not None
        assert state.below_hold_readings == 0

    def test_a_stale_reading_zeroes_the_count(self) -> None:
        state = opened()
        state = advance(state, evaluation("10", at=START + timedelta(minutes=1)), DETECTOR).state
        assert state is not None
        state = advance(
            state,
            evaluation(
                "10",
                at=START + timedelta(minutes=2),
                state=AnomalyEvaluationState.STALE,
                reason="stale_input",
            ),
            DETECTOR,
        ).state
        assert state is not None
        assert state.below_hold_readings == 0

    def test_enough_readings_but_not_enough_time_does_not_resolve_either(self) -> None:
        # The two conditions are independent: five readings inside four minutes
        # is not five minutes of calm.
        state = opened()
        for seconds in (30, 60, 90, 120, 150):
            transition = advance(
                state, evaluation("10", at=START + timedelta(seconds=seconds)), DETECTOR
            )
            assert transition.state is not None
            state = transition.state
        assert state.below_hold_readings == 5
        assert transition.action is AnomalyAction.HOLD
        assert state.status is AnomalyStatus.ACTIVE

    def test_the_detector_declares_how_many_readings_prove_the_calm(self) -> None:
        assert DETECTOR.resolve_min_readings == 5
        assert DETECTOR.as_wire()["thresholds"]["resolve_min_readings"] == 5


class TestCrossReviewGapsAreTheWatchdogsJob:
    """What the reading count proves, and what only the watchdog can prove.

    Astra reproduced readings at minutes 0, 1, 2, 3 and 60 resolving an anomaly
    after 57 minutes of silence (revisão do fix-pass, item d). That is the
    declared behaviour, not a bug being tolerated quietly: ``resolve_min_readings``
    proves five *readings*, never five *contiguous* minutes, and a pure function
    cannot infer a gap nobody told it about — inventing one would be a clock
    read. The remedy is the watchdog feeding ``no_data`` for the silent minutes
    (requisito T2.5 (a), notes-T2.3 §10). Both halves are pinned here so that
    changing the policy has to be a decision, not a refactor.
    """

    def below_at(self, state: AnomalyState, minute: int) -> AnomalyState:
        transition = advance(
            state, evaluation("10", at=START + timedelta(minutes=minute)), DETECTOR
        )
        assert transition.state is not None
        return transition.state

    def test_five_readings_spread_over_an_hour_do_resolve(self) -> None:
        # Astra's series exactly: below-hold readings at minutes 0, 1, 2, 3 and
        # 60. The documented limitation, stated as a test — the count is
        # readings, so five of them resolve however far apart they are.
        state = opened(at=START - timedelta(minutes=5))
        for minute in (0, 1, 2, 3):
            state = self.below_at(state, minute)
        transition = advance(state, evaluation("10", at=START + timedelta(minutes=60)), DETECTOR)
        assert transition.action is AnomalyAction.RESOLVE
        assert transition.state is not None
        assert transition.state.below_hold_readings == 5

    def test_a_watchdog_reporting_the_silence_is_what_prevents_it(self) -> None:
        # Same series, with the watchdog doing its job in the gap: the run is
        # zeroed and the minute-60 reading starts a fresh one instead of
        # closing an episode nobody watched.
        state = opened(at=START - timedelta(minutes=5))
        for minute in (0, 1, 2, 3):
            state = self.below_at(state, minute)
        transition = advance(
            state,
            no_data(MARKET, DETECTOR, observation_ts=START + timedelta(minutes=30), reason="gap"),
            DETECTOR,
        )
        assert transition.state is not None
        state = transition.state
        assert state.below_hold_readings == 0
        assert state.below_hold_since is None

        transition = advance(state, evaluation("10", at=START + timedelta(minutes=60)), DETECTOR)
        assert transition.action is AnomalyAction.HOLD
        assert transition.state is not None
        assert transition.state.status is AnomalyStatus.ACTIVE
        assert transition.state.below_hold_readings == 1
