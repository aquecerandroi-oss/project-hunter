"""EARLY / DEVELOPING / EXTENDED — the three scenarios, hysteresis and precedence.

``r = |return_1h| / atr_14_pct``, both fractions. Every ``r`` below is written out
in the test that uses it, because a stage is a claim about where a move is in its
life and "trust me" is not an acceptable justification for one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import OpportunityStage, TradeDirection
from hunter_indicators.features import DEFAULT_REGISTRY, FeatureValue, FeatureVector, Reason
from hunter_indicators.stage import (
    EMPTY_STAGE_STATE,
    REASON_ATR_DEGRADED,
    REASON_ATR_WARMUP,
    REASON_NOT_CONFIRMED,
    REASON_STAGE_WITHDRAWN,
    STAGE_BASIS_EXHAUSTION,
    STAGE_BASIS_RATIO,
    StageDecision,
    StageInputs,
    StageState,
    StageThresholds,
    classify_stage,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
START = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)

THRESHOLDS = StageThresholds(
    r_early_max=Decimal("1.5"),
    r_developing_max=Decimal("4"),
    relative_volume_1h_min=Decimal("3"),
    trade_velocity_baseline_multiple_min=Decimal("2"),
    open_interest_change_1h_min=Decimal("0.02"),
    buy_pressure_5m_long_min=Decimal("0.60"),
    buy_pressure_5m_short_max=Decimal("0.40"),
    extended_return_4h_atr_multiple=Decimal("3"),
    extended_relative_volume_15m_declines=3,
    extended_relative_volume_15m_closes=4,
    confirmations=2,
    weights_version="v2",
)


def vector(
    values: dict[str, Decimal],
    *,
    ts: datetime = START,
    overrides: dict[str, FeatureValue] | None = None,
) -> FeatureVector:
    entries = {key: FeatureValue.ok(key, value) for key, value in values.items()}
    entries.update(overrides or {})
    return FeatureVector(
        exchange="binance",
        symbol="BTCUSDT",
        ts=ts,
        feature_set_version=DEFAULT_REGISTRY.feature_set_version,
        values=entries,
    )


def early_values(*, return_1h: str = "0.028", atr: str = "0.02") -> dict[str, Decimal]:
    """The directive's scenario: volume 4.7x, trades +320%, OI +15%, price +2.8%."""
    return {
        "return_1h": Decimal(return_1h),
        "atr_14_pct": Decimal(atr),
        "relative_volume_1h": Decimal("4.7"),
        "trade_velocity_1m": Decimal("4.2"),
        "open_interest_change_1h": Decimal("0.15"),
        "buy_pressure_5m": Decimal("0.72"),
    }


def inputs(
    trade_velocity_baseline: str | None = "1",
    relative_volume_15m_closes: tuple[Decimal, ...] = (),
) -> StageInputs:
    return StageInputs(
        trade_velocity_baseline=(
            None if trade_velocity_baseline is None else Decimal(trade_velocity_baseline)
        ),
        relative_volume_15m_closes=relative_volume_15m_closes,
    )


def classify(
    values: dict[str, Decimal],
    *,
    state: StageState = EMPTY_STAGE_STATE,
    ts: datetime = START,
    extra: StageInputs | None = None,
    overrides: dict[str, FeatureValue] | None = None,
) -> StageDecision:
    return classify_stage(
        vector(values, ts=ts, overrides=overrides),
        thresholds=THRESHOLDS,
        state=state,
        inputs=extra or inputs(),
    )


class TestTheThreeScenarios:
    def test_early_when_the_move_is_small_and_every_confirmation_fired(self) -> None:
        # 0.028 / 0.02 = 1.4 < 1.5
        first = classify(early_values())
        assert first.candidate is OpportunityStage.EARLY
        assert first.r == Decimal("1.4")
        assert first.direction is TradeDirection.LONG
        # one observation is not enough: the stage is published on the second
        assert first.stage is OpportunityStage.NONE
        second = classify(early_values(), state=first.state_out, ts=START + timedelta(minutes=1))
        assert second.stage is OpportunityStage.EARLY
        assert second.basis == STAGE_BASIS_RATIO

    def test_developing_between_the_two_ratios(self) -> None:
        # 0.04 / 0.02 = 2
        values = early_values(return_1h="0.04")
        first = classify(values)
        second = classify(values, state=first.state_out, ts=START + timedelta(minutes=1))
        assert second.stage is OpportunityStage.DEVELOPING
        assert second.r == Decimal("2")

    def test_extended_when_the_move_already_ran(self) -> None:
        # 0.028 / 0.005 = 5.6 > 4
        values = early_values(atr="0.005")
        first = classify(values)
        second = classify(values, state=first.state_out, ts=START + timedelta(minutes=1))
        assert second.stage is OpportunityStage.EXTENDED
        assert second.r == Decimal("5.6")


class TestBoundaries:
    def test_the_early_boundary_is_strict(self) -> None:
        # r exactly 1.5 is DEVELOPING, not EARLY
        assert classify(early_values(return_1h="0.03")).candidate is OpportunityStage.DEVELOPING

    def test_the_developing_boundary_includes_four(self) -> None:
        assert classify(early_values(return_1h="0.08")).candidate is OpportunityStage.DEVELOPING

    def test_just_over_four_is_extended(self) -> None:
        assert classify(early_values(return_1h="0.081")).candidate is OpportunityStage.EXTENDED

    def test_a_short_move_is_classified_by_magnitude(self) -> None:
        values = early_values(return_1h="-0.028")
        values["buy_pressure_5m"] = Decimal("0.30")
        decision = classify(values)
        assert decision.direction is TradeDirection.SHORT
        assert decision.candidate is OpportunityStage.EARLY

    def test_a_flat_return_confirms_nothing(self) -> None:
        values = early_values(return_1h="0")
        decision = classify(values)
        assert decision.direction is TradeDirection.NEUTRAL
        assert decision.candidate is OpportunityStage.NONE
        assert decision.reason == REASON_NOT_CONFIRMED


class TestConfirmations:
    def test_every_confirmation_is_necessary(self) -> None:
        values = early_values()
        values["relative_volume_1h"] = Decimal("2.9")
        decision = classify(values)
        assert decision.candidate is OpportunityStage.NONE
        assert decision.confirmations["relative_volume_1h"] is False

    def test_an_unavailable_confirmation_does_not_confirm(self) -> None:
        decision = classify(
            early_values(),
            overrides={
                "open_interest_change_1h": FeatureValue.unavailable(
                    "open_interest_change_1h", Reason.MISSING_INPUT
                )
            },
        )
        assert decision.candidate is OpportunityStage.NONE
        assert decision.confirmations["open_interest_change_1h"] is False

    def test_trade_velocity_is_compared_against_its_baseline(self) -> None:
        values = early_values()
        values["trade_velocity_1m"] = Decimal("1.9")
        decision = classify(values, extra=inputs(trade_velocity_baseline="1"))
        assert decision.confirmations["trade_velocity_1m"] is False

    def test_without_a_baseline_trade_velocity_cannot_confirm(self) -> None:
        decision = classify(early_values(), extra=inputs(trade_velocity_baseline=None))
        assert decision.confirmations["trade_velocity_1m"] is False
        assert decision.candidate is OpportunityStage.NONE

    def test_the_short_side_uses_the_mirrored_pressure_threshold(self) -> None:
        values = early_values(return_1h="-0.028")
        values["buy_pressure_5m"] = Decimal("0.45")
        decision = classify(values)
        assert decision.confirmations["buy_pressure_5m"] is False


class TestExtendedAlternative:
    def falling(self) -> tuple[Decimal, ...]:
        return (Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1"))

    def test_exhaustion_extends_a_move_that_is_not_over_four_atrs(self) -> None:
        # r = 0.028/0.02 = 1.4 (EARLY territory), but |return_4h| = 0.07 > 3*0.02
        # and the 15-minute relative volume fell three times over four closes.
        values = early_values()
        values["return_4h"] = Decimal("0.07")
        decision = classify(values, extra=inputs(relative_volume_15m_closes=self.falling()))
        assert decision.candidate is OpportunityStage.EXTENDED
        assert decision.basis == STAGE_BASIS_EXHAUSTION

    def test_three_strict_declines_are_required(self) -> None:
        values = early_values()
        values["return_4h"] = Decimal("0.07")
        flat = (Decimal("4"), Decimal("3"), Decimal("3"), Decimal("1"))
        decision = classify(values, extra=inputs(relative_volume_15m_closes=flat))
        assert decision.candidate is OpportunityStage.EARLY

    def test_four_closes_are_required(self) -> None:
        values = early_values()
        values["return_4h"] = Decimal("0.07")
        short = (Decimal("3"), Decimal("2"), Decimal("1"))
        decision = classify(values, extra=inputs(relative_volume_15m_closes=short))
        assert decision.candidate is OpportunityStage.EARLY

    def test_precedence_extended_beats_developing_and_early(self) -> None:
        values = early_values(return_1h="0.04")  # r = 2 -> DEVELOPING
        values["return_4h"] = Decimal("0.07")
        decision = classify(values, extra=inputs(relative_volume_15m_closes=self.falling()))
        assert decision.candidate is OpportunityStage.EXTENDED


class TestWarmUpAndQuality:
    def test_without_an_atr_there_is_no_stage(self) -> None:
        decision = classify(
            early_values(),
            overrides={"atr_14_pct": FeatureValue.unavailable("atr_14_pct", Reason.WARMUP)},
        )
        assert decision.candidate is OpportunityStage.NONE
        assert decision.reason == REASON_ATR_WARMUP

    def test_a_zero_atr_is_not_a_divisor(self) -> None:
        values = early_values(atr="0")
        decision = classify(values)
        assert decision.candidate is OpportunityStage.NONE
        assert decision.reason == REASON_ATR_WARMUP

    def test_losing_quality_invalidates_the_published_stage_at_once(self) -> None:
        values = early_values(return_1h="0.04")
        first = classify(values)
        published = classify(values, state=first.state_out, ts=START + timedelta(minutes=1))
        assert published.stage is OpportunityStage.DEVELOPING
        blind = classify(
            values,
            state=published.state_out,
            ts=START + timedelta(minutes=2),
            overrides={"atr_14_pct": FeatureValue.unavailable("atr_14_pct", Reason.GAP)},
        )
        assert blind.stage is OpportunityStage.NONE
        assert blind.invalidated is True
        assert blind.state_out.confirmations == 0

    def test_a_degraded_input_also_invalidates(self) -> None:
        from hunter_indicators.features import Quality

        values = early_values(return_1h="0.04")
        first = classify(values)
        published = classify(values, state=first.state_out, ts=START + timedelta(minutes=1))
        degraded = FeatureValue.ok("return_1h", Decimal("0.04")).degraded_to(
            Quality.DEGRADED, Reason.STALE_INPUT
        )
        blind = classify(
            values,
            state=published.state_out,
            ts=START + timedelta(minutes=2),
            overrides={"return_1h": degraded},
        )
        assert blind.stage is OpportunityStage.NONE
        assert blind.invalidated is True


class TestHysteresis:
    def test_a_new_candidate_needs_two_distinct_observations(self) -> None:
        early = early_values()
        first = classify(early)
        published = classify(early, state=first.state_out, ts=START + timedelta(minutes=1))
        assert published.stage is OpportunityStage.EARLY

        developing = early_values(return_1h="0.04")
        pending = classify(developing, state=published.state_out, ts=START + timedelta(minutes=2))
        assert pending.stage is OpportunityStage.EARLY
        assert pending.candidate is OpportunityStage.DEVELOPING
        confirmed = classify(developing, state=pending.state_out, ts=START + timedelta(minutes=3))
        assert confirmed.stage is OpportunityStage.DEVELOPING

    def test_a_duplicate_observation_does_not_confirm(self) -> None:
        early = early_values()
        first = classify(early)
        again = classify(early, state=first.state_out, ts=START)
        assert again.stage is OpportunityStage.NONE
        assert again.state_out.confirmations == first.state_out.confirmations

    def test_an_older_observation_does_not_move_the_state(self) -> None:
        early = early_values()
        first = classify(early)
        published = classify(early, state=first.state_out, ts=START + timedelta(minutes=1))
        stale = classify(early, state=published.state_out, ts=START)
        assert stale.stage is OpportunityStage.EARLY
        assert stale.state_out == published.state_out

    def test_a_flapping_candidate_restarts_the_count(self) -> None:
        early = early_values()
        first = classify(early)
        published = classify(early, state=first.state_out, ts=START + timedelta(minutes=1))
        developing = classify(
            early_values(return_1h="0.04"),
            state=published.state_out,
            ts=START + timedelta(minutes=2),
        )
        assert developing.state_out.confirmations == 1
        back = classify(early, state=developing.state_out, ts=START + timedelta(minutes=3))
        assert back.stage is OpportunityStage.EARLY
        assert back.state_out.confirmations == 0


class TestThresholdsComeFromTheWeights:
    def test_read_from_the_weight_vector(self) -> None:
        weights = {
            "stage": {
                "r_early_max": "1.5",
                "r_developing_max": "4",
                "relative_volume_1h_min": "3",
                "trade_velocity_baseline_multiple_min": "2",
                "open_interest_change_1h_min": "0.02",
                "buy_pressure_5m_long_min": "0.60",
                "buy_pressure_5m_short_max": "0.40",
                "extended_return_4h_atr_multiple": "3",
                "extended_relative_volume_15m_declines": 3,
                "extended_relative_volume_15m_closes": 4,
                "confirmations": 2,
            }
        }
        assert StageThresholds.from_weights(weights, version="v2") == THRESHOLDS

    def test_a_vector_without_the_block_is_refused(self) -> None:
        with pytest.raises(KeyError):
            StageThresholds.from_weights({"components": {}}, version="v2")


class TestEnvelope:
    def test_the_decision_carries_state_in_and_state_out(self) -> None:
        decision = classify(early_values())
        assert decision.state_in == StageState()
        assert decision.state_out.candidate is OpportunityStage.EARLY
        wire = decision.as_wire()
        assert wire["state_in"]["stage"] == "NONE"
        assert wire["state_out"]["candidate"] == "EARLY"
        assert wire["thresholds_version"] == "v2"
        assert wire["r"] == Decimal("1.4")


class TestAstraDiffReview:
    """Regressions for findings 4 and 5 of ``astra-review-T2.3-diff.md``."""

    def test_two_computations_of_one_minute_do_not_confirm_twice(self) -> None:
        # ``vector.ts`` is ``ctx.as_of`` — the instant of processing. Recomputing
        # the same minute a second later must not be a second observation.
        early = early_values()
        first = classify(early)
        again = classify(early, state=first.state_out, ts=START + timedelta(seconds=1))
        assert again.stage is OpportunityStage.NONE
        assert again.reason == "stale_observation"

    def test_a_minute_later_does_confirm(self) -> None:
        early = early_values()
        first = classify(early)
        later = classify(early, state=first.state_out, ts=START + timedelta(minutes=1, seconds=7))
        assert later.stage is OpportunityStage.EARLY

    def test_losing_the_trade_velocity_baseline_invalidates_early_at_once(self) -> None:
        # Finding 5: the baseline is an input of the published EARLY, and it does
        # not live in the vector, so ``_required_keys`` never saw it disappear.
        early = early_values()
        first = classify(early)
        published = classify(early, state=first.state_out, ts=START + timedelta(minutes=1))
        assert published.stage is OpportunityStage.EARLY
        blind = classify(
            early,
            state=published.state_out,
            ts=START + timedelta(minutes=2),
            extra=inputs(trade_velocity_baseline=None),
        )
        assert blind.stage is OpportunityStage.NONE
        assert blind.invalidated is True
        assert blind.state_out.confirmations == 0

    def test_losing_the_volume_history_invalidates_an_exhaustion_extended(self) -> None:
        values = early_values()
        values["return_4h"] = Decimal("0.07")
        falling = (Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1"))
        first = classify(values, extra=inputs(relative_volume_15m_closes=falling))
        published = classify(
            values,
            state=first.state_out,
            ts=START + timedelta(minutes=1),
            extra=inputs(relative_volume_15m_closes=falling),
        )
        assert published.stage is OpportunityStage.EXTENDED
        assert published.basis == STAGE_BASIS_EXHAUSTION
        blind = classify(
            values,
            state=published.state_out,
            ts=START + timedelta(minutes=2),
            extra=inputs(relative_volume_15m_closes=()),
        )
        assert blind.stage is OpportunityStage.NONE
        assert blind.invalidated is True

    def test_the_envelope_carries_the_external_inputs(self) -> None:
        decision = classify(early_values())
        wire = decision.as_wire()
        assert wire["inputs"]["trade_velocity_baseline"] == Decimal("1")
        assert wire["inputs"]["relative_volume_15m_closes"] == []


class TestCrossReviewPublishedDirection:
    """The state carries the direction of the **published** stage.

    ``StageDecision.direction`` is the sign of *this* observation's
    ``return_1h``; the published stage is a claim that was confirmed two
    observations ago and it has a side of its own. Without it in
    :class:`StageState` the side is lost on restart — the scanner reloads the
    state, gets a duplicate or an out-of-order observation and can only report
    ``NEUTRAL`` for an EARLY it is still publishing — and a sign inversion would
    silently repaint a published long as a short.
    """

    def reloaded(self, state: StageState) -> StageState:
        """The state as a restarted scanner rebuilds it from the envelope."""
        wire = state.as_wire()
        return StageState(
            stage=OpportunityStage(wire["stage"]),
            basis=wire["basis"],
            candidate=OpportunityStage(wire["candidate"]),
            confirmations=wire["confirmations"],
            last_observation_ts=wire["last_observation_ts"],
            direction=TradeDirection(wire["direction"]),
            candidate_direction=TradeDirection(wire["candidate_direction"]),
        )

    def published_long(self) -> StageDecision:
        early = early_values()
        first = classify(early)
        return classify(early, state=first.state_out, ts=START + timedelta(minutes=1))

    def test_the_state_records_the_side_of_the_published_stage(self) -> None:
        published = self.published_long()
        assert published.stage is OpportunityStage.EARLY
        assert published.state_out.direction is TradeDirection.LONG
        assert published.as_wire()["state_out"]["direction"] == TradeDirection.LONG.value
        assert published.published_direction is TradeDirection.LONG

    def test_a_duplicate_observation_after_a_restart_keeps_the_side(self) -> None:
        published = self.published_long()
        state = self.reloaded(published.state_out)
        assert state.direction is TradeDirection.LONG
        again = classify(early_values(), state=state, ts=START + timedelta(minutes=1))
        assert again.reason == "stale_observation"
        assert again.stage is OpportunityStage.EARLY
        assert again.published_direction is TradeDirection.LONG
        assert again.state_out.direction is TradeDirection.LONG

    def test_a_sign_inversion_does_not_repaint_the_published_stage(self) -> None:
        published = self.published_long()
        short = early_values(return_1h="-0.028")
        short["buy_pressure_5m"] = Decimal("0.30")
        flipped = classify(short, state=published.state_out, ts=START + timedelta(minutes=2))
        # this observation is short, but what is *published* is still the long EARLY
        assert flipped.direction is TradeDirection.SHORT
        assert flipped.stage is OpportunityStage.EARLY
        assert flipped.published_direction is TradeDirection.LONG
        assert flipped.state_out.candidate_direction is TradeDirection.SHORT
        assert flipped.state_out.confirmations == 1

    def test_two_inverted_observations_republish_the_other_side(self) -> None:
        published = self.published_long()
        short = early_values(return_1h="-0.028")
        short["buy_pressure_5m"] = Decimal("0.30")
        flipped = classify(short, state=published.state_out, ts=START + timedelta(minutes=2))
        confirmed = classify(short, state=flipped.state_out, ts=START + timedelta(minutes=3))
        assert confirmed.stage is OpportunityStage.EARLY
        assert confirmed.published_direction is TradeDirection.SHORT

    def test_invalidation_drops_the_side_with_the_stage(self) -> None:
        published = self.published_long()
        blind = classify(
            early_values(),
            state=published.state_out,
            ts=START + timedelta(minutes=2),
            extra=inputs(trade_velocity_baseline=None),
        )
        assert blind.stage is OpportunityStage.NONE
        assert blind.state_out.direction is TradeDirection.NEUTRAL
        assert blind.published_direction is TradeDirection.NEUTRAL


class TestCrossReviewAtrReason:
    """``atr_warmup`` and ``atr_degraded`` are different facts about the ATR."""

    def test_a_missing_atr_is_still_a_warmup(self) -> None:
        decision = classify(
            early_values(),
            overrides={"atr_14_pct": FeatureValue.unavailable("atr_14_pct", Reason.WARMUP)},
        )
        assert decision.reason == REASON_ATR_WARMUP

    def test_a_zero_atr_is_a_warmup_not_a_degradation(self) -> None:
        assert classify(early_values(atr="0")).reason == REASON_ATR_WARMUP

    def test_a_degraded_atr_says_degraded(self) -> None:
        from hunter_indicators.features import Quality

        degraded = FeatureValue.ok("atr_14_pct", Decimal("0.02")).degraded_to(
            Quality.DEGRADED, Reason.STALE_INPUT
        )
        decision = classify(early_values(), overrides={"atr_14_pct": degraded})
        assert decision.reason == REASON_ATR_DEGRADED

    def test_a_gap_in_the_atr_is_a_degradation_not_a_warmup(self) -> None:
        # "the ATR does not exist yet" and "the ATR we have cannot be believed"
        # send an operator to two different places.
        decision = classify(
            early_values(),
            overrides={"atr_14_pct": FeatureValue.unavailable("atr_14_pct", Reason.GAP)},
        )
        assert decision.reason == REASON_ATR_DEGRADED


class TestAstraFixesReviewWithdrawal:
    """Astra, revisão do fix-pass: um estágio sem sustentação tem de cair.

    Hysteresis over the ``(stage, direction)`` pair protects the side, but on its
    own it also protects the *stage*: a market alternating long and short
    restarts the candidate count on every observation, the count never reaches
    two, and a DEVELOPING published half an hour ago stays published forever.
    Astra reproduced exactly that. Withdrawing a claim and publishing a new one
    are different decisions: two observations that do not support what is
    published take it down to ``NONE``; publishing the replacement still needs
    two observations of the *same* pair.
    """

    def alternating(self, index: int) -> dict[str, Decimal]:
        """EARLY territory (r = 0.005), flipping side on every observation."""
        if index % 2 == 0:
            return early_values(return_1h="0.0001")
        values = early_values(return_1h="-0.0001")
        values["buy_pressure_5m"] = Decimal("0.30")
        return values

    def published_developing(self) -> StageDecision:
        values = early_values(return_1h="0.04")  # r = 2
        first = classify(values)
        return classify(values, state=first.state_out, ts=START + timedelta(minutes=1))

    def test_an_alternating_sign_does_not_keep_an_old_stage_alive(self) -> None:
        published = self.published_developing()
        assert published.stage is OpportunityStage.DEVELOPING
        state = published.state_out
        decisions: list[StageDecision] = []
        for index in range(6):
            decision = classify(
                self.alternating(index), state=state, ts=START + timedelta(minutes=2 + index)
            )
            decisions.append(decision)
            state = decision.state_out
        assert decisions[0].stage is OpportunityStage.DEVELOPING  # one observation is not enough
        assert decisions[1].stage is OpportunityStage.NONE  # two unsupported ones take it down
        assert decisions[1].reason == REASON_STAGE_WITHDRAWN
        assert decisions[1].state_out.direction is TradeDirection.NEUTRAL
        # and the alternation never publishes anything of its own
        assert all(decision.stage is OpportunityStage.NONE for decision in decisions[1:])

    def test_a_steady_candidate_still_publishes_after_the_withdrawal(self) -> None:
        published = self.published_developing()
        state = published.state_out
        for index in range(2):
            state = classify(
                self.alternating(index), state=state, ts=START + timedelta(minutes=2 + index)
            ).state_out
        assert state.stage is OpportunityStage.NONE
        steady = early_values(return_1h="0.0001")
        first = classify(steady, state=state, ts=START + timedelta(minutes=4))
        second = classify(steady, state=first.state_out, ts=START + timedelta(minutes=5))
        assert second.stage is OpportunityStage.EARLY
        assert second.published_direction is TradeDirection.LONG

    def test_the_published_stage_is_re_affirmed_before_anything_is_withdrawn(self) -> None:
        # One unsupported observation followed by the published pair again clears
        # the count: this is the flapping the hysteresis is *supposed* to absorb.
        published = self.published_developing()
        developing = early_values(return_1h="0.04")
        away = classify(
            self.alternating(0), state=published.state_out, ts=START + timedelta(minutes=2)
        )
        assert away.stage is OpportunityStage.DEVELOPING
        assert away.state_out.unsupported == 1
        back = classify(developing, state=away.state_out, ts=START + timedelta(minutes=3))
        assert back.stage is OpportunityStage.DEVELOPING
        assert back.state_out.unsupported == 0
