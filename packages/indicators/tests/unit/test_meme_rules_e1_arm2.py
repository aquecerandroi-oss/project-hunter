# pyright: reportPrivateUsage=false
"""The second arm of the E1 gate (T4.21, EXP-M5 arm 2): four criteria, every
one **off by default** so ``fluxo_e_holders/1`` reads byte for byte as it was
frozen — a floor on the holders count, "not falling" instead of "rising",
an unknown creator vouched for by a measured dev share, and the 60 s
market-cap delta as an alternative to progress rising. Every refusal keeps
its name and every unknown input still refuses by name."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.rules import EntryGate, evaluate_entry

from .test_meme_rules_flow import FLOW_GATE, _features

pytestmark = pytest.mark.unit

ARM_2 = replace(
    FLOW_GATE,
    version=2,
    max_snipers=10,
    min_holders=20,
    holders_rising_or_flat=True,
    creator_unknown_allowed_if_dev_measured=True,
    progress_or_mcap_rising=True,
)
"""``0034``'s ``flow_v2/2`` in miniature: the arm-1 gate with the four
switches the funnel of 12/09 19:1x BRT asked for."""


def _arm2(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "holders": 25,
        "holders_prev": 25,
        "holders_rising": False,
        "snipers": 8,
    }
    base.update(overrides)
    return _features(**base)


def test_the_arm_2_row_passes_arm_2_and_arm_1_refuses_it_by_three_names() -> None:
    row = _arm2(creator_net_seller=None)
    assert evaluate_entry(row, ARM_2).allowed
    assert evaluate_entry(row, FLOW_GATE).refusals == (
        "creator_net_seller_unknown",
        "snipers_above_max",
        "holders_not_rising",
    )


# ---- min_holders --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("holders", "holders_prev", "refusals"),
    [
        (20, 20, ()),
        (19, 19, ("holders_below_min",)),
        (0, 0, ("holders_below_min",)),
    ],
)
def test_the_holders_floor_is_inclusive_and_refuses_below_it(
    holders: int, holders_prev: int, refusals: tuple[str, ...]
) -> None:
    decision = evaluate_entry(_arm2(holders=holders, holders_prev=holders_prev), ARM_2)
    assert decision.refusals == refusals


def test_an_unknown_holders_count_refuses_by_its_reason_once() -> None:
    blind = _arm2(
        holders=None, holders_prev=None, holders_rising=None, holders_reason="no_holders_reader"
    )
    assert evaluate_entry(blind, ARM_2).refusals == ("holders_no_holders_reader",)
    assert evaluate_entry(_arm2(holders=None, holders_rising=None), ARM_2).refusals == (
        "holders_unknown",
    )
    floor_only = replace(ARM_2, require_holders_rising=False)
    assert evaluate_entry(blind, floor_only).refusals == ("holders_no_holders_reader",)


# ---- holders_rising_or_flat ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("holders", "holders_prev", "rising", "refusals"),
    [
        (26, 25, True, ()),
        (25, 25, False, ()),
        (24, 25, False, ("holders_falling",)),
    ],
)
def test_flat_holders_pass_and_only_a_fall_refuses_by_name(
    holders: int, holders_prev: int, rising: bool, refusals: tuple[str, ...]
) -> None:
    row = _arm2(holders=holders, holders_prev=holders_prev, holders_rising=rising)
    assert evaluate_entry(row, ARM_2).refusals == refusals
    strict = replace(ARM_2, holders_rising_or_flat=False)
    assert evaluate_entry(row, strict).refusals == (() if rising else ("holders_not_rising",))


def test_a_single_reading_is_not_flat_it_is_unknown() -> None:
    one = _arm2(
        holders=25, holders_prev=None, holders_rising=None, holders_reason="too_few_readings"
    )
    assert evaluate_entry(one, ARM_2).refusals == ("holders_too_few_readings",)
    # A caller that filled only the trend flag cannot tell flat from falling.
    trend_only = _arm2(holders=None, holders_prev=None, holders_rising=False)
    floor_off = replace(ARM_2, min_holders=None)
    assert evaluate_entry(trend_only, floor_off).refusals == ("holders_unknown",)


# ---- creator_unknown_allowed_if_dev_measured ----------------------------------------------


def test_an_unknown_creator_passes_only_when_the_dev_share_was_measured_within_the_ceiling() -> (
    None
):
    vouched = _arm2(creator_net_seller=None, dev_share=Decimal("0.10"))
    assert evaluate_entry(vouched, ARM_2).allowed, "the ceiling is inclusive"
    too_much = _arm2(creator_net_seller=None, dev_share=Decimal("0.11"))
    assert evaluate_entry(too_much, ARM_2).refusals == (
        "creator_net_seller_unknown",
        "dev_share_above_max",
    )
    unmeasured = _arm2(
        creator_net_seller=None, dev_share=None, dev_share_reason="no_holders_reader"
    )
    assert evaluate_entry(unmeasured, ARM_2).refusals == (
        "creator_net_seller_unknown",
        "dev_share_unknown",
    )


def test_a_known_net_seller_is_still_refused_and_the_switch_needs_a_ceiling() -> None:
    seller = _arm2(creator_net_seller=True, dev_share=Decimal("0.01"))
    assert evaluate_entry(seller, ARM_2).refusals == ("creator_is_net_seller",)
    no_ceiling = replace(ARM_2, max_dev_share=None)
    assert evaluate_entry(_arm2(creator_net_seller=None), no_ceiling).refusals == (
        "creator_net_seller_unknown",
    )
    assert evaluate_entry(_arm2(creator_net_seller=None), FLOW_GATE).refusals[0] == (
        "creator_net_seller_unknown"
    ), "arm 1 never asked"


# ---- progress_or_mcap_rising --------------------------------------------------------------


@pytest.mark.parametrize(
    ("progress_rising", "mcap_delta_60s", "refusals"),
    [
        (True, Decimal("-1"), ()),
        (False, Decimal("2"), ()),
        (None, Decimal("2"), ()),
        (False, Decimal("0"), ("progress_not_rising",)),
        (False, None, ("progress_not_rising",)),
        (None, Decimal("-1"), ("progress_not_rising",)),
        (None, None, ("progress_trend_unknown",)),
    ],
)
def test_progress_rising_or_the_60_s_delta_rising_passes_and_neither_refuses_by_name(
    progress_rising: bool | None, mcap_delta_60s: Decimal | None, refusals: tuple[str, ...]
) -> None:
    row = _arm2(progress_rising=progress_rising, mcap_delta_60s=mcap_delta_60s)
    assert evaluate_entry(row, ARM_2).refusals == refusals


def test_without_the_switch_the_delta_is_not_an_alternative() -> None:
    row = _arm2(progress_rising=False, mcap_delta_60s=Decimal("2"))
    strict = replace(ARM_2, progress_or_mcap_rising=False)
    assert evaluate_entry(row, strict).refusals == ("progress_not_rising",)
    assert evaluate_entry(
        _arm2(progress_rising=None, mcap_delta_60s=Decimal(2)), strict
    ).refusals == ("progress_trend_unknown",)


# ---- the registered parameters ------------------------------------------------------------


def test_the_four_switches_are_listed_only_when_set_and_arm_1_does_not_change() -> None:
    assert ARM_2.as_parameters() == {
        **FLOW_GATE.as_parameters(),
        "max_snipers": "10",
        "min_holders": "20",
        "holders_rising_or_flat": "True",
        "creator_unknown_allowed_if_dev_measured": "True",
        "progress_or_mcap_rising": "True",
    }
    assert (
        not {
            "min_holders",
            "holders_rising_or_flat",
            "creator_unknown_allowed_if_dev_measured",
            "progress_or_mcap_rising",
        }
        & FLOW_GATE.as_parameters().keys()
    )


def test_a_negative_holders_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="min_holders"):
        EntryGate("k", 1, "d", 0, 1, Decimal(0), Decimal(1), Decimal(1), min_holders=-1)
