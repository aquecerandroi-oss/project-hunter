"""T4.11 — the moonshot exits: the trailing armed only after N×, the ``dead``
rule, migration as a parameter, and the frozen sets reading as before.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_indicators.meme.rules import (
    ExitRules,
    ExitState,
    evaluate_exit,
    hit_dead,
    hit_trailing,
)

FROZEN = ExitRules(
    key="alvo_2x_trailing_30_tempo_15m",
    version=1,
    description="EXP-M1's exits, as frozen.",
    target_multiple=Decimal(2),
    trailing_drawdown_pct=Decimal(30),
    time_stop_s=900,
    max_loss_pct=Decimal(50),
)
MOONSHOT = ExitRules(
    key="alvo_10x_trailing_50_apos_3x_tempo_2h",
    version=1,
    description="EXP-M4 arm 1: 10x, trailing 50 % armed at 3x, 2 h, hold through migration, dead.",
    target_multiple=Decimal(10),
    trailing_drawdown_pct=Decimal(50),
    time_stop_s=7200,
    max_loss_pct=Decimal(100),
    exit_on_curve_complete=False,
    exit_on_migration=False,
    trailing_arm_multiple=Decimal(3),
    exit_on_dead=True,
    dead_stale_s=900,
    dead_mark_pct=Decimal(50),
)


def _state(mark: str, peak: str, **kw: object) -> ExitState:
    return ExitState(
        mark_sol=Decimal(mark),
        cost_basis_sol=Decimal("0.02"),
        peak_mark_sol=Decimal(peak),
        held_s=kw.pop("held_s", 100),  # type: ignore[arg-type]
        rug_suspected=False,
        creator_net_seller=False,
        **kw,  # type: ignore[arg-type]
    )


# ---- the trailing armed only after 3x ------------------------------------------------


def test_before_three_x_the_trailing_is_disarmed_and_after_it_fires() -> None:
    """Peak 2,5× and a 60 % drawdown: a moonshot rides it. Peak 3× and −50 %: sells."""
    riding = _state("0.02", "0.05")  # peak 2,5x, mark back to 1x = −60 % from the peak
    assert not hit_trailing(riding, MOONSHOT)
    assert evaluate_exit(riding, MOONSHOT).should_exit is False
    assert hit_trailing(riding, FROZEN), "the frozen set (no arm) would have sold"
    armed = _state("0.03", "0.06")  # peak exactly 3x, mark −50 %
    assert hit_trailing(armed, MOONSHOT)
    assert evaluate_exit(armed, MOONSHOT).reason == "trailing_from_peak"
    still_up = _state("0.0301", "0.06")
    assert not hit_trailing(still_up, MOONSHOT)


def test_the_arm_must_be_above_one_when_set() -> None:
    with pytest.raises(ValueError, match="trailing_arm_multiple"):
        replace(MOONSHOT, trailing_arm_multiple=Decimal(1))


# ---- the dead rule ---------------------------------------------------------------------


def test_dead_needs_both_the_silence_and_the_drawdown() -> None:
    dead = _state("0.01", "0.03", mark_stale_s=900)  # 50 % of the cost, 15 min silent
    assert hit_dead(dead, MOONSHOT)
    assert evaluate_exit(dead, MOONSHOT).reason == "dead"
    quiet_but_alive = _state("0.0101", "0.03", mark_stale_s=5000)
    assert not hit_dead(quiet_but_alive, MOONSHOT), "51 % of the cost is not dead"
    falling_but_traded = _state("0.001", "0.03", mark_stale_s=899)
    assert not hit_dead(falling_but_traded, MOONSHOT), "one second short of the silence"
    assert not hit_dead(dead, FROZEN), "a set that does not watch for it never fires it"


def test_on_the_curve_the_staleness_is_unknown_and_named_never_assumed() -> None:
    on_curve = _state("0.005", "0.03", mark_stale_s=None)
    decision = evaluate_exit(on_curve, MOONSHOT)
    assert not decision.should_exit
    assert "mark_staleness_unknown" in decision.unknown
    assert "mark_staleness_unknown" not in evaluate_exit(on_curve, FROZEN).unknown


def test_dead_outranks_the_loss_floor_and_yields_to_the_creator_dump() -> None:
    both = replace(MOONSHOT, max_loss_pct=Decimal(50))
    state = _state("0.008", "0.03", mark_stale_s=1000)
    assert evaluate_exit(state, both).reason == "dead"
    dumped = replace(state, creator_net_seller=True)
    assert evaluate_exit(dumped, both).reason == "creator_dump"


# ---- migration as a parameter ------------------------------------------------------------


def test_a_set_that_holds_through_the_migration_ignores_completion_and_migration() -> None:
    migrated = _state("0.03", "0.03", migrated=True, curve_complete=True)
    assert evaluate_exit(migrated, MOONSHOT).should_exit is False
    assert evaluate_exit(migrated, FROZEN).reason == "migrated"
    assert evaluate_exit(replace(migrated, migrated=False), FROZEN).reason == "curve_complete"


def test_the_target_and_the_time_stop_still_rule_a_moonshot() -> None:
    assert evaluate_exit(_state("0.2", "0.2"), MOONSHOT).reason == "target_multiple"
    assert evaluate_exit(_state("0.03", "0.03", held_s=7200), MOONSHOT).reason == "time_stop"
    assert evaluate_exit(_state("0.03", "0.03", held_s=7199), MOONSHOT).should_exit is False


# ---- the frozen sets read exactly as they did ---------------------------------------------


def test_the_frozen_parameters_are_byte_for_byte_what_they_were() -> None:
    assert FROZEN.as_parameters() == {
        "target_multiple": "2",
        "trailing_drawdown_pct": "30",
        "time_stop_s": "900",
        "max_loss_pct": "50",
        "exit_on_curve_complete": "True",
        "exit_on_migration": "True",
        "exit_on_creator_dump": "True",
    }
    assert MOONSHOT.as_parameters() == {
        "target_multiple": "10",
        "trailing_drawdown_pct": "50",
        "time_stop_s": "7200",
        "max_loss_pct": "100",
        "exit_on_curve_complete": "False",
        "exit_on_migration": "False",
        "exit_on_creator_dump": "True",
        "trailing_arm_multiple": "3",
        "exit_on_dead": "True",
        "dead_stale_s": "900",
        "dead_mark_pct": "50",
    }
