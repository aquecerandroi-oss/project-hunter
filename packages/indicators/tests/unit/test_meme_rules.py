"""T4.5 — the entry gate and the exit rules, every yes and every no named.

The gate is the place where "unknown" must never read as "fine": a feature the
free sources cannot produce yet (creator net seller, last-minute curve volume)
refuses **by name**, and the name says which input was missing. That is the
MUST-FIX 1 of Astra's T4.0 review turned into code.

The exit side is a precedence, declared once and tested as a table: rug signal,
creator dump, the curve's own events (migration, completion), the loss floor,
the target multiple, the trailing from the peak mark, the time stop. Two rules
can be true at the same instant; the reason reported is always the one higher in
this list, so two runs of EXP-M1 can be compared.

The gate and the rule set below are **fixtures of this test**, chosen for round
numbers — not the frozen parameters of EXP-M1, which live in the experiment page
and come from the ``meme_paper_v0`` profile of ``docs/RISK_ENGINE_MEME.md`` §3.1.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_indicators.meme.rules import (
    EntryFeatures,
    EntryGate,
    ExitRules,
    ExitState,
    evaluate_entry,
    evaluate_exit,
    hit_max_loss,
    hit_target,
    hit_time_stop,
    hit_trailing,
    participation_pct,
)

GATE = EntryGate(
    key="teste_porta",
    version=1,
    description="Test fixture: age window, progress window, creator and participation caps.",
    min_age_s=60,
    max_age_s=900,
    min_progress_pct=Decimal(1),
    max_progress_pct=Decimal(20),
    max_participation_pct=Decimal(5),
)
FEATURES = EntryFeatures(
    mint="5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38",
    age_s=300,
    progress_pct=Decimal(8),
    creator_net_seller=False,
    curve_volume_1m_sol=Decimal(10),
    intended_size_sol=Decimal("0.4"),
)
RULES = ExitRules(
    key="teste_saida",
    version=1,
    description="Test fixture: 3x target, 40 % trailing from the peak mark, 30 min time stop.",
    target_multiple=Decimal(3),
    trailing_drawdown_pct=Decimal(40),
    time_stop_s=1800,
    max_loss_pct=Decimal(50),
)
OPEN = ExitState(
    mark_sol=Decimal("1.6"),
    cost_basis_sol=Decimal(1),
    peak_mark_sol=Decimal("2.5"),
    held_s=100,
    rug_suspected=False,
    creator_net_seller=False,
)


def test_a_registered_gate_and_rule_set_carry_their_own_parameters() -> None:
    assert GATE.version >= 1
    assert GATE.as_parameters() == {
        "min_age_s": "60",
        "max_age_s": "900",
        "min_progress_pct": "1",
        "max_progress_pct": "20",
        "max_participation_pct": "5",
        "require_creator_not_net_seller": "True",
    }
    assert RULES.as_parameters() == {
        "target_multiple": "3",
        "trailing_drawdown_pct": "40",
        "time_stop_s": "1800",
        "max_loss_pct": "50",
        "exit_on_curve_complete": "True",
        "exit_on_migration": "True",
        "exit_on_creator_dump": "True",
    }
    assert GATE.inputs and RULES.inputs


@pytest.mark.parametrize("version", [0, -1])
def test_a_rule_set_version_starts_at_one(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        replace(RULES, version=version)
    with pytest.raises(ValueError, match="version"):
        replace(GATE, version=version)


def test_the_gate_lets_the_declared_window_through() -> None:
    decision = evaluate_entry(FEATURES, GATE)
    assert decision.allowed
    assert decision.refusals == ()


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"age_s": None}, ("age_unknown",)),
        ({"age_s": 30}, ("age_below_min",)),
        ({"age_s": 1000}, ("age_above_max",)),
        ({"progress_pct": None}, ("progress_unknown",)),
        ({"progress_pct": Decimal("0.5")}, ("progress_below_min",)),
        ({"progress_pct": Decimal(30)}, ("progress_above_max",)),
        ({"creator_net_seller": None}, ("creator_net_seller_unknown",)),
        ({"creator_net_seller": True}, ("creator_is_net_seller",)),
        ({"curve_volume_1m_sol": None}, ("curve_volume_1m_unknown",)),
        ({"intended_size_sol": Decimal("0.6")}, ("participation_above_cap",)),
        ({"intended_size_sol": Decimal(0)}, ("size_not_positive",)),
        ({"curve_complete": True}, ("curve_complete",)),
        ({"migrated": True}, ("already_migrated",)),
        ({"age_s": None, "progress_pct": None}, ("age_unknown", "progress_unknown")),
    ],
)
def test_every_refusal_of_the_gate_has_a_name(
    patch: dict[str, object], expected: tuple[str, ...]
) -> None:
    decision = evaluate_entry(replace(FEATURES, **patch), GATE)
    assert not decision.allowed
    assert decision.refusals == expected


def test_the_creator_check_is_on_by_default_and_off_means_not_a_criterion() -> None:
    """The default refuses a blind read; a version with it off declares that, loudly.

    An arm that wants to falsify the creator filter has to be a **new version**
    of the gate (2 here), and turning the flag off removes the feature from the
    decision entirely — it never turns "unknown" into "the dev did not sell".
    """
    unknown_creator = replace(FEATURES, creator_net_seller=None)
    assert evaluate_entry(unknown_creator, GATE).refusals == ("creator_net_seller_unknown",)
    assert evaluate_entry(replace(FEATURES, creator_net_seller=True), GATE).refusals == (
        "creator_is_net_seller",
    )
    permissive = replace(GATE, version=2, require_creator_not_net_seller=False)
    assert evaluate_entry(unknown_creator, permissive).allowed
    assert evaluate_entry(replace(FEATURES, creator_net_seller=True), permissive).allowed


def test_a_minute_without_curve_volume_is_unmeasurable_not_zero_participation() -> None:
    zero = replace(FEATURES, curve_volume_1m_sol=Decimal(0))
    assert evaluate_entry(zero, GATE).refusals == ("curve_volume_1m_zero",)


def test_participation_is_our_size_over_the_last_minute_of_curve_volume() -> None:
    assert participation_pct(Decimal("0.4"), Decimal(10)) == Decimal(4)
    assert participation_pct(Decimal("0.4"), None) is None
    assert participation_pct(Decimal("0.4"), Decimal(0)) is None


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"rug_suspected": True}, "rug_signal"),
        ({"creator_net_seller": True}, "creator_dump"),
        ({"migrated": True}, "migrated"),
        ({"curve_complete": True}, "curve_complete"),
        ({"mark_sol": Decimal("0.5")}, "max_loss"),
        ({"mark_sol": Decimal(3), "peak_mark_sol": Decimal(3)}, "target_multiple"),
        ({"mark_sol": Decimal("1.2")}, "trailing_from_peak"),
        ({"held_s": 1900}, "time_stop"),
        ({"held_s": 1800}, "time_stop"),
    ],
)
def test_every_exit_has_a_name(patch: dict[str, object], reason: str) -> None:
    decision = evaluate_exit(replace(OPEN, **patch), RULES)
    assert decision.should_exit
    assert decision.reason == reason


def test_an_open_position_inside_every_rule_is_not_an_exit() -> None:
    decision = evaluate_exit(OPEN, RULES)
    assert not decision.should_exit
    assert decision.reason is None
    assert decision.unknown == ()


def test_the_declared_precedence_decides_when_two_rules_fire_together() -> None:
    both = replace(OPEN, mark_sol=Decimal(3), peak_mark_sol=Decimal(3), rug_suspected=True)
    assert evaluate_exit(both, RULES).reason == "rug_signal"
    creator_and_target = replace(both, rug_suspected=False, creator_net_seller=True)
    assert evaluate_exit(creator_and_target, RULES).reason == "creator_dump"
    event_and_target = replace(both, rug_suspected=False, curve_complete=True)
    assert evaluate_exit(event_and_target, RULES).reason == "curve_complete"
    loss_and_time = replace(OPEN, mark_sol=Decimal("0.4"), held_s=5000)
    assert evaluate_exit(loss_and_time, RULES).reason == "max_loss"


def test_an_unknown_rug_or_creator_signal_is_named_and_is_not_an_exit() -> None:
    """Neither detector exists yet (T4.2 leaves both inputs null with a reason)."""
    decision = evaluate_exit(replace(OPEN, rug_suspected=None), RULES)
    assert not decision.should_exit
    assert decision.unknown == ("rug_signal_unknown",)
    blind = evaluate_exit(replace(OPEN, rug_suspected=None, creator_net_seller=None), RULES)
    assert not blind.should_exit
    assert blind.unknown == ("rug_signal_unknown", "creator_dump_unknown")
    forced = replace(OPEN, rug_suspected=None, held_s=1900)
    assert evaluate_exit(forced, RULES).reason == "time_stop"
    assert evaluate_exit(forced, RULES).unknown == ("rug_signal_unknown",)


def test_the_creator_dump_exit_can_be_declared_off_and_then_is_not_even_unknown() -> None:
    quiet = replace(RULES, version=2, exit_on_creator_dump=False)
    blind = replace(OPEN, creator_net_seller=None)
    assert evaluate_exit(blind, quiet).unknown == ()
    assert not evaluate_exit(replace(OPEN, creator_net_seller=True), quiet).should_exit


def test_the_curve_events_can_be_declared_off_for_a_contrast_arm() -> None:
    quiet = replace(RULES, version=2, exit_on_curve_complete=False, exit_on_migration=False)
    assert not evaluate_exit(replace(OPEN, curve_complete=True), quiet).should_exit
    assert not evaluate_exit(replace(OPEN, migrated=True), quiet).should_exit


def test_the_predicates_are_pure_functions_anyone_can_check_alone() -> None:
    assert hit_target(replace(OPEN, mark_sol=Decimal(3)), RULES)
    assert not hit_target(replace(OPEN, mark_sol=Decimal("2.99")), RULES)
    assert hit_max_loss(replace(OPEN, mark_sol=Decimal("0.5")), RULES)
    assert not hit_max_loss(replace(OPEN, mark_sol=Decimal("0.51")), RULES)
    assert hit_trailing(replace(OPEN, mark_sol=Decimal("1.5")), RULES)
    assert not hit_trailing(replace(OPEN, mark_sol=Decimal("1.51")), RULES)
    assert hit_time_stop(replace(OPEN, held_s=1800), RULES)
    assert not hit_time_stop(replace(OPEN, held_s=1799), RULES)


def test_an_impossible_rule_set_refuses_to_exist() -> None:
    with pytest.raises(ValueError, match="target_multiple"):
        replace(RULES, target_multiple=Decimal(1))
    with pytest.raises(ValueError, match="trailing_drawdown_pct"):
        replace(RULES, trailing_drawdown_pct=Decimal(100))
    with pytest.raises(ValueError, match="max_loss_pct"):
        replace(RULES, max_loss_pct=Decimal(0))
    with pytest.raises(ValueError, match="time_stop_s"):
        replace(RULES, time_stop_s=0)
    with pytest.raises(ValueError, match="age"):
        replace(GATE, min_age_s=1000)
    with pytest.raises(ValueError, match="progress"):
        replace(GATE, min_progress_pct=Decimal(50))
