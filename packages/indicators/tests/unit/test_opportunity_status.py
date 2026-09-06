"""The status machine: the table of cases, the precedence, the episode identity."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.opportunity import (
    EpisodeAction,
    EpisodeState,
    StatusSample,
    StatusThresholds,
    advance_status,
)
from hunter_indicators.opportunity.status import (
    REASON_BELOW_FLOOR_PROVEN,
    REASON_EPISODE_CLOSED,
    REASON_NOT_ELIGIBLE,
    REASON_STALE_OBSERVATION,
    REASON_SUSTAINED_BY_ANOMALY,
    candidate_status,
)
from packages.indicators.tests.scoring import OBSERVED_AT, TEST_WEIGHTS

THRESHOLDS = StatusThresholds.from_weights(TEST_WEIGHTS, version="v2-test")
MINUTE = timedelta(minutes=1)


def sample(
    minutes: int = 0,
    score: str | None = "50",
    *,
    stage: OpportunityStage = OpportunityStage.NONE,
    anomaly: str | None = None,
    signals: int = 0,
    eligible: bool = True,
    direction: TradeDirection = TradeDirection.LONG,
) -> StatusSample:
    return StatusSample(
        observation_ts=OBSERVED_AT + minutes * MINUTE,
        score=None if score is None else Decimal(score),
        eligible=eligible,
        stage=stage,
        direction=direction,
        confidence=Decimal("0.9000"),
        anomaly_severity=None if anomaly is None else Decimal(anomaly),
        agreeing_signals=signals,
    )


class TestTheTableOfCases:
    @pytest.mark.parametrize(
        ("score", "anomaly", "stage", "signals", "expected"),
        [
            ("10", None, OpportunityStage.NONE, 0, OpportunityStatus.NORMAL),
            ("39.99", None, OpportunityStage.NONE, 0, OpportunityStatus.NORMAL),
            ("40", None, OpportunityStage.NONE, 0, OpportunityStatus.WATCHING),
            ("30", "60", OpportunityStage.NONE, 0, OpportunityStatus.ANOMALY),
            ("30", "59.99", OpportunityStage.NONE, 0, OpportunityStatus.NORMAL),
            ("50", "80", OpportunityStage.NONE, 0, OpportunityStatus.ANOMALY),
            ("75", "80", OpportunityStage.NONE, 0, OpportunityStatus.HOT),
            ("80", None, OpportunityStage.NONE, 0, OpportunityStatus.HOT),
            ("80", None, OpportunityStage.NONE, 1, OpportunityStatus.ENTRY_CANDIDATE),
            ("80", None, OpportunityStage.EXTENDED, 1, OpportunityStatus.EXTENDED),
            ("45", None, OpportunityStage.EXTENDED, 0, OpportunityStatus.EXTENDED),
            ("39", None, OpportunityStage.EXTENDED, 0, OpportunityStatus.NORMAL),
            ("90", None, OpportunityStage.EARLY, 0, OpportunityStatus.HOT),
        ],
    )
    def test_the_candidate_follows_the_declared_precedence(
        self,
        score: str,
        anomaly: str | None,
        stage: OpportunityStage,
        signals: int,
        expected: OpportunityStatus,
    ) -> None:
        assert (
            candidate_status(
                sample(score=score, anomaly=anomaly, stage=stage, signals=signals), THRESHOLDS
            )
            is expected
        )

    def test_entry_candidate_is_unreachable_without_an_agreeing_signal(self) -> None:
        assert candidate_status(sample(score="99"), THRESHOLDS) is OpportunityStatus.HOT


class TestEpisodeIdentity:
    def test_normal_never_opens_an_episode(self) -> None:
        decision = advance_status(None, sample(score="20"), THRESHOLDS)
        assert decision.action is EpisodeAction.NONE
        assert decision.state_out is None

    def test_an_anomaly_opens_an_episode_below_the_watching_line(self) -> None:
        decision = advance_status(None, sample(score="30", anomaly="70"), THRESHOLDS)
        assert decision.action is EpisodeAction.OPEN
        assert decision.status is OpportunityStatus.ANOMALY

    def test_eighty_then_thirty_five_then_forty_five_is_one_episode(self) -> None:
        """The decisive scenario of ``docs/DATABASE.md`` §17.3."""
        opened = advance_status(None, sample(0, "80"), THRESHOLDS)
        assert opened.action is EpisodeAction.OPEN
        state = opened.state_out
        assert state is not None
        dipped = advance_status(state, sample(1, "35"), THRESHOLDS)
        assert dipped.action is EpisodeAction.UPDATE
        assert dipped.status is OpportunityStatus.NORMAL
        assert dipped.state_out is not None
        assert dipped.state_out.first_seen_at == state.first_seen_at
        assert dipped.state_out.below_floor_since == OBSERVED_AT + MINUTE
        recovered = advance_status(dipped.state_out, sample(2, "45"), THRESHOLDS)
        assert recovered.status is OpportunityStatus.WATCHING
        assert recovered.state_out is not None
        assert recovered.state_out.first_seen_at == state.first_seen_at
        assert recovered.state_out.below_floor_since is None
        assert recovered.state_out.peak_score == Decimal("80")

    def test_a_redelivered_sample_changes_nothing(self) -> None:
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        again = advance_status(state, sample(0, "80"), THRESHOLDS)
        assert again.action is EpisodeAction.NONE
        assert again.reason == REASON_STALE_OBSERVATION
        assert again.state_out == state

    def test_a_closed_episode_is_never_reopened_in_place(self) -> None:
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        expired = _run_below_floor(state)
        decision = advance_status(expired, sample(30, "90"), THRESHOLDS)
        assert decision.action is EpisodeAction.NONE
        assert decision.reason == REASON_EPISODE_CLOSED
        fresh = advance_status(None, sample(30, "90"), THRESHOLDS)
        assert fresh.action is EpisodeAction.OPEN
        assert fresh.state_out is not None
        assert fresh.state_out.first_seen_at == OBSERVED_AT + 30 * MINUTE


def _run_below_floor(state: EpisodeState, *, start: int = 1, count: int = 16) -> EpisodeState:
    """Feed ``count`` valid readings under the floor, one per minute."""
    current = state
    for index in range(count):
        decision = advance_status(current, sample(start + index, "35"), THRESHOLDS)
        assert decision.state_out is not None
        current = decision.state_out
    return current


class TestExpiry:
    def test_fifteen_proven_minutes_expire_the_episode(self) -> None:
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        current = state
        actions: list[EpisodeAction] = []
        for index in range(16):
            decision = advance_status(current, sample(1 + index, "35"), THRESHOLDS)
            actions.append(decision.action)
            assert decision.state_out is not None
            current = decision.state_out
        assert actions[-1] is EpisodeAction.EXPIRE
        assert actions[-2] is EpisodeAction.UPDATE  # fifteen points span fourteen minutes
        assert current.expired_at == OBSERVED_AT + 16 * MINUTE
        assert current.status is OpportunityStatus.EXPIRED

    def test_a_lost_reading_zeroes_the_run_instead_of_pausing_it(self) -> None:
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        current = _run_below_floor(state, start=1, count=14)
        blind = advance_status(current, sample(15, None, eligible=False), THRESHOLDS)
        assert blind.action is EpisodeAction.HOLD
        assert blind.reason == REASON_NOT_ELIGIBLE
        assert blind.state_out is not None
        assert blind.state_out.below_floor_since is None
        assert blind.state_out.below_floor_readings == 0
        assert blind.state_out.status is OpportunityStatus.NORMAL
        after = advance_status(blind.state_out, sample(16, "35"), THRESHOLDS)
        assert after.action is EpisodeAction.UPDATE
        assert after.state_out is not None
        assert after.state_out.below_floor_readings == 1

    def test_an_eligible_anomaly_sustains_the_episode(self) -> None:
        """Contract revision agreed with Astra (T2.4 review, item 7): an episode
        with a live severity-70 anomaly does not expire on the score alone."""
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        current = state
        for index in range(20):
            decision = advance_status(current, sample(1 + index, "30", anomaly="70"), THRESHOLDS)
            assert decision.action is EpisodeAction.UPDATE
            assert decision.reason == REASON_SUSTAINED_BY_ANOMALY
            assert decision.status is OpportunityStatus.ANOMALY
            assert decision.state_out is not None
            current = decision.state_out
        assert current.expired_at is None

    def test_expiry_is_proven_by_readings_and_not_by_two_distant_samples(self) -> None:
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        first = advance_status(state, sample(1, "35"), THRESHOLDS)
        assert first.state_out is not None
        distant = advance_status(first.state_out, sample(60, "35"), THRESHOLDS)
        assert distant.action is EpisodeAction.UPDATE
        assert distant.state_out is not None
        assert distant.state_out.expired_at is None
        assert distant.state_out.below_floor_readings == 2

    def test_the_expiring_sample_reports_its_reason(self) -> None:
        state = advance_status(None, sample(0, "80"), THRESHOLDS).state_out
        assert state is not None
        current = _run_below_floor(state, start=1, count=15)
        decision = advance_status(current, sample(16, "35"), THRESHOLDS)
        assert decision.reason == REASON_BELOW_FLOOR_PROVEN


class TestRestartAndDelivery:
    def test_the_state_survives_a_restart_through_json(self) -> None:
        opened = advance_status(None, sample(0, "80"), THRESHOLDS)
        state = opened.state_out
        assert state is not None
        dipped = advance_status(state, sample(1, "35"), THRESHOLDS).state_out
        assert dipped is not None
        rehydrated = EpisodeState.from_wire(json.loads(canonical_json(dipped.as_wire())))
        assert rehydrated == dipped
        live = advance_status(dipped, sample(2, "45"), THRESHOLDS)
        after_restart = advance_status(rehydrated, sample(2, "45"), THRESHOLDS)
        assert after_restart.state_out == live.state_out

    def test_a_duplicate_delivery_after_a_restart_is_still_a_duplicate(self) -> None:
        opened = advance_status(None, sample(0, "80"), THRESHOLDS)
        assert opened.state_out is not None
        rehydrated = EpisodeState.from_wire(json.loads(canonical_json(opened.state_out.as_wire())))
        again = advance_status(rehydrated, sample(0, "80"), THRESHOLDS)
        assert again.action is EpisodeAction.NONE
        assert again.reason == REASON_STALE_OBSERVATION


class TestThresholdsComeFromTheProfile:
    def test_every_threshold_is_read_from_the_weight_vector(self) -> None:
        assert THRESHOLDS.watching_min == Decimal("40")
        assert THRESHOLDS.hot_min == Decimal("75")
        assert THRESHOLDS.entry_candidate_min == Decimal("80")
        assert THRESHOLDS.anomaly_severity_min == Decimal("60")
        assert THRESHOLDS.score_floor == Decimal("40")
        assert THRESHOLDS.below_floor_minutes == 15
        assert THRESHOLDS.below_floor_min_readings == 16

    def test_a_profile_without_the_block_raises_instead_of_defaulting(self) -> None:
        with pytest.raises(KeyError):
            StatusThresholds.from_weights({"status": {}}, version="broken")
