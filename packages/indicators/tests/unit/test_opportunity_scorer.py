"""The score: arithmetic, direction, confidence, envelope, byte reproducibility."""

from __future__ import annotations

import decimal
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyType,
    OpportunityStage,
    TradeDirection,
)
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.anomalies import AnomalyState
from hunter_indicators.baselines import BaselineProjection
from hunter_indicators.opportunity import (
    CONFIDENCE_QUANTUM,
    REASON_NO_EVIDENCE,
    SCORE_QUANTUM,
    ScoreContext,
    ScoreResult,
    WeightProfile,
    explain,
    opportunity_envelope,
    score_opportunity,
)
from hunter_indicators.opportunity.model import quantize
from hunter_indicators.regime import RegimeDecision, RegimeTrend, RegimeVolatility
from packages.indicators.tests.scoring import (
    CONFIG,
    MARKET,
    OBSERVED_AT,
    REGIME_ID,
    TEST_WEIGHTS,
    anomaly,
    degraded,
    ok,
    pending_regime_decision,
    projection,
    regime_decision,
    revision,
    stage_decision,
    vector,
)

PROFILE = WeightProfile.from_weights(TEST_WEIGHTS, version="v2-test")

FULL_VALUES = {
    "momentum_15m": "2",
    "momentum_acceleration": "2",
    "breakout_strength_20": "2",
    "relative_volume_5m": "2",
    "relative_volume_15m": "2",
    "relative_volume_1h": "2",
    "volume_acceleration": "2",
    "spread_pct": "0.5",
    "buy_pressure_5m": "0.7",
    "orderbook_imbalance_20": "0.3",
    "trade_velocity_1m": "2",
    "open_interest_change_1h": "2",
    "open_interest_change_4h": "2",
    "funding_rate": "2",
    "funding_change_8h": "2",
}
"""Every reading four MADs above its median, except the two with their own
baselines below (``buy_pressure_5m`` and ``orderbook_imbalance_20``)."""


def baselines(values: dict[str, str]) -> BaselineProjection:
    special = {
        "buy_pressure_5m": revision("buy_pressure_5m", median="0.5", mad="0.05"),
        "orderbook_imbalance_20": revision("orderbook_imbalance_20", median="0", mad="0.1"),
    }
    return projection(
        *(special.get(key) or revision(key) for key in values),
    )


def context(
    values: dict[str, str] | None = None,
    *,
    stage: OpportunityStage = OpportunityStage.NONE,
    anomalies: Sequence[AnomalyState] = (),
    regime: RegimeDecision | None = None,
    degraded_keys: tuple[str, ...] = (),
    regime_stale: bool = False,
) -> ScoreContext:
    values = FULL_VALUES if values is None else values
    entries = {
        key: (degraded(key, value) if key in degraded_keys else ok(key, value))
        for key, value in values.items()
    }
    return ScoreContext(
        market_id=MARKET,
        vector=vector(entries),
        projection=baselines(values),
        config=CONFIG,
        profile=PROFILE,
        stage=None if stage is OpportunityStage.NONE else stage_decision(stage),
        regime=regime_decision() if regime is None else regime,
        regime_stale=regime_stale,
        anomalies=list(anomalies),
    )


class TestTheArithmeticOfTheJointDecision:
    def test_a_fully_read_market_scores_the_sum_of_its_contributions(self) -> None:
        result = score_opportunity(context())
        assert result.component("momentum").contribution == Decimal("12.0000")
        assert result.component("volume").contribution == Decimal("12.0000")
        assert result.component("liquidity").contribution == Decimal("2.0000")
        assert result.component("order_flow").contribution == Decimal("8.0000")
        assert result.component("derivatives").contribution == Decimal("6.0000")
        assert result.component("market_regime").contribution == Decimal("8.0000")
        assert result.component("anomalies").contribution == Decimal("0.0000")
        assert result.score == Decimal("48.00")

    def test_the_decomposition_adds_up_to_the_score(self) -> None:
        result = score_opportunity(context(stage=OpportunityStage.EARLY))
        total = (
            sum((item.contribution for item in result.components), Decimal(0))
            + result.early_movement.contribution
        )
        assert result.score == total.quantize(Decimal("0.01"))

    def test_the_early_movement_term_is_signed_and_outside_the_budget(self) -> None:
        neutral = score_opportunity(context()).score
        early = score_opportunity(context(stage=OpportunityStage.EARLY))
        extended = score_opportunity(context(stage=OpportunityStage.EXTENDED))
        developing = score_opportunity(context(stage=OpportunityStage.DEVELOPING))
        assert neutral is not None and early.score is not None and extended.score is not None
        assert early.early_movement.e == 1
        assert extended.early_movement.e == -1
        assert developing.early_movement.e == 0
        assert early.score - neutral == Decimal("10.00")
        assert neutral - extended.score == Decimal("10.00")
        assert developing.score == neutral

    def test_the_stage_factor_follows_the_published_stage_and_its_own_side(self) -> None:
        result = score_opportunity(context(stage=OpportunityStage.EARLY))
        assert result.early_movement.stage == "EARLY"
        assert result.early_movement.stage_direction == "long"

    def test_the_score_is_clipped_at_zero(self) -> None:
        result = score_opportunity(context({"spread_pct": "1"}, stage=OpportunityStage.EXTENDED))
        assert result.score == Decimal("0.00")

    def test_an_anomaly_contributes_through_its_own_component(self) -> None:
        result = score_opportunity(context(anomalies=[anomaly(AnomalyType.VOLUME_SPIKE, "80")]))
        assert result.component("anomalies").contribution == Decimal("4.0000")
        assert result.score == Decimal("52.00")


class TestAbsenceDoesNotRedistribute:
    def test_a_missing_component_lowers_the_score_and_the_confidence(self) -> None:
        values = {
            key: value
            for key, value in FULL_VALUES.items()
            if not key.startswith(("open_interest", "funding"))
        }
        full = score_opportunity(context())
        partial = score_opportunity(context(values))
        assert full.score is not None and partial.score is not None
        assert full.score - partial.score == Decimal("6.00")  # exactly the lost weight
        assert partial.component("momentum").contribution == Decimal("12.0000")
        assert partial.confidence < full.confidence
        assert partial.component("derivatives").weight == Decimal("0.10")

    def test_a_zero_weight_component_moves_neither_score_nor_confidence(self) -> None:
        result = score_opportunity(context())
        consensus = result.component("agent_consensus")
        external = result.component("external_intelligence")
        assert consensus.contribution == Decimal("0.0000")
        assert external.contribution == Decimal("0.0000")
        assert consensus.counts_for_confidence is False
        assert external.counts_for_confidence is False


class TestEligibility:
    def test_degraded_evidence_produces_no_new_score(self) -> None:
        result = score_opportunity(context(degraded_keys=tuple(FULL_VALUES), anomalies=[]))
        assert result.eligible is False
        assert result.score is None
        assert result.reason == REASON_NO_EVIDENCE
        assert result.confidence == Decimal("0.0000")

    def test_the_components_are_still_explained_when_nothing_is_eligible(self) -> None:
        result = score_opportunity(context(degraded_keys=tuple(FULL_VALUES)))
        assert len(result.components) == 9
        assert result.component("volume").reason == "no_usable_input"


class TestDirectionAndConfidence:
    def test_the_direction_is_the_weighted_vote_of_the_directional_inputs(self) -> None:
        result = score_opportunity(context())
        assert result.direction is TradeDirection.LONG
        assert result.agreement == Decimal("1.0000")

    def test_a_split_tape_lowers_the_agreement_and_the_confidence(self) -> None:
        agreeing = score_opportunity(context())
        split = score_opportunity(
            context({**FULL_VALUES, "buy_pressure_5m": "0.3", "orderbook_imbalance_20": "-0.3"})
        )
        assert split.agreement is not None and agreeing.agreement is not None
        assert split.agreement < agreeing.agreement
        assert split.confidence < agreeing.confidence
        assert split.direction is TradeDirection.LONG  # momentum still outweighs the tape

    def test_without_a_directional_reading_there_is_no_side(self) -> None:
        result = score_opportunity(context({"relative_volume_5m": "2"}))
        assert result.direction is TradeDirection.NEUTRAL
        assert result.direction_reason == "no_directional_evidence"

    def test_the_regime_is_scored_against_the_direction_the_others_produced(self) -> None:
        result = score_opportunity(context(regime=regime_decision(trend=RegimeTrend.BEAR)))
        component = result.component("market_regime")
        assert result.direction is TradeDirection.LONG
        assert component.detail["direction_input"] == "long"
        assert component.normalized == Decimal("20.0000")

    def test_a_stale_regime_does_not_feed_the_score(self) -> None:
        result = score_opportunity(context(regime_stale=True))
        component = result.component("market_regime")
        assert component.available is False
        assert component.contribution == Decimal("0.0000")

    def test_high_volatility_is_visible_in_the_pair_not_only_in_the_label(self) -> None:
        result = score_opportunity(
            context(regime=regime_decision(volatility=RegimeVolatility.HIGH))
        )
        detail = result.component("market_regime").detail
        assert detail["regime"] == "HIGH_VOLATILITY"
        assert detail["trend"] == "bull"


class TestReproducibility:
    def test_the_same_inputs_serialise_to_the_same_bytes(self) -> None:
        first = score_opportunity(context(stage=OpportunityStage.EARLY))
        second = score_opportunity(context(stage=OpportunityStage.EARLY))
        assert canonical_json(first.decomposition()) == canonical_json(second.decomposition())

    def test_the_ambient_decimal_context_cannot_change_the_score(self) -> None:
        expected = score_opportunity(context()).score
        previous = decimal.getcontext().prec
        try:
            decimal.getcontext().prec = 6
            assert score_opportunity(context()).score == expected
        finally:
            decimal.getcontext().prec = previous

    def test_the_persisted_precision_is_the_agreed_one(self) -> None:
        result = score_opportunity(context())
        assert result.score is not None
        assert int(result.score.as_tuple().exponent) == -2
        assert int(result.confidence.as_tuple().exponent) == -4
        for component in result.components:
            if component.normalized is not None:
                assert int(component.normalized.as_tuple().exponent) == -4
            assert int(component.contribution.as_tuple().exponent) == -4

    def test_the_decomposition_names_every_version_a_replay_needs(self) -> None:
        result = score_opportunity(context(stage=OpportunityStage.EARLY))
        versions = result.decomposition()["versions"]
        assert set(versions) == {
            "scorer",
            "components",
            "weights",
            "features",
            "quality_policy",
            "normalization",
            "stage",
            "regime",
        }
        assert versions["weights"] == "v2-test"
        assert versions["regime"] == "regime_v0"


class TestEnvelope:
    def test_the_envelope_carries_the_sample_that_produced_the_score(self) -> None:
        ctx = context(stage=OpportunityStage.EARLY)
        result = score_opportunity(ctx)
        envelope = opportunity_envelope(result, ctx, regime_id=REGIME_ID)
        assert envelope["as_of"] == ctx.projection.cut.as_of
        assert envelope["observation_ts"] == OBSERVED_AT
        assert envelope["vector"]["values"]["momentum_15m"]["value"] == Decimal("2")
        assert envelope["regime_id"] == str(REGIME_ID)
        assert envelope["state_out"]["stage"]["stage"] == "EARLY"
        assert envelope["decomposition"]["score"] == result.score

    def test_the_envelope_lists_the_baselines_the_deviations_came_from(self) -> None:
        ctx = context()
        result = score_opportunity(ctx)
        envelope = opportunity_envelope(result, ctx)
        assert len(envelope["baseline_ids"]) == len(FULL_VALUES)
        assert envelope["baseline_ids"] == sorted(envelope["baseline_ids"])

    def test_the_envelope_is_byte_stable(self) -> None:
        ctx = context(stage=OpportunityStage.EARLY)
        first = canonical_json(opportunity_envelope(score_opportunity(ctx), ctx))
        second = canonical_json(opportunity_envelope(score_opportunity(ctx), ctx))
        assert first == second


def test_a_result_without_evidence_still_reports_its_versions() -> None:
    result: ScoreResult = score_opportunity(context(degraded_keys=tuple(FULL_VALUES)))
    assert result.decomposition()["versions"]["weights"] == "v2-test"
    assert result.decomposition()["score"] is None


class TestAstraDiffReviewT24:
    """The five findings of ``.claude/state/astra-review-T2.4-diff.md``, each with
    the probe that reproduced it before the fix."""

    def test_evidence_from_after_the_cut_is_refused(self) -> None:
        """must-fix 1: an anomaly of 10:01 moved the score of the 10:00 sample
        from 48 to 52 — a replay pairing an old vector with the newest cache."""
        future = anomaly(AnomalyType.VOLUME_SPIKE, "80")
        later = replace(
            future,
            observation_ts=OBSERVED_AT + timedelta(days=1),
            detected_at=OBSERVED_AT + timedelta(days=1),
        )
        with pytest.raises(ValueError, match="after the cut"):
            context(anomalies=[later])

    def test_a_stage_from_after_the_cut_is_refused(self) -> None:
        with pytest.raises(ValueError, match="after the cut"):
            ctx = context()
            ScoreContext(
                market_id=ctx.market_id,
                vector=ctx.vector,
                projection=ctx.projection,
                config=ctx.config,
                profile=ctx.profile,
                stage=stage_decision(OpportunityStage.EARLY, ts=OBSERVED_AT + timedelta(days=1)),
            )

    def test_the_baselines_and_the_vector_must_describe_one_cut(self) -> None:
        ctx = context()
        with pytest.raises(ValueError, match="one score, one cut"):
            ScoreContext(
                market_id=ctx.market_id,
                vector=vector(
                    {"relative_volume_5m": ok("relative_volume_5m", "2")},
                    ts=OBSERVED_AT - timedelta(minutes=1),
                ),
                projection=ctx.projection,
                config=ctx.config,
                profile=ctx.profile,
            )

    def test_the_ambient_precision_cannot_move_a_contribution_or_a_sentence(self) -> None:
        """must-fix 2: with ``prec = 4`` the contribution of momentum was stored
        as 11.9300 instead of 11.9340, and formatting a saturated 100.0000 under
        ``prec = 6`` raised ``InvalidOperation``."""
        fractional = {**FULL_VALUES, "momentum_15m": "1.98765", "relative_volume_5m": "9"}
        ctx = context(fractional)
        expected = score_opportunity(ctx)
        expected_text = canonical_json(explain(expected))
        previous = decimal.getcontext().prec
        try:
            for precision in (4, 6):
                decimal.getcontext().prec = precision
                again = score_opportunity(context(fractional))
                assert canonical_json(again.decomposition()) == canonical_json(
                    expected.decomposition()
                )
                assert canonical_json(explain(again)) == expected_text
        finally:
            decimal.getcontext().prec = previous

    def test_the_same_anomalies_in_another_order_are_the_same_score_and_bytes(self) -> None:
        """must-fix 3: the sum was already order-free, the stored evidence was not."""
        pair = [anomaly(AnomalyType.VOLUME_SPIKE, "80"), anomaly(AnomalyType.MOMENTUM_SHIFT, "60")]
        first = score_opportunity(context(anomalies=pair))
        second = score_opportunity(context(anomalies=list(reversed(pair))))
        assert first.score == second.score
        assert canonical_json(first.decomposition()) == canonical_json(second.decomposition())
        assert canonical_json(explain(first)) == canonical_json(explain(second))

    def test_an_anomaly_nobody_could_evaluate_lowers_the_confidence(self) -> None:
        """must-fix 4: ``ACTIVE + UNKNOWN`` kept the confidence of a market with
        no anomalies at all — absence of evaluation is not absence of anomaly."""
        known = score_opportunity(
            context(anomalies=[anomaly(AnomalyType.VOLUME_SPIKE, "80", confidence="1")])
        )
        blind = score_opportunity(
            context(
                anomalies=[
                    anomaly(AnomalyType.VOLUME_SPIKE, "80", state=AnomalyEvaluationState.UNKNOWN)
                ]
            )
        )
        empty = score_opportunity(context(anomalies=[]))
        # A fully mature anomaly is as much knowledge as having none; one the
        # detector is only 90% sure of now sits between the two, and one nobody
        # could evaluate below both (cross review, nice-to-have 1).
        unsure = score_opportunity(
            context(anomalies=[anomaly(AnomalyType.VOLUME_SPIKE, "80", confidence="0.9")])
        )
        assert blind.component("anomalies").available is False
        assert blind.confidence < unsure.confidence < empty.confidence == known.confidence


MEDIAN_DIRECTIONALS = {
    **FULL_VALUES,
    "momentum_15m": "1",
    "momentum_acceleration": "1",
    "breakout_strength_20": "1",
    "buy_pressure_5m": "0.5",
    "orderbook_imbalance_20": "0",
}
"""All fifteen readings available; the five directional ones sit **on** their
medians, so every directional vote weighs exactly zero and there is no evidence
about a side — which is not the same statement as "the sides cancel"."""

CANCELLING = {
    **MEDIAN_DIRECTIONALS,
    "momentum_15m": "2",  # severity 60, long: 0.20 * 60 / 3 = 4
    "orderbook_imbalance_20": "-0.5",  # severity 80, short: 0.15 * 80 / 3 = 4
}
"""Two directional inputs of equal weight pulling opposite ways: real evidence,
read contradictorily."""


class TestCrossReviewT24MustFixOne:
    """`no evidence about a side` and `the sides cancel` were the same number.

    Hand arithmetic of the confidence, with no agreement factor at all:
    ``(0.75 * 0.9524 + 0.15 * 1) / 0.90 = 0.9603`` — the five MAD components at
    the maturity of a 400/420 baseline, the regime and the anomalies at one.
    """

    def test_no_directional_evidence_leaves_the_confidence_alone(self) -> None:
        result = score_opportunity(context(MEDIAN_DIRECTIONALS))
        assert result.direction is TradeDirection.NEUTRAL
        assert result.direction_reason == "no_directional_evidence"
        assert result.agreement is None
        assert result.confidence == Decimal("0.9603")
        assert result.score == Decimal("28.00")

    def test_a_directional_reading_changes_the_score_and_not_the_confidence(self) -> None:
        """The probe of the review: moving ``momentum_15m`` from 1 to 2.5 doubled
        the confidence (0.4802 to 0.9603) without one reading getting better."""
        silent = score_opportunity(context(MEDIAN_DIRECTIONALS))
        speaking = score_opportunity(context({**MEDIAN_DIRECTIONALS, "momentum_15m": "2.5"}))
        assert speaking.direction is TradeDirection.LONG
        assert speaking.agreement == Decimal("1.0000")
        assert speaking.confidence == silent.confidence == Decimal("0.9603")
        assert speaking.score == Decimal("37.67")

    def test_an_exact_cancellation_is_a_disagreement_and_keeps_the_floor(self) -> None:
        result = score_opportunity(context(CANCELLING))
        assert result.direction is TradeDirection.NEUTRAL
        assert result.direction_reason == "directional_evidence_cancels"
        assert result.agreement == Decimal("0.0000")
        assert result.confidence == Decimal("0.4802")  # 0.9603 * (1 + 0) / 2

    def test_the_missing_agreement_is_null_in_the_decomposition(self) -> None:
        wire = score_opportunity(context(MEDIAN_DIRECTIONALS)).decomposition()
        assert wire["agreement"] is None
        assert wire["direction_reason"] == "no_directional_evidence"
        assert b'"agreement":null' in canonical_json(wire)

    def test_the_explanation_says_which_of_the_two_it_is(self) -> None:
        silent = explain(score_opportunity(context(MEDIAN_DIRECTIONALS)))["resumo"]
        cancelling = explain(score_opportunity(context(CANCELLING)))["resumo"]
        assert "sem evidência direcional" in silent
        assert "concordância" not in silent
        assert "concordância 0,0000" in cancelling


class TestCrossReviewT24NiceToHaves:
    def test_the_confidence_of_an_anomaly_reaches_the_component(self) -> None:
        """A 90-severity anomaly the detector is 10% sure of still contributes
        4.50 points; what it may not do is contribute them with confidence one."""
        unsure = score_opportunity(
            context(anomalies=[anomaly(AnomalyType.VOLUME_SPIKE, "90", confidence="0.1")])
        )
        sure = score_opportunity(
            context(anomalies=[anomaly(AnomalyType.VOLUME_SPIKE, "90", confidence="1")])
        )
        assert unsure.component("anomalies").contribution == Decimal("4.5000")
        assert unsure.component("anomalies").confidence == Decimal("0.1000")
        assert sure.component("anomalies").confidence == Decimal("1.0000")
        assert unsure.score == sure.score
        assert unsure.confidence < sure.confidence

    def test_the_confidence_of_the_regime_reaches_the_component(self) -> None:
        agreeing = score_opportunity(context())
        disagreeing = score_opportunity(context(regime=regime_decision(trend=RegimeTrend.BEAR)))
        assert agreeing.component("market_regime").confidence == Decimal("1.0000")
        assert disagreeing.component("market_regime").confidence == Decimal("0.6000")

    def test_a_regime_that_cannot_grade_itself_does_not_feed_the_score(self) -> None:
        pending = pending_regime_decision()
        assert pending.trend is RegimeTrend.BULL  # still the published pair
        assert pending.state_out.candidate_trend is RegimeTrend.BEAR  # one reading against it
        assert pending.confidence is None
        result = score_opportunity(context(regime=pending))
        component = result.component("market_regime")
        assert component.available is False
        assert component.reason == "regime_confidence_unknown"
        assert component.contribution == Decimal("0.0000")

    def test_half_even_is_the_rounding_of_the_stored_score(self) -> None:
        """``5.6050`` is exactly on the boundary: HALF_EVEN keeps 5.60, HALF_UP
        would store 5.61. One reading of 1.40125 sits 1.605 MADs out, severity
        12.10, a quarter of the volume component, 0.6050 points."""
        result = score_opportunity(context({"relative_volume_5m": "1.40125"}))
        assert result.component("volume").normalized == Decimal("3.0250")
        assert result.component("volume").contribution == Decimal("0.6050")
        assert result.score == Decimal("5.60")
        assert quantize(Decimal("0.12345"), CONFIDENCE_QUANTUM) == Decimal("0.1234")
        assert quantize(Decimal("48.125"), SCORE_QUANTUM) == Decimal("48.12")
