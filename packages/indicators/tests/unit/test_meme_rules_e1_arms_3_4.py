# pyright: reportPrivateUsage=false
"""The E1 gate's sibling arms 3 and 4 (T4.23, EXP-M5): the closing of 13/09
measured `snipers > 2` at +0,25 R (n = 17) against −0,28 R elsewhere (n = 49)
and `top10_share` in 0,1767–0,257 at +0,25 R (n = 14) against −0,25 R elsewhere
(n = 52) — both contradict the E1 pre-registration (`snipers <= 2`), so both
are registered `descartar`, measured beside the live sets. `min_snipers` and
`min_top10_share` are floors beside the existing ceilings, off by default,
each unknown input still refusing by its own name."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_indicators.meme.rules import EntryGate, evaluate_entry

from .test_meme_rules_e1_arm2 import ARM_2, _arm2
from .test_meme_rules_flow import FLOW_GATE, _features

pytestmark = pytest.mark.unit

ARM_3 = replace(ARM_2, version=3, min_snipers=3, max_snipers=10)
"""``0037``'s ``flow_v2/3`` in miniature: arm 2 with the funnel's sniper band."""

ARM_4 = replace(
    ARM_2, version=4, min_top10_share=Decimal("0.1767"), max_top10_share=Decimal("0.257")
)
"""``0037``'s ``flow_v2/4`` in miniature: arm 2 with the funnel's top-10 band."""


# ---- min_snipers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("snipers", "refusals"),
    [
        (3, ()),
        (10, ()),
        (2, ("snipers_below_min",)),
        (0, ("snipers_below_min",)),
        (11, ("snipers_above_max",)),
    ],
)
def test_the_sniper_band_is_inclusive_at_both_ends(snipers: int, refusals: tuple[str, ...]) -> None:
    row = _arm2(snipers=snipers)
    assert evaluate_entry(row, ARM_3).refusals == refusals


def test_snipers_unknown_refuses_by_name_even_with_no_ceiling() -> None:
    floor_only = replace(ARM_2, max_snipers=None, min_snipers=3)
    row = _arm2(snipers=None)
    assert evaluate_entry(row, floor_only).refusals == ("snipers_unknown",)


def test_a_gate_that_asks_neither_bound_never_refuses_on_snipers() -> None:
    neither = replace(ARM_2, max_snipers=None, min_snipers=None)
    assert "snipers_unknown" not in evaluate_entry(_arm2(snipers=None), neither).refusals


def test_a_negative_sniper_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="min_snipers"):
        EntryGate("k", 1, "d", 0, 1, Decimal(0), Decimal(1), Decimal(1), min_snipers=-1)


def test_a_sniper_floor_above_the_ceiling_is_refused() -> None:
    with pytest.raises(ValueError, match="min_snipers"):
        replace(ARM_2, min_snipers=11, max_snipers=10)


# ---- min_top10_share --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("top10_share", "refusals"),
    [
        (Decimal("0.1767"), ()),
        (Decimal("0.257"), ()),
        (Decimal("0.1766"), ("top10_below_min",)),
        (Decimal("0"), ("top10_below_min",)),
        (Decimal("0.2571"), ("top10_above_max",)),
    ],
)
def test_the_top_10_band_is_inclusive_at_both_ends(
    top10_share: Decimal, refusals: tuple[str, ...]
) -> None:
    row = _arm2(top10_share=top10_share, top10_reason=None)
    assert evaluate_entry(row, ARM_4).refusals == refusals


def test_top10_unknown_refuses_by_its_reason_even_with_no_ceiling() -> None:
    floor_only = replace(ARM_2, max_top10_share=None, min_top10_share=Decimal("0.1767"))
    row = _arm2(top10_share=None, top10_reason="no_holders_reader")
    assert evaluate_entry(row, floor_only).refusals == ("top10_no_holders_reader",)


def test_a_gate_that_asks_neither_bound_never_refuses_on_top10() -> None:
    neither = replace(ARM_2, max_top10_share=None, min_top10_share=None)
    row = _arm2(top10_share=None, top10_reason=None)
    assert "top10_unknown" not in evaluate_entry(row, neither).refusals


def test_the_top_10_floor_must_be_a_fraction() -> None:
    with pytest.raises(ValueError, match="min_top10_share"):
        replace(ARM_2, min_top10_share=Decimal("1.5"))


def test_a_top_10_floor_above_the_ceiling_is_refused() -> None:
    with pytest.raises(ValueError, match="min_top10_share"):
        replace(ARM_2, min_top10_share=Decimal("0.5"), max_top10_share=Decimal("0.3"))


# ---- the registered parameters --------------------------------------------------------------


def test_the_two_floors_are_listed_only_when_set_and_arm_2_does_not_change() -> None:
    assert ARM_3.as_parameters() == {**ARM_2.as_parameters(), "min_snipers": "3"}
    assert "min_snipers" not in ARM_2.as_parameters()
    assert ARM_4.as_parameters() == {
        **ARM_2.as_parameters(),
        "min_top10_share": "0.1767",
        "max_top10_share": "0.257",
    }
    assert "min_top10_share" not in ARM_2.as_parameters()
    assert FLOW_GATE.as_parameters() == FLOW_GATE.as_parameters(), "arm 1 untouched"


def test_the_flow_gate_never_asks_for_either_floor() -> None:
    assert FLOW_GATE.min_snipers is None
    assert FLOW_GATE.min_top10_share is None
    row = _features(snipers=0, top10_share=Decimal("0"))
    assert evaluate_entry(row, FLOW_GATE).allowed
