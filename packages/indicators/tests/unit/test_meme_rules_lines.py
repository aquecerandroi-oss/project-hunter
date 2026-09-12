"""T4.10 — the EXP-M2/EXP-M3 criteria of the entry gate and the "line broken"
exit, every yes and every no named.

Two properties matter more than the individual thresholds: a gate that does not
ask a question does not refuse over it (EXP-M1's frozen gate reads the new
columns and ignores them), and a gate that asks and finds the input missing
refuses **by the input's own reason** (``line_too_few_points``,
``hype_no_tape_no_board``), so the heartbeat can tell blindness from a no.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_indicators.meme import exits, rules
from hunter_indicators.meme.rules import (
    EntryFeatures,
    EntryGate,
    ExitRules,
    ExitState,
    evaluate_entry,
    evaluate_exit,
)

pytestmark = pytest.mark.unit

BASE_GATE = EntryGate(
    key="teste_porta",
    version=1,
    description="fixture",
    min_age_s=60,
    max_age_s=900,
    min_progress_pct=Decimal(1),
    max_progress_pct=Decimal(20),
    max_participation_pct=Decimal(5),
)
LINE_GATE = replace(
    BASE_GATE,
    key="teste_linha",
    require_higher_lows=True,
    require_breakout_15m=True,
    min_distance_to_support_pct=Decimal(0),
    max_distance_to_support_pct=Decimal("0.25"),
)
HYPE_GATE = replace(
    BASE_GATE,
    key="teste_hype",
    require_progress=False,
    min_hype_score=Decimal("0.6"),
    max_dev_share=Decimal("0.10"),
    dev_share_unknown_allowed=True,
    max_snipers=2,
)
OK = EntryFeatures(
    mint="5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38",
    age_s=300,
    progress_pct=Decimal(8),
    creator_net_seller=False,
    curve_volume_1m_sol=Decimal(10),
    intended_size_sol=Decimal("0.4"),
    higher_lows=True,
    breakout_15m=True,
    distance_to_support_pct=Decimal("0.1"),
    hype_score=Decimal("0.7"),
    dev_share=Decimal("0.05"),
    snipers=1,
)


def _refusals(features: EntryFeatures, gate: EntryGate) -> tuple[str, ...]:
    return evaluate_entry(features, gate).refusals


# ---- a gate that does not ask does not refuse ---------------------------------------------


def test_a_gate_without_the_new_criteria_ignores_the_new_columns() -> None:
    blind = replace(
        OK,
        higher_lows=None,
        breakout_15m=None,
        distance_to_support_pct=None,
        line_reason="too_few_points",
        hype_score=None,
        hype_reason="no_tape_no_board",
        dev_share=None,
        snipers=None,
    )
    assert evaluate_entry(blind, BASE_GATE).allowed
    assert "require_higher_lows" not in BASE_GATE.as_parameters(), "not asked, not listed"
    listed = LINE_GATE.as_parameters()
    assert (
        listed["require_higher_lows"] == "True" and listed["max_distance_to_support_pct"] == "0.25"
    )
    assert HYPE_GATE.as_parameters()["require_progress"] == "False"


def test_the_line_gate_accepts_a_confirmed_line() -> None:
    assert evaluate_entry(OK, LINE_GATE).allowed


# ---- the line criteria (EXP-M2) -----------------------------------------------------------


def test_a_missing_line_refuses_by_the_lines_own_reason() -> None:
    blind = replace(OK, higher_lows=None, distance_to_support_pct=None, line_reason="flat")
    assert _refusals(blind, LINE_GATE) == ("line_flat",)
    unnamed = replace(blind, line_reason=None)
    assert _refusals(unnamed, LINE_GATE) == ("line_unknown",)


def test_lower_lows_no_breakout_and_the_band_each_have_a_name() -> None:
    assert _refusals(replace(OK, higher_lows=False), LINE_GATE) == ("no_higher_lows",)
    assert _refusals(replace(OK, breakout_15m=False), LINE_GATE) == ("no_breakout",)
    assert _refusals(replace(OK, breakout_15m=None), LINE_GATE) == ("breakout_unknown",)
    below = replace(OK, distance_to_support_pct=Decimal("-0.02"))
    assert _refusals(below, LINE_GATE) == ("distance_below_min",)
    above = replace(OK, distance_to_support_pct=Decimal("0.30"))
    assert _refusals(above, LINE_GATE) == ("distance_above_max",)
    assert _refusals(replace(OK, distance_to_support_pct=Decimal("0.25")), LINE_GATE) == ()


def test_the_band_may_be_one_sided() -> None:
    only_max = replace(BASE_GATE, max_distance_to_support_pct=Decimal("0.25"))
    assert _refusals(replace(OK, distance_to_support_pct=Decimal("-1")), only_max) == ()
    with pytest.raises(ValueError, match="min <= max"):
        replace(
            BASE_GATE,
            min_distance_to_support_pct=Decimal(1),
            max_distance_to_support_pct=Decimal(0),
        )


# ---- the hype criteria (EXP-M3) -----------------------------------------------------------


def test_the_hype_gate_accepts_a_hyped_young_coin_without_progress() -> None:
    young = replace(OK, age_s=90, progress_pct=None)
    assert evaluate_entry(young, HYPE_GATE).allowed, "progress is not a criterion here"
    assert "progress_unknown" in _refusals(young, BASE_GATE)


def test_hype_refusals_are_named_including_the_missing_sources() -> None:
    assert _refusals(replace(OK, hype_score=Decimal("0.59")), HYPE_GATE) == ("hype_below_min",)
    blind = replace(OK, hype_score=None, hype_reason="no_tape_no_board")
    assert _refusals(blind, HYPE_GATE) == ("hype_no_tape_no_board",)
    assert _refusals(replace(OK, hype_score=None), HYPE_GATE) == ("hype_unknown",)


def test_dev_share_may_be_unknown_only_with_a_reason_and_only_when_allowed() -> None:
    with_reason = replace(OK, dev_share=None, dev_share_reason="no_holders_reader")
    assert _refusals(with_reason, HYPE_GATE) == ()
    no_reason = replace(OK, dev_share=None, dev_share_reason=None)
    assert _refusals(no_reason, HYPE_GATE) == ("dev_share_unknown",)
    strict = replace(HYPE_GATE, dev_share_unknown_allowed=False)
    assert _refusals(with_reason, strict) == ("dev_share_unknown",)
    assert _refusals(replace(OK, dev_share=Decimal("0.11")), HYPE_GATE) == ("dev_share_above_max",)


def test_snipers_refuse_unknown_and_above_the_ceiling() -> None:
    assert _refusals(replace(OK, snipers=None), HYPE_GATE) == ("snipers_unknown",)
    assert _refusals(replace(OK, snipers=3), HYPE_GATE) == ("snipers_above_max",)
    assert _refusals(replace(OK, snipers=2), HYPE_GATE) == ()


def test_thresholds_outside_their_domain_are_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="min_hype_score"):
        replace(BASE_GATE, min_hype_score=Decimal("1.5"))
    with pytest.raises(ValueError, match="max_dev_share"):
        replace(BASE_GATE, max_dev_share=Decimal(-1))
    with pytest.raises(ValueError, match="max_snipers"):
        replace(BASE_GATE, max_snipers=-1)


# ---- the "line broken" exit ---------------------------------------------------------------

RULES = ExitRules(
    key="teste_saida",
    version=1,
    description="fixture",
    target_multiple=Decimal(2),
    trailing_drawdown_pct=Decimal(30),
    time_stop_s=900,
    max_loss_pct=Decimal(50),
    exit_on_line_break=True,
    line_break_snapshots=2,
)
HELD = ExitState(
    mark_sol=Decimal("0.9"),
    cost_basis_sol=Decimal(1),
    peak_mark_sol=Decimal(1),
    held_s=60,
    rug_suspected=False,
    creator_net_seller=False,
    below_support_streak=0,
)


def test_two_closes_below_the_line_sell_and_one_does_not() -> None:
    assert not evaluate_exit(replace(HELD, below_support_streak=1), RULES).should_exit
    decision = evaluate_exit(replace(HELD, below_support_streak=2), RULES)
    assert decision.should_exit and decision.reason == "line_broken"
    assert decision.unknown == ()


def test_a_rule_set_that_does_not_watch_the_line_never_sells_on_it() -> None:
    off = replace(RULES, exit_on_line_break=False)
    decision = evaluate_exit(replace(HELD, below_support_streak=5), off)
    assert not decision.should_exit and "support_line_unknown" not in decision.unknown


def test_a_watched_line_that_does_not_exist_is_named_unknown() -> None:
    decision = evaluate_exit(replace(HELD, below_support_streak=None), RULES)
    assert not decision.should_exit and decision.unknown == ("support_line_unknown",)


def test_precedence_max_loss_beats_the_line_and_the_line_beats_the_target() -> None:
    floor = replace(HELD, mark_sol=Decimal("0.4"), below_support_streak=2)
    assert evaluate_exit(floor, RULES).reason == "max_loss"
    both = replace(
        HELD, mark_sol=Decimal("2.5"), peak_mark_sol=Decimal("2.5"), below_support_streak=2
    )
    assert evaluate_exit(both, RULES).reason == "line_broken"


def test_line_break_snapshots_must_be_at_least_one() -> None:
    with pytest.raises(ValueError, match="line_break_snapshots"):
        replace(RULES, line_break_snapshots=0)
    assert RULES.as_parameters()["line_break_snapshots"] == "2"


def test_rules_re_exports_the_exit_side_unchanged() -> None:
    assert rules.evaluate_exit is exits.evaluate_exit
    assert rules.ExitRules is exits.ExitRules and rules.ExitState is exits.ExitState
    assert rules.hit_line_break is exits.hit_line_break
