"""``trendline_bounce_v1`` — the same drawn geometry, one door, and no invalidation.

The series are **not** rewritten here: they are the two waves
``test_trendline_breakout_v1`` already documents formula by formula, imported so
that "the geometry is identical to the mother's" can be *asserted* instead of
asserted about a lookalike. From those formulas every expected number below
follows without running the detector:

```
ascending wave, slope +0.5, cut on bar 115 (a trough, so the bounce is confirmed
on the decision bar itself); every true range is 20, so ATR = 20 exactly

reference = support(115) + 15            = 1072.5   (0.75 ATR above the line)
line      = support(115)                 = 1057.5
pivot low = 1052.5                       (closer than 2 ATR, so the ATR floor wins)
stop      = min(1052.5, 1072.5 - 2*20)   = 1032.5
risk                                     = 40       = 2 ATR exactly
target1   = 1072.5 + max(35, 2*40)       = 1152.5   (2 R beats the channel)
```

Volume in that wave is a flat 10 on every bar, so the median of the 96-bar
baseline is 10 and the relative volume of the decision bar is **exactly 1.0** —
which is exactly ``rvol_min``. That is deliberate: the frozen series is the proof
that the gate is inclusive, and dropping the last bar's volume to 9 is the proof
that it exists at all.

Run: ``uv run pytest packages/core/tests/unit/strategies/test_trendline_bounce_v1.py -q``
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import (
    Decision,
    EvaluationState,
    StrategyContext,
    build_context,
)
from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.constraints import check_ranges
from hunter_core.strategies.trendline_bounce_v1 import TRENDLINE_BOUNCE_V1
from hunter_core.strategies.trendline_breakout_v1 import TRENDLINE_BREAKOUT_V1

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, explode, flat, minute, series
from .test_trendline_breakout_v1 import BOUNCE_CUT, CUT, support
from .test_trendline_breakout_v1 import build_bounce_series as bounce_series
from .test_trendline_breakout_v1 import build_series as breakout_series

pytestmark = pytest.mark.unit

PARAMS = TRENDLINE_BOUNCE_V1.default_parameters
UP = D("0.5")
BAR_MINUTES = 15

FROZEN_DIGESTS = {
    # The six rows already activated on the VPS. Adding a module must not move
    # one of them: a moved digest is ``code_ref_mismatch`` in
    # ``load_version_roster`` and the whole Lab goes silent behind a green
    # ``/ready`` (T3.26c, T3.33, T3.34c).
    "momentum_v1": "ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c",
    "volume_anomaly_v1": "9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22",
    "breakout_v1": "4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1",
    "mean_reversion_v1": "a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f",
    "session_orb_v1": "a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba",
    "trendline_breakout_v1": ("7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648"),
}


def ctx_of(
    candles: list[NormalizedCandle], cut: Any = BOUNCE_CUT, *, eligible: bool = True
) -> StrategyContext:
    return build_context(
        candles,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        source_bar_close=cut,
        eligible=eligible,
        eligibility_reason=None if eligible else "not_monitored",
    )


def context() -> StrategyContext:
    """The triggering context, for whoever wants a decision from this version."""
    return ctx_of(bounce_series())


def explain(candles: list[NormalizedCandle], cut: Any = BOUNCE_CUT, **overrides: Any):
    params: Mapping[str, Any] = {**PARAMS, **overrides}
    return TRENDLINE_BOUNCE_V1.explain(ctx_of(candles, cut), params)


def envelope_of(decision: Any) -> dict[str, Any]:
    return {f.name: f.value for f in decision.supporting_features.features}


def with_last_volume(candles: list[NormalizedCandle], volume: Decimal) -> list[NormalizedCandle]:
    """The same tape with the decision bar's volume replaced.

    ``conftest.explode`` puts the whole bar's volume in its **first** minute, so
    the only candle to touch is the one that opens the last 15-minute bar. The
    geometry never reads volume, so this changes the relative volume and nothing
    else — which is what makes it a test of the gate rather than of the drawing.
    """
    copied = list(candles)
    first_minute = -BAR_MINUTES
    copied[first_minute] = copied[first_minute].model_copy(update={"volume": volume})
    return copied


# --------------------------------------------------------------- 1. identity


class TestIdentity:
    def test_the_frozen_identity(self) -> None:
        assert TRENDLINE_BOUNCE_V1.key == "trendline_bounce_v1"
        assert TRENDLINE_BOUNCE_V1.version == "v1"
        assert TRENDLINE_BOUNCE_V1.timeframe is Timeframe.M15

    def test_every_parameter_the_schema_declares_has_a_default_and_vice_versa(self) -> None:
        schema = TRENDLINE_BOUNCE_V1.parameters_schema
        assert set(schema["required"]) == set(PARAMS)
        assert schema["additionalProperties"] is False

    def test_the_door_is_an_identity_and_not_a_knob(self) -> None:
        """No ``mode`` and no breakout tolerance: this version cannot be turned
        back into the other experiment by a ``--set`` on ``derive_variant.py``."""
        assert "mode" not in PARAMS
        assert "max_violations_breakout" not in PARAMS
        assert "max_violations_bounce" in PARAMS

    def test_the_contract_is_the_mothers_minus_two_plus_nothing(self) -> None:
        mother = set(TRENDLINE_BREAKOUT_V1.default_parameters)

        assert set(PARAMS) == mother - {"mode", "max_violations_breakout"}
        assert len(PARAMS) == 34

    def test_the_params_hash_is_pinned(self) -> None:
        """The identity a shadow signal carries. It changes only when the frozen
        contract changes, and that is a new version, never an edit."""
        assert params_hash(dict(PARAMS)) == (
            "9b1e882f169c89ca549e2386d032ee1fa61e4447c1226058fa8796b902dc7ca6"
        )

    def test_only_the_rvol_floor_differs_in_value_from_the_mother(self) -> None:
        """One experiment moves one number. Every shared parameter is inherited
        verbatim so the paired contrast is about the door, the invalidation and
        the volume gate — and nothing else."""
        mother = TRENDLINE_BREAKOUT_V1.default_parameters
        moved = {name for name in PARAMS if PARAMS[name] != mother[name]}

        assert moved == {"rvol_min"}
        assert PARAMS["rvol_min"] == D("1.0") < mother["rvol_min"] == D("1.5")


# --------------------------------------------------------- 2. the decision


class TestTheBounce:
    def test_it_fires_with_the_levels_the_geometry_dictates(self) -> None:
        result = explain(bounce_series())

        assert (result.state, result.reason) == (EvaluationState.TRIGGERED, "signal")
        decision = result.decision
        assert decision is not None
        assert decision.direction is TradeDirection.LONG
        atr = decision.supporting_features.atr
        assert atr is not None and atr.value == D("20")
        assert decision.reference_price == support(115, UP) + D("15") == D("1072.5")
        assert decision.stop == D("1072.5") - 2 * D("20") == D("1032.5")
        assert decision.target1 == D("1072.5") + 2 * D("40") == D("1152.5")
        assert decision.horizon_s == 28800
        assert decision.confidence == D("0.5")

    def test_there_is_no_invalidation_at_all(self) -> None:
        """The point of the version (T3.34c 4b): the line is still drawn, still
        recorded in the envelope, and no longer a level that can close a trade."""
        decision = explain(bounce_series()).decision

        assert decision is not None
        assert decision.invalidations == ()
        assert envelope_of(decision)["line_price_at_decision"] == support(115, UP) == D("1057.5")

    def test_the_reason_names_the_volume_that_decided(self) -> None:
        decision = explain(bounce_series()).decision

        assert decision is not None
        assert "repique de um support ascendente" in decision.reason
        assert "0.75 ATR da linha" in decision.reason
        assert "volume relativo 1.00x" in decision.reason
        assert "ATR% 1.86%" in decision.reason

    def test_the_envelope_carries_the_drawing_and_the_volume(self) -> None:
        decision = explain(bounce_series()).decision

        assert decision is not None
        features = envelope_of(decision)
        assert features["event_kind"] == "bounce"
        assert features["line_kind"] == "support"
        assert features["line_slope_per_bar"] == UP
        assert features["close_15m"] == D("1072.5")
        assert features["relative_volume_15m"] == D("1")
        assert features["volume_median_15m"] == D("10")
        assert features["pivot_low_price"] == D("1052.5")


class TestGeometryParityWithTheMother:
    """The three declared differences, and the proof that they are the only ones.

    Both versions read the same ``tl_scan`` with the same ``pattern_params``, so
    on a bar both of them take, every number the drawing produced has to agree
    digit for digit. If it ever stops agreeing, one of the two silently forked
    the geometry — and the paired contrast against ``v1`` would be measuring that
    fork instead of the hypothesis.
    """

    def test_the_levels_and_the_drawing_are_identical(self) -> None:
        mine = explain(bounce_series()).decision
        hers = TRENDLINE_BREAKOUT_V1.explain(
            ctx_of(bounce_series()), TRENDLINE_BREAKOUT_V1.default_parameters
        ).decision

        assert mine is not None and hers is not None
        assert (mine.reference_price, mine.stop, mine.target1) == (
            hers.reference_price,
            hers.stop,
            hers.target1,
        )
        assert mine.horizon_s == hers.horizon_s
        assert mine.confidence == hers.confidence
        drawing = ("line_", "event_", "pivot_", "pattern_", "channel_", "atr_pct")
        ours, theirs = envelope_of(mine), envelope_of(hers)
        shared = {k: v for k, v in ours.items() if k.startswith(drawing)}
        assert shared == {k: v for k, v in theirs.items() if k.startswith(drawing)}
        assert shared["pattern_params"] == theirs["pattern_params"]

    def test_the_atr_reading_is_the_same_reading(self) -> None:
        mine = explain(bounce_series()).decision
        hers = TRENDLINE_BREAKOUT_V1.explain(
            ctx_of(bounce_series()), TRENDLINE_BREAKOUT_V1.default_parameters
        ).decision

        assert mine is not None and hers is not None
        assert mine.supporting_features.atr == hers.supporting_features.atr

    def test_only_the_invalidation_and_the_provenance_differ(self) -> None:
        mine = explain(bounce_series()).decision
        hers = TRENDLINE_BREAKOUT_V1.explain(
            ctx_of(bounce_series()), TRENDLINE_BREAKOUT_V1.default_parameters
        ).decision

        assert mine is not None and hers is not None
        assert len(hers.invalidations) == 1
        assert mine.invalidations == ()
        assert mine.supporting_features.strategy_key == "trendline_bounce_v1"
        assert hers.supporting_features.strategy_key == "trendline_breakout_v1"

    def test_the_breakout_door_is_shut(self) -> None:
        """The descending wave breaks its resistance on the last bar: ``v1``
        signals, this version reports that nothing it looks for happened."""
        hers = TRENDLINE_BREAKOUT_V1.explain(
            ctx_of(breakout_series(), CUT), TRENDLINE_BREAKOUT_V1.default_parameters
        )
        mine = explain(breakout_series(), CUT)

        assert hers.state is EvaluationState.TRIGGERED
        assert (mine.state, mine.reason) == (EvaluationState.NOT_TRIGGERED, "no_event")


# ------------------------------------------------- 3. the gate that is new


class TestTheVolumeGate:
    def test_a_bounce_at_exactly_the_median_passes(self) -> None:
        """``rvol_min`` is inclusive: 1.0 is "at least the median", not "above"."""
        result = explain(bounce_series())

        assert result.state is EvaluationState.TRIGGERED
        assert envelope_of(result.decision)["relative_volume_15m"] == D("1")

    def test_a_quiet_bounce_is_refused_with_its_number(self) -> None:
        quiet = with_last_volume(bounce_series(), D("9"))

        result = explain(quiet)

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "rvol_low")
        assert result.detail["relative_volume_15m"] == "0.9"

    def test_the_same_quiet_bounce_is_a_signal_for_the_mother(self) -> None:
        """The measured difference, on one bar: ``v1``'s bounce asked for no
        volume, so the gate — not the geometry — is what changed."""
        quiet = with_last_volume(bounce_series(), D("9"))

        hers = TRENDLINE_BREAKOUT_V1.explain(
            ctx_of(quiet), TRENDLINE_BREAKOUT_V1.default_parameters
        )

        assert hers.state is EvaluationState.TRIGGERED

    def test_a_zero_volume_baseline_is_unavailable_not_a_low_rvol(self) -> None:
        """A median of zero has no ratio. Reporting it as ``rvol_low`` would be
        a false condition observed, which is the one thing a reason may not be."""
        muted = [candle.model_copy(update={"volume": D(0)}) for candle in bounce_series()]

        result = explain(muted)

        assert (result.state, result.reason) == (
            EvaluationState.UNAVAILABLE,
            "rvol_unavailable",
        )


# ------------------------------------------------ 4. it cannot evaluate / refuses


class TestItDoesNotDecide:
    def test_an_ineligible_market_is_not_a_false_condition(self) -> None:
        evaluation = TRENDLINE_BOUNCE_V1.explain(ctx_of(bounce_series(), eligible=False), PARAMS)

        assert (evaluation.state, evaluation.reason) == (
            EvaluationState.INELIGIBLE,
            "ineligible",
        )

    def test_a_short_history_is_warmup(self) -> None:
        short = bounce_series(bars=20)

        result = explain(short, ORIGIN + timedelta(minutes=BAR_MINUTES * 20))

        assert result.state is EvaluationState.UNAVAILABLE
        assert result.reason == "warmup"

    def test_a_tape_without_geometry_has_no_line(self) -> None:
        candles = series([flat(D("100"), D("1"), D("10"))] * 120, timeframe=Timeframe.M15)

        result = explain(candles, ORIGIN + timedelta(minutes=BAR_MINUTES * 120))

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "no_line")

    def test_atr_out_of_range_below_the_cost_floor(self) -> None:
        """0.75 ATR of edge is worth nothing if the toll eats it: the floor is
        the same 0.005 the mother froze (KB-0008)."""
        result = explain(bounce_series(), atr_pct_min=D("0.02"))

        assert (result.state, result.reason) == (
            EvaluationState.NOT_TRIGGERED,
            "atr_out_of_range",
        )

    def test_line_weak_when_the_line_has_not_earned_the_signal(self) -> None:
        result = explain(bounce_series(), min_touches_signal=15)

        assert (result.state, result.reason) == (EvaluationState.NOT_TRIGGERED, "line_weak")

    def test_risk_too_wide_is_still_a_refusal_and_not_a_wider_stop(self) -> None:
        result = explain(bounce_series(), max_risk_atr=D("1.5"))

        assert (result.state, result.reason) == (EvaluationState.REJECTED, "risk_too_wide")
        assert result.detail["risk"] == "40"

    def test_there_is_no_invalidation_guard_left_to_refuse_anything(self) -> None:
        """``geometry_invalidation`` was ``v1``'s third guard. It cannot appear
        here, on any bar, because the level it protected is not read."""
        reasons = {
            explain(bounce_series()).reason,
            explain(breakout_series(), CUT).reason,
            explain(with_last_volume(bounce_series(), D("9"))).reason,
        }

        assert "geometry_invalidation" not in reasons


# ------------------------------------------------------- 5. no look-ahead


ABSURD = BarSpec(D("1000"), D("9999"), D("0.01"), D("5000"), D("999999"))


class TestNoLookAhead:
    def test_bars_after_the_cut_cannot_change_the_decision(self) -> None:
        clean = bounce_series()
        baseline = TRENDLINE_BOUNCE_V1.evaluate(ctx_of(clean), PARAMS)

        for pollution in (
            explode(ABSURD, BOUNCE_CUT, BAR_MINUTES),
            explode(BarSpec(D("1000"), D("1001"), D("1"), D("2"), D("7")), BOUNCE_CUT, 15),
        ):
            assert baseline is not None
            assert TRENDLINE_BOUNCE_V1.evaluate(ctx_of([*clean, *pollution]), PARAMS) == baseline

    @pytest.mark.parametrize(
        ("high", "low", "close", "volume"),
        [
            (D("9999"), D("0.01"), D("5000"), D("999999")),
            (D("1073"), D("1072"), D("1072.5"), D("0")),
            (D("1"), D("0.5"), D("0.75"), D("1")),
        ],
    )
    def test_the_candle_still_forming_never_moves_the_decision(
        self, high: Decimal, low: Decimal, close: Decimal, volume: Decimal
    ) -> None:
        """The rule of PIPELINE.md §2: a bar-feature reads only ``is_final``
        candles. The forming minute is the one that opens the bar *after* the
        cut, and whatever it prints — including a volume that would move the
        median and a price that would move the line — the decision is the same,
        envelope bytes included."""
        clean = bounce_series()
        # ``open`` is the previous close clamped into the forming bar: a candle
        # whose open sits outside its own range is not a candle, and the clamp
        # changes nothing under test (nothing here reads ``open``).
        opening = min(max(D("1072.5"), low), high)
        forming = minute(BOUNCE_CUT, opening, high, low, close, volume, is_final=False)

        baseline = TRENDLINE_BOUNCE_V1.evaluate(ctx_of(clean), PARAMS)
        polluted = TRENDLINE_BOUNCE_V1.evaluate(ctx_of([*clean, forming]), PARAMS)

        assert baseline is not None and polluted is not None
        assert polluted == baseline
        assert canonical_json(polluted.supporting_features.to_jsonable()) == canonical_json(
            baseline.supporting_features.to_jsonable()
        )

    def test_a_non_final_candle_inside_the_window_is_a_gap_not_an_input(self) -> None:
        """The other direction of the same rule: flipping a minute the window
        needs to ``is_final = false`` must not be silently read — the version
        reports the hole instead of deciding on a bar it cannot see."""
        clean = bounce_series()
        holed = list(clean)
        holed[-BAR_MINUTES] = holed[-BAR_MINUTES].model_copy(update={"is_final": False})

        result = TRENDLINE_BOUNCE_V1.explain(ctx_of(holed), PARAMS)

        assert result.state is EvaluationState.UNAVAILABLE
        assert result.decision is None

    def test_bootstrap_equals_continuous_execution(self) -> None:
        """One long history evaluated once, against the same tape grown bar by
        bar: the rolling ATR window is what makes these equal."""
        candles = bounce_series()
        bootstrap = TRENDLINE_BOUNCE_V1.evaluate(ctx_of(candles), PARAMS)

        grown: list[NormalizedCandle] = []
        decisions: list[Decision | None] = []
        for start in range(0, len(candles), BAR_MINUTES):
            grown.extend(candles[start : start + BAR_MINUTES])
            bar_close = ORIGIN + timedelta(minutes=len(grown))
            decisions.append(TRENDLINE_BOUNCE_V1.evaluate(ctx_of(list(grown), bar_close), PARAMS))

        assert bootstrap is not None
        assert decisions[-1] == bootstrap

    def test_the_decision_does_not_depend_on_how_much_history_is_kept(self) -> None:
        full = bounce_series()
        trimmed = full[-98 * BAR_MINUTES :]

        assert TRENDLINE_BOUNCE_V1.evaluate(
            ctx_of(trimmed), PARAMS
        ) == TRENDLINE_BOUNCE_V1.evaluate(ctx_of(full), PARAMS)


# ------------------------------------------------------------- 6. purity


class TestPurity:
    def test_the_same_context_twice_gives_the_same_decision(self) -> None:
        ctx = ctx_of(bounce_series())

        first = TRENDLINE_BOUNCE_V1.evaluate(ctx, PARAMS)
        second = TRENDLINE_BOUNCE_V1.evaluate(ctx, PARAMS)

        assert first is not None and second is not None
        assert first == second
        assert canonical_json(first.supporting_features.to_jsonable()) == canonical_json(
            second.supporting_features.to_jsonable()
        )

    @pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP])
    def test_the_numbers_do_not_depend_on_the_ambient_decimal_context(self, rounding: str) -> None:
        ctx = ctx_of(bounce_series())
        baseline = TRENDLINE_BOUNCE_V1.evaluate(ctx, PARAMS)

        with localcontext() as ambient:
            ambient.prec = 6
            ambient.rounding = rounding
            narrowed = TRENDLINE_BOUNCE_V1.evaluate(ctx, PARAMS)

        assert baseline is not None
        assert narrowed == baseline

    def test_the_module_reads_no_clock_and_no_database(self) -> None:
        from pathlib import Path

        import hunter_core.strategies as package

        directory = Path(package.__file__).parent
        forbidden = ("datetime.now", "time.time", "import redis", "sqlalchemy", "utcnow")
        source = (directory / "trendline_bounce_v1.py").read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source, f"trendline_bounce_v1.py mentions {needle}"


# ------------------------------------------------------ 7. the freeze


class TestTheFreeze:
    @pytest.mark.parametrize("module", sorted(FROZEN_DIGESTS))
    def test_the_six_live_digests_did_not_move(self, module: str) -> None:
        """Adding this module must not re-freeze a row already activated on the
        VPS — ``trendline_breakout_v1`` (…7b83a1ff…) included, since the two
        versions share five geometry siblings."""
        from hunter_strategy_worker.code_ref import version_code_ref

        expected = f"hunter_core.strategies.{module}@sha256:{FROZEN_DIGESTS[module]}"
        assert version_code_ref(module) == expected

    def test_the_closure_is_the_geometry_and_not_the_other_experiment(self) -> None:
        from hunter_strategy_worker.code_ref import module_closure

        closure = module_closure("trendline_bounce_v1")

        assert closure == (
            "aggregate",
            "base",
            "canonical",
            "envelope",
            "indicators",
            "numeric",
            "schema",
            "tl_events",
            "tl_lines",
            "tl_pivots",
            "tl_scan",
            "tl_setup",
            "trendline_bounce_v1",
        )
        assert "trendline_breakout_v1" not in closure
        assert "constraints" not in closure

    def test_it_is_registered_under_the_key_the_catalogue_will_resolve(self) -> None:
        from hunter_core.strategies.registry import DEFAULT_REGISTRY

        assert DEFAULT_REGISTRY.get("trendline_bounce_v1", "v1") is TRENDLINE_BOUNCE_V1


# --------------------------------------------------------- 8. constraints


class TestRanges:
    def test_the_frozen_contract_passes_its_own_check(self) -> None:
        assert check_ranges(TRENDLINE_BOUNCE_V1, dict(PARAMS), dict(PARAMS)) == []

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"rvol_min": "-1"}, "rvol_min"),
            ({"min_touches": "1"}, "min_touches"),
            ({"stop_atr_max": "3.0", "max_risk_atr": "2.0"}, "stop_atr_max"),
            ({"atr_pct_min": "0.06"}, "atr_pct_min"),
            ({"base_confidence": "42"}, "base_confidence"),
            ({"horizon_s": "0"}, "horizon_s"),
        ],
    )
    def test_a_variant_outside_the_declared_range_is_refused(
        self, override: dict[str, str], fragment: str
    ) -> None:
        variant = {**{k: str(v) for k, v in PARAMS.items()}, **override}

        problems = check_ranges(TRENDLINE_BOUNCE_V1, dict(PARAMS), variant)

        assert any(fragment in problem for problem in problems), problems

    def test_turning_the_volume_gate_off_is_a_legitimate_variant(self) -> None:
        """``rvol_min = 0`` recovers the mother's bounce (no volume asked). It is
        the counterfactual EXP-0022 pre-registers, so the table must allow it."""
        variant = {**{k: str(v) for k, v in PARAMS.items()}, "rvol_min": "0"}

        assert check_ranges(TRENDLINE_BOUNCE_V1, dict(PARAMS), variant) == []
