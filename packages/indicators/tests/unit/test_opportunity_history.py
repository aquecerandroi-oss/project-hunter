"""``should_record_history``: what is worth a row, against the last persisted one."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection
from hunter_indicators.opportunity import (
    HISTORY_POLICY_VERSION,
    HistoryMark,
    HistoryPolicy,
    quality_signature,
    score_opportunity,
    should_record_history,
)
from hunter_indicators.opportunity.history import (
    REASON_DIRECTION,
    REASON_ELIGIBILITY,
    REASON_FIRST,
    REASON_INTERVAL,
    REASON_QUALITY,
    REASON_REGIME,
    REASON_SCORE_DELTA,
    REASON_STAGE,
    REASON_STAGE_DIRECTION,
    REASON_STALE,
    REASON_STATUS,
    REASON_VERSION,
)
from packages.indicators.tests.scoring import OBSERVED_AT

MINUTE = timedelta(minutes=1)
VERSIONS = {"scorer": "opportunity_v1", "weights": "v2"}


def mark(minutes: int = 0, score: str = "50", **kwargs: Any) -> HistoryMark:
    base = HistoryMark(
        ts=OBSERVED_AT + minutes * MINUTE,
        score=Decimal(score),
        status=OpportunityStatus.WATCHING,
        stage=OpportunityStage.NONE,
        direction=TradeDirection.LONG,
        stage_direction=TradeDirection.NEUTRAL,
        regime="bull/normal",
        eligible=True,
        versions=VERSIONS,
    )
    return replace(base, **kwargs)


class TestTheTriggers:
    def test_the_first_sample_is_always_kept(self) -> None:
        verdict = should_record_history(None, mark())
        assert verdict.record is True
        assert verdict.reasons == (REASON_FIRST,)
        assert verdict.policy_version == HISTORY_POLICY_VERSION

    def test_three_points_are_enough_and_two_point_nine_are_not(self) -> None:
        previous = mark(0, "50")
        assert should_record_history(previous, mark(1, "53")).record is True
        assert should_record_history(previous, mark(1, "52.9")).record is False
        assert should_record_history(previous, mark(1, "47")).record is True

    def test_the_delta_is_measured_against_the_last_persisted_sample(self) -> None:
        persisted = mark(0, "50")
        for minutes, score in ((1, "51"), (2, "52"), (3, "52.5")):
            assert should_record_history(persisted, mark(minutes, score)).record is False
        assert should_record_history(persisted, mark(4, "53")).reasons == (REASON_SCORE_DELTA,)

    def test_a_status_change_is_a_row(self) -> None:
        verdict = should_record_history(mark(0), mark(1, status=OpportunityStatus.HOT))
        assert verdict.reasons == (REASON_STATUS,)

    def test_a_stage_change_is_a_row(self) -> None:
        verdict = should_record_history(mark(0), mark(1, stage=OpportunityStage.EARLY))
        assert verdict.reasons == (REASON_STAGE,)

    def test_a_direction_flip_at_the_same_score_is_a_row(self) -> None:
        """Astra, T2.4 design review, item 10: long to short with everything else
        unchanged would otherwise be invisible for five minutes."""
        verdict = should_record_history(mark(0), mark(1, direction=TradeDirection.SHORT))
        assert verdict.reasons == (REASON_DIRECTION,)

    def test_the_published_side_of_the_stage_counts_too(self) -> None:
        verdict = should_record_history(mark(0), mark(1, stage_direction=TradeDirection.SHORT))
        assert verdict.reasons == (REASON_STAGE_DIRECTION,)

    def test_a_regime_change_is_a_row(self) -> None:
        verdict = should_record_history(mark(0), mark(1, regime="bear/high"))
        assert verdict.reasons == (REASON_REGIME,)

    def test_any_version_change_is_a_row(self) -> None:
        verdict = should_record_history(mark(0), mark(1, versions={**VERSIONS, "weights": "v3"}))
        assert verdict.reasons == (REASON_VERSION,)

    def test_losing_or_regaining_eligibility_is_a_row(self) -> None:
        verdict = should_record_history(mark(0), mark(1, eligible=False))
        assert verdict.reasons == (REASON_ELIGIBILITY,)

    def test_five_quiet_minutes_still_leave_a_heartbeat(self) -> None:
        assert should_record_history(mark(0), mark(4)).record is False
        assert should_record_history(mark(0), mark(5)).reasons == (REASON_INTERVAL,)

    def test_several_reasons_come_out_in_the_declared_order(self) -> None:
        verdict = should_record_history(
            mark(0, "50"),
            mark(6, "60", status=OpportunityStatus.HOT, direction=TradeDirection.SHORT),
        )
        assert verdict.reasons == (
            REASON_SCORE_DELTA,
            REASON_STATUS,
            REASON_DIRECTION,
            REASON_INTERVAL,
        )


class TestWhatItRefuses:
    def test_a_redelivered_sample_writes_nothing(self) -> None:
        verdict = should_record_history(mark(1), mark(1, "99"))
        assert verdict.record is False
        assert verdict.reasons == (REASON_STALE,)

    def test_an_out_of_order_sample_writes_nothing(self) -> None:
        assert should_record_history(mark(5), mark(1)).reasons == (REASON_STALE,)

    def test_a_quiet_sample_inside_the_interval_writes_nothing(self) -> None:
        verdict = should_record_history(mark(0), mark(1))
        assert verdict.record is False
        assert verdict.reasons == ()


def test_the_policy_numbers_are_the_ones_the_joint_decision_fixed() -> None:
    policy = HistoryPolicy()
    assert policy.min_score_delta == Decimal("3")
    assert policy.interval == timedelta(minutes=5)
    assert policy.version == "history_v1"


class TestAstraDiffReviewT24:
    def test_a_partial_loss_of_quality_is_recorded(self) -> None:
        """must-fix 5: degrading only the spread kept the score, the status, the
        stage and the global eligibility, and the sample vanished from the
        history — the outage between two periodic samples was invisible."""
        from packages.indicators.tests.unit.test_opportunity_scorer import FULL_VALUES, context

        healthy = score_opportunity(context())
        degraded = score_opportunity(context(FULL_VALUES, degraded_keys=("spread_pct",)))
        assert healthy.score is not None
        assert degraded.score is not None
        assert degraded.confidence < healthy.confidence

        before = mark(0, str(healthy.score), quality=quality_signature(healthy.components))
        after = mark(1, str(degraded.score), quality=quality_signature(degraded.components))
        assert before.quality != after.quality
        assert should_record_history(before, after).reasons == (REASON_QUALITY,)

    def test_the_signature_is_stable_for_the_same_sample(self) -> None:
        from packages.indicators.tests.unit.test_opportunity_scorer import context

        first = score_opportunity(context())
        second = score_opportunity(context())
        assert quality_signature(first.components) == quality_signature(second.components)
        assert "liquidity:1:1/1" in quality_signature(first.components)
