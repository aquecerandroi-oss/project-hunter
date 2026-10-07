"""H-031b (EXP-M27) — ``exit_on_creator_dump`` on every bet, and honoured by the exit.

Until now the switch existed only on ``ExitRules`` (default ``True``): no bet
recorded it (the advogado de Jesus found it in 0 of 1 680 bets of the R88), so
"this bet sold on the creator's dump because its set said so" could only be
inferred from the code of the day. The twin ``absorb_semdump_v0/1`` is
``absorb_v0/2`` plus ``"exit_on_creator_dump": false``; its bets must say so,
and the exit must not fire ``creator_dump`` on either path — the photo's
``creator_net_seller`` (``paper_engine.decide_exit_at`` → ``evaluate_exit``)
and the chain watch's ``creator_sold_seen_at`` (``lab_bets`` gates it on
``params.exit_rules().exit_on_creator_dump``). The rule set → bet link
(``RuleSetSpec`` → ``effective_params``) is ``test_rule_set_creator_dump.py``.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.exits import ExitState, evaluate_exit
from hunter_meme_worker.lab_params import EffectiveParams

pytestmark = pytest.mark.unit

ORIGINAL = EffectiveParams(
    size_sol=Decimal("0.07"),
    target_x=Decimal("1.15"),
    trailing_pct=Decimal(10),
    max_hold_s=300,
    max_loss_pct=Decimal(50),
)
"""``absorb_v0/2``'s exits (``ddl/meme_gate_absorb_arm.ABSORB_BASE``) minus the line."""
TWIN = replace(ORIGINAL, exit_on_creator_dump=False)


def _creator_sold(**overrides: Any) -> ExitState:
    """A bet flat on its cost, no other exit due, the creator a net seller."""
    base: dict[str, Any] = {
        "mark_sol": Decimal("0.07"),
        "cost_basis_sol": Decimal("0.07"),
        "peak_mark_sol": Decimal("0.07"),
        "held_s": 10,
        "rug_suspected": False,
        "creator_net_seller": True,
    }
    return ExitState(**{**base, **overrides})


def test_the_default_still_sells_on_the_creator_dump() -> None:
    assert ORIGINAL.exit_on_creator_dump is True
    rules = ORIGINAL.exit_rules()
    assert rules.exit_on_creator_dump is True
    assert evaluate_exit(_creator_sold(), rules).reason == "creator_dump"


def test_the_twin_never_sells_on_the_creator_dump_and_never_waits_for_it() -> None:
    rules = TWIN.exit_rules()
    assert rules.exit_on_creator_dump is False
    decision = evaluate_exit(_creator_sold(), rules)
    assert (decision.should_exit, decision.reason) == (False, None)
    unknown = evaluate_exit(_creator_sold(creator_net_seller=None), rules).unknown
    assert "creator_dump_unknown" not in unknown


def test_the_twin_still_takes_the_next_exit_that_would_fire() -> None:
    """What H-031b measures: ``creator_dump`` against the next exit, not "hold"."""
    rules = TWIN.exit_rules()
    crashed = _creator_sold(mark_sol=Decimal("0.028"))  # -60 % against max_loss 50 %
    assert evaluate_exit(crashed, rules).reason == "max_loss"
    off_peak = _creator_sold(peak_mark_sol=Decimal("0.075"), mark_sol=Decimal("0.0675"))
    assert evaluate_exit(off_peak, rules).reason == "trailing_from_peak"
    assert evaluate_exit(_creator_sold(held_s=300), rules).reason == "time_stop"


@pytest.mark.parametrize(("params", "expected"), [(ORIGINAL, True), (TWIN, False)])
def test_every_bet_records_the_switch_it_ran_on(params: EffectiveParams, expected: bool) -> None:
    written = params.as_json()
    assert written["exit_on_creator_dump"] is expected
    assert EffectiveParams.from_json(written) == params


def test_a_bet_written_before_the_switch_was_recorded_reads_the_only_value_it_ran_on() -> None:
    """Before H-031b no code path could set it: every such bet ran on ``True``."""
    legacy = ORIGINAL.as_json()
    del legacy["exit_on_creator_dump"]
    assert EffectiveParams.from_json(legacy).exit_on_creator_dump is True


@pytest.mark.parametrize("bad", ["false", "true", 0, 1, "0", None])
def test_a_recorded_switch_is_a_bare_json_boolean(bad: Any) -> None:
    """``bool("false")`` is ``True`` and a ``null`` would mean "the default": a
    present key that is not a boolean is refused, never read."""
    with pytest.raises(TypeError):
        EffectiveParams.from_json({**ORIGINAL.as_json(), "exit_on_creator_dump": bad})
