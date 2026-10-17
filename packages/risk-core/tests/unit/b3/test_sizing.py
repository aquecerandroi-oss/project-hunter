"""§8.3 sizing: the minimum of the ceilings, the winner published as
``binding_constraint`` (ties broken by the contract's order), WARNING halving with
"1 becomes 0", volume normalisation always downwards, and the risk measured from the
worst admissible price (the limit price), never from the reference."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_b3 import Side, limit_price_for, risk_per_contract_brl

from . import factories as fx

pytestmark = pytest.mark.unit
D = Decimal

# ref 207005, limit 207010, stop 205975 → 207 ticks × R$ 1 + 2 ticks + 2 × 0,256
RISK_1 = D("209.512")


def _wide(**limits: object) -> fx.Scenario:
    """Caps loosened so the ceiling under test is the one that binds."""
    base: dict[str, object] = {"max_contracts_per_order": 50, "max_contracts_per_position": 50,
            "max_loss_per_trade_brl": D("5000")}  # fmt: skip
    base.update(limits)
    sc = fx.scenario()
    return sc.with_(
        limits=sc.limits.model_copy(update=base),
        proposal=sc.proposal.model_copy(update={"requested_contracts": 50}),
        margin=fx.margin(per_volume={v: D("100") * v for v in range(1, 51)},
                         order_check={v: fx.OrderCheckResult(ok=True) for v in range(1, 51)}),
    )  # fmt: skip


def test_limit_price_is_worst_admissible_on_each_side() -> None:
    assert limit_price_for(Side.BUY, D("207005"), D("5"), 1) == D("207010")
    assert limit_price_for(Side.SELL, D("207000"), D("5"), 1) == D("206995")


def test_risk_per_contract_is_from_limit_price_plus_stop_slippage_plus_round_trip_fees() -> None:
    sc = fx.scenario()
    risk = risk_per_contract_brl(
        limit_price=D("207010"), stop=D("205975"), pin=sc.spec.pin,
        stop_slippage_ticks=2, per_leg_brl=D("0.256"),
    )  # fmt: skip
    assert risk == RISK_1


def test_binding_requested_when_one_contract_is_asked() -> None:
    sizing = fx.scenario().evaluate().sizing
    assert sizing is not None
    assert sizing.caps["requested"] == 1
    assert sizing.binding_constraint == "requested"
    assert sizing.risk_per_contract_brl == RISK_1
    assert sizing.risk_modeled_brl == RISK_1
    assert sizing.limit_price == D("207010")
    assert sizing.bracket_gap_ticks is None


def test_tie_is_broken_by_contract_order() -> None:
    sc = fx.scenario()  # requested = per_order = per_position = 1
    assert sc.evaluate().sizing.binding_constraint == "requested"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("limits", "margin_free", "expected_binding", "expected_n", "approved"),
    [
        # check 12 refuses requested > cap, so these two bind only in a rejected decision
        ({"max_contracts_per_order": 3}, None, "max_contracts_per_order", 3, False),
        ({"max_contracts_per_position": 2}, None, "max_contracts_per_position", 2, False),
        ({"alloc_per_trade_brl": D("700")}, None, "alloc_margin", 7, True),
        ({}, D("900"), "free_margin", 4, True),
        ({"max_loss_per_trade_brl": D("1000")}, None, "trade_risk_cap", 4, True),
        ({"max_loss_per_trade_brl": D("5000"), "daily_loss_limit_brl": D("1100")}, None,
         "daily_allowance", 5, True),
    ],
)  # fmt: skip
def test_each_ceiling_can_bind(
    limits: dict[str, object],
    margin_free: Decimal | None,
    expected_binding: str,
    expected_n: int,
    approved: bool,
) -> None:
    sc = _wide(**limits)
    sc = sc.with_(
        limits=sc.limits.model_copy(
            update={"alloc_per_trade_brl": limits.get("alloc_per_trade_brl", D("5000"))}
        )
    )
    if margin_free is not None:
        sc = sc.with_(account=sc.account.model_copy(update={"margin_free": margin_free}))
    else:
        sc = sc.with_(account=sc.account.model_copy(update={"margin_free": D("100000")}))
    decision = sc.evaluate()
    sizing = decision.sizing
    assert sizing is not None
    assert (sizing.binding_constraint, sizing.n_final) == (expected_binding, expected_n), sizing
    assert decision.approved is approved, decision.reasons


def test_warning_halves_and_publishes_warning_halving() -> None:
    sc = _wide(max_contracts_per_order=5, alloc_per_trade_brl=D("5000"))
    sc = sc.with_(account=sc.account.model_copy(update={"margin_free": D("100000")}),
                  kill_switch=sc.kill_switch.model_copy(update={"robot": KillSwitchState.WARNING}))  # fmt: skip
    sizing = sc.evaluate().sizing
    assert sizing is not None
    assert (sizing.n_raw, sizing.n_final, sizing.binding_constraint) == (5, 2, "warning_halving")


def test_warning_with_one_contract_gives_zero_and_sizing_zero() -> None:
    sc = fx.scenario()
    sc = sc.with_(kill_switch=sc.kill_switch.model_copy(update={"robot": KillSwitchState.WARNING}))
    decision = sc.evaluate()
    assert decision.sizing is not None
    assert decision.sizing.n_final == 0
    assert decision.sizing.binding_constraint == "warning_halving"
    assert not decision.approved
    assert decision.reasons == ("sizing_zero",)


def test_automatic_warning_from_the_days_loss_halves_too() -> None:
    sc = _wide(max_contracts_per_order=4, alloc_per_trade_brl=D("5000"))
    sc = sc.with_(account=sc.account.model_copy(update={"margin_free": D("100000")}))
    day = sc.ops.day.model_copy(
        update={"realized_gross_brl": D("-4600"), "equity_delta_brl": D("-4600")}
    )
    sc = sc.with_(ops=sc.ops.model_copy(update={"day": day}))
    decision = sc.evaluate()
    assert decision.kill_switch_effective is KillSwitchState.WARNING
    assert decision.sizing is not None
    assert (decision.sizing.n_raw, decision.sizing.n_final) == (4, 2)


def test_volume_step_normalises_downwards() -> None:
    sc = _wide(max_contracts_per_order=5, alloc_per_trade_brl=D("5000"))
    sc = sc.with_(account=sc.account.model_copy(update={"margin_free": D("100000")}),
                  spec=fx.spec(pin={"volume_step": D("2")}, now={"volume_step": D("2")}))  # fmt: skip
    sizing = sc.evaluate().sizing
    assert sizing is not None
    assert (sizing.n_raw, sizing.n_final, sizing.binding_constraint) == (
        5,
        5,
        "max_contracts_per_order",
    )
    sc2 = sc.with_(limits=sc.limits.model_copy(update={"max_contracts_per_order": 4}))
    s2 = sc2.evaluate().sizing
    assert s2 is not None
    assert (s2.n_raw, s2.n_final, s2.binding_constraint) == (4, 3, "volume_step")


def test_zero_size_fails_the_winning_ceiling_with_its_reason() -> None:
    sc = fx.scenario()
    sc = sc.with_(limits=sc.limits.model_copy(update={"max_loss_per_trade_brl": D("200")}))
    decision = sc.evaluate()
    assert decision.sizing is not None
    assert decision.sizing.binding_constraint == "trade_risk_cap"
    assert decision.sizing.n_final == 0
    assert decision.reasons == ("trade_risk_exceeds_cap", "sizing_zero")


def test_sizing_without_a_computable_ceiling_never_approves() -> None:
    sc = fx.scenario()
    sc = sc.with_(margin=sc.margin.model_copy(update={"per_volume": {}}))
    decision = sc.evaluate()
    assert decision.sizing is not None
    assert decision.sizing.n_raw is None
    assert decision.sizing.caps["alloc_margin"] is None
    assert decision.sizing.n_final == 0
    assert not decision.approved


def test_margin_and_order_check_are_evaluated_at_the_final_volume() -> None:
    sc = _wide(max_contracts_per_order=3, alloc_per_trade_brl=D("5000"))
    sc = sc.with_(account=sc.account.model_copy(update={"margin_free": D("100000")}))
    refused = dict(sc.margin.order_check)
    refused[3] = fx.OrderCheckResult(ok=False, reason="limit_volume")
    sc = sc.with_(margin=sc.margin.model_copy(update={"order_check": refused}))
    decision = sc.evaluate()
    assert decision.checks[17].reason == "order_check_refused"
    assert decision.checks[17].value == 3
