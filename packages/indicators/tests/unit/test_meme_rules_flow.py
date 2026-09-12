"""The flow-and-holders criteria of the entry gate (T4.16, EXP-M5): each one
refuses by name, unknown inputs refuse by name, the 60 s market-cap delta
stands in for the tape's flow when the tape is absent, and a gate that does
not ask keeps EXP-M1's frozen parameters byte for byte."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.rules import EntryFeatures, EntryGate, evaluate_entry

pytestmark = pytest.mark.unit

FLOW_GATE = EntryGate(
    key="fluxo_e_holders",
    version=1,
    description="EXP-M5",
    min_age_s=30,
    max_age_s=300,
    min_progress_pct=Decimal(5),
    max_progress_pct=Decimal(100),
    max_participation_pct=Decimal(1),
    require_creator_not_net_seller=True,
    max_snipers=2,
    max_dev_share=Decimal("0.10"),
    require_positive_flow=True,
    min_unique_buyers=10,
    max_sells_to_buys=Decimal("0.6"),
    require_holders_rising=True,
    require_progress_rising=True,
)
FROZEN_M1 = EntryGate(
    key="comprar_cedo_na_curva",
    version=1,
    description="EXP-M1",
    min_age_s=30,
    max_age_s=600,
    min_progress_pct=Decimal(2),
    max_progress_pct=Decimal(50),
    max_participation_pct=Decimal(1),
)


def _features(**overrides: Any) -> EntryFeatures:
    base: dict[str, Any] = {
        "mint": "MINT",
        "age_s": 120,
        "progress_pct": Decimal(12),
        "creator_net_seller": False,
        "curve_volume_1m_sol": Decimal(20),
        "intended_size_sol": Decimal("0.05"),
        "dev_share": Decimal("0.05"),
        "snipers": 1,
        "net_sol_flow_1m": Decimal("0.8"),
        "buys_1m": 20,
        "sells_1m": 10,
        "unique_buyers_1m": 12,
        "holders_rising": True,
        "progress_rising": True,
    }
    base.update(overrides)
    return EntryFeatures(**base)


def test_a_coin_with_net_demand_buyers_and_rising_holders_passes() -> None:
    assert evaluate_entry(_features(), FLOW_GATE).allowed


@pytest.mark.parametrize(
    ("overrides", "refusal"),
    [
        ({"net_sol_flow_1m": Decimal("-0.1")}, "flow_not_positive"),
        ({"net_sol_flow_1m": Decimal(0)}, "flow_not_positive"),
        ({"unique_buyers_1m": 9}, "buyers_below_min"),
        ({"sells_1m": 13}, "sells_ratio_above_max"),
        ({"buys_1m": 0, "sells_1m": 0}, "no_buys"),
        ({"buys_1m": 0, "sells_1m": 3}, "no_buys"),
        ({"holders_rising": False}, "holders_not_rising"),
        ({"progress_rising": False}, "progress_not_rising"),
    ],
)
def test_each_flow_criterion_refuses_by_name(overrides: dict[str, Any], refusal: str) -> None:
    decision = evaluate_entry(_features(**overrides), FLOW_GATE)
    assert not decision.allowed and decision.refusals == (refusal,)


def test_the_sells_to_buys_ceiling_is_inclusive() -> None:
    assert evaluate_entry(_features(buys_1m=10, sells_1m=6), FLOW_GATE).allowed
    assert evaluate_entry(_features(buys_1m=10, sells_1m=7), FLOW_GATE).refusals == (
        "sells_ratio_above_max",
    )


def test_an_absent_tape_refuses_every_tape_criterion_by_its_reason() -> None:
    blind = _features(
        net_sol_flow_1m=None,
        buys_1m=None,
        sells_1m=None,
        unique_buyers_1m=None,
        curve_volume_1m_sol=None,
        tape_reason="not_polled",
    )
    decision = evaluate_entry(blind, FLOW_GATE)
    assert decision.refusals == (
        "curve_volume_1m_unknown",
        "flow_not_polled",
        "buyers_unknown",
        "sells_ratio_unknown",
    )
    unknown = evaluate_entry(
        _features(holders_rising=None, holders_reason="too_few_readings", progress_rising=None),
        FLOW_GATE,
    )
    assert unknown.refusals == ("holders_too_few_readings", "progress_trend_unknown")
    assert evaluate_entry(_features(holders_rising=None), FLOW_GATE).refusals == (
        "holders_unknown",
    )


def test_the_60_s_delta_stands_in_for_the_flow_only_when_the_tape_is_absent() -> None:
    by_delta = _features(net_sol_flow_1m=None, mcap_delta_60s=Decimal("2"))
    assert evaluate_entry(by_delta, FLOW_GATE).allowed
    falling = _features(net_sol_flow_1m=None, mcap_delta_60s=Decimal("-2"))
    assert evaluate_entry(falling, FLOW_GATE).refusals == ("flow_not_positive",)
    # The tape spoke: its word wins over the curve's delta.
    tape_wins = _features(net_sol_flow_1m=Decimal("-1"), mcap_delta_60s=Decimal("5"))
    assert evaluate_entry(tape_wins, FLOW_GATE).refusals == ("flow_not_positive",)
    nothing = _features(net_sol_flow_1m=None, mcap_delta_60s=None, tape_reason=None)
    assert "flow_unknown" in evaluate_entry(nothing, FLOW_GATE).refusals


def test_the_frozen_gates_do_not_ask_and_their_parameters_do_not_change() -> None:
    assert FROZEN_M1.as_parameters() == {
        "min_age_s": "30",
        "max_age_s": "600",
        "min_progress_pct": "2",
        "max_progress_pct": "50",
        "max_participation_pct": "1",
        "require_creator_not_net_seller": "True",
    }
    churn = _features(
        net_sol_flow_1m=Decimal("-3"), unique_buyers_1m=1, holders_rising=False, sells_1m=50
    )
    assert evaluate_entry(churn, FROZEN_M1).allowed, "a gate that does not ask does not refuse"
    assert FLOW_GATE.as_parameters() == {
        "min_age_s": "30",
        "max_age_s": "300",
        "min_progress_pct": "5",
        "max_progress_pct": "100",
        "max_participation_pct": "1",
        "require_creator_not_net_seller": "True",
        "max_dev_share": "0.10",
        "max_snipers": "2",
        "require_positive_flow": "True",
        "min_unique_buyers": "10",
        "max_sells_to_buys": "0.6",
        "require_holders_rising": "True",
        "require_progress_rising": "True",
    }


def test_the_new_ceilings_refuse_nonsense() -> None:
    with pytest.raises(ValueError, match="min_unique_buyers"):
        EntryGate("k", 1, "d", 0, 1, Decimal(0), Decimal(1), Decimal(1), min_unique_buyers=-1)
    with pytest.raises(ValueError, match="max_sells_to_buys"):
        EntryGate(
            "k", 1, "d", 0, 1, Decimal(0), Decimal(1), Decimal(1), max_sells_to_buys=Decimal(-1)
        )
