"""§8.3 day-loss contract: each deal once (by ticket), cost per leg = max(modelled,
|commission| + |fee|) and always positive, non-trading deals out of the P&L (deposits go to
``cash_flows``), the open position discounts only the exit fee, and no absent field becomes
zero. §8.5: duplicate deal + negative commission + mid-day deposit = the true loss."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hunter_risk_b3 import DayDeal, DealKind, summarize_deals

from . import factories as fx

pytestmark = pytest.mark.unit
D = Decimal
LEG = D("0.256")
Z = D("0")


def _trade(ticket: int, profit: str, commission: str = "0", fee: str = "0") -> DayDeal:
    return DayDeal(
        ticket=ticket, kind=DealKind.TRADE, profit=D(profit), commission=D(commission), fee=D(fee)
    )


def test_duplicate_negative_commission_and_deposit() -> None:
    deals = [
        _trade(1, "0", commission="-3"),  # entry leg: rebate never becomes a gain
        _trade(2, "-120", commission="0.10"),  # exit leg: modelled 0,256 > 0,10
        _trade(2, "-120", commission="0.10"),  # same deal delivered twice
        DayDeal(
            ticket=3, kind=DealKind.CASH_FLOW, profit=D("500"), commission=Z, fee=Z
        ),  # deposit at noon
        DayDeal(
            ticket=4, kind=DealKind.OTHER, profit=D("9"), commission=Z, fee=Z
        ),  # correction, not trading
    ]
    summary = summarize_deals(deals, per_leg_brl=LEG)
    assert summary.realized_gross_brl == D("-120")
    assert summary.costs_positive_brl == D("3") + LEG  # |−3| on leg 1, modelled on leg 2
    assert summary.cash_flows_brl == D("500")
    assert summary.trade_legs == 2


def test_a_ticket_with_two_different_contents_is_refused() -> None:
    with pytest.raises(ValueError, match="deal_ticket_conflict"):
        summarize_deals([_trade(1, "-1"), _trade(1, "-2")], per_leg_brl=LEG)


def test_the_true_loss_reaches_the_engine_through_the_summary() -> None:
    deals = [
        _trade(1, "0"),
        _trade(2, "-300"),
        DayDeal(ticket=3, kind=DealKind.CASH_FLOW, profit=D("1000"), commission=Z, fee=Z),
    ]
    summary = summarize_deals(deals, per_leg_brl=LEG)
    sc = fx.scenario()
    day = sc.ops.day.model_copy(
        update={
            "realized_gross_brl": summary.realized_gross_brl,
            "costs_positive_brl": summary.costs_positive_brl,
            "cash_flows_brl": summary.cash_flows_brl,
            # the broker's equity moved by the deposit plus the gross loss minus real fees (0)
            "equity_delta_brl": D("1000") + D("-300"),
        }
    )
    decision = sc.with_(ops=sc.ops.model_copy(update={"day": day})).evaluate()
    c14 = decision.checks[13]
    assert c14.state.value == "passed"
    assert c14.value == D("300") + 2 * LEG  # the deposit does not hide the loss


def test_the_open_position_discounts_only_the_exit_fee() -> None:
    sc = fx.scenario()
    day = sc.ops.day.model_copy(
        update={
            "open_mtm_gross_brl": D("-50"),
            "open_exit_fee_brl": LEG,
            "equity_delta_brl": D("-50"),
        }
    )
    decision = sc.with_(ops=sc.ops.model_copy(update={"day": day})).evaluate()
    assert decision.checks[13].value == D("50") + LEG


def test_a_gain_is_zero_loss_not_negative() -> None:
    sc = fx.scenario()
    day = sc.ops.day.model_copy(
        update={"realized_gross_brl": D("400"), "equity_delta_brl": D("400")}
    )
    decision = sc.with_(ops=sc.ops.model_copy(update={"day": day})).evaluate()
    assert decision.checks[13].value == D("0")
    assert decision.sizing is not None
    assert decision.sizing.allowance_brl == D("9000")


money = st.decimals(min_value=D("-5000"), max_value=D("5000"), places=2)
fees = st.decimals(min_value=D("-5"), max_value=D("5"), places=2)


@settings(max_examples=200, deadline=None)
@given(
    legs=st.lists(st.tuples(money, fees, fees), min_size=0, max_size=12),
    deposits=st.lists(st.decimals(min_value=D("-2000"), max_value=D("2000"), places=2), max_size=3),
    dup=st.lists(st.integers(min_value=0, max_value=11), max_size=4),
)
def test_property_summary_equals_the_true_loss(
    legs: list[tuple[Decimal, Decimal, Decimal]], deposits: list[Decimal], dup: list[int]
) -> None:
    deals = [_trade(i, str(p), str(c), str(f)) for i, (p, c, f) in enumerate(legs)]
    deals += [
        DayDeal(ticket=1000 + i, kind=DealKind.CASH_FLOW, profit=v, commission=Z, fee=Z)
        for i, v in enumerate(deposits)
    ]
    deals += [deals[i] for i in dup if i < len(legs)]  # redelivered deals
    summary = summarize_deals(deals, per_leg_brl=LEG)
    true_realized = sum((p for p, _, _ in legs), D(0))
    true_costs = sum((max(LEG, abs(c) + abs(f)) for _, c, f in legs), D(0))
    assert summary.realized_gross_brl == true_realized
    assert summary.costs_positive_brl == true_costs
    assert summary.costs_positive_brl >= 0
    assert summary.cash_flows_brl == sum(deposits, D(0))
