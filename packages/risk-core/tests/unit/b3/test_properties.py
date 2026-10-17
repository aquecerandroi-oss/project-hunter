"""§8.5 invariants, over generated scenarios (hypothesis):

- approved ⇒ ``n_final × risk_per_contract ≤ min(max_loss_per_trade_brl, allowance)``,
  with the risk measured from the limit price (worst admissible entry);
- ``n_final ≤`` every ceiling, always;
- effective kill ≥ TRADING_DISABLED ⇒ never approved;
- WARNING with ``n_raw = 1`` gives 0;
- 25 checks in every decision, same inputs ⇒ same hash;
- an unavailable input refuses and never passes.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from hunter_core.domain.enums import KillSwitchState as K
from hunter_risk_b3 import CheckState, FeeSchedule, RiskLimitsB3, Side, most_restrictive

from . import factories as fx
from .factories import Scenario

pytestmark = pytest.mark.unit
SETTINGS = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
D = Decimal
TICK = D("5")

states = st.sampled_from(list(K))
money = st.decimals(min_value=D("10"), max_value=D("20000"), places=2)


@st.composite
def scenarios(draw: st.DrawFn, *, approvable: bool = False) -> Scenario:
    """Limits go through real validation (no ``model_copy`` shortcut). With
    ``approvable`` the persisted scopes stay ACTIVE and the ranges are scaled so most
    draws reach the approved branch while every ceiling (and the automatic WARNING
    from the day loss) can still bind."""
    side = draw(st.sampled_from([Side.BUY, Side.SELL]))
    slip = draw(st.integers(0, 3))
    dist = draw(st.integers(slip + 2, 120 if approvable else 450))
    ask = D("207005")
    bid = ask - TICK
    ref = ask if side is Side.BUY else bid
    limit = ref + slip * TICK if side is Side.BUY else ref - slip * TICK
    stop = limit - dist * TICK if side is Side.BUY else limit + dist * TICK
    per_order = draw(st.integers(1, 6))
    max_volume = 60
    per_contract = draw(
        st.decimals(min_value=D("10"), max_value=D("300" if approvable else "3000"), places=2)
    )
    roomy = st.decimals(min_value=D("1500"), max_value=D("20000"), places=2)
    wide = roomy if approvable else money
    sc = fx.scenario()
    max_loss = draw(wide)
    daily = draw(st.decimals(min_value=max_loss, max_value=D("30000"), places=2))
    floor_realized = -daily * D("0.75") if approvable else -daily * 2
    realized = draw(st.decimals(min_value=floor_realized, max_value=D("2000"), places=2))
    limits = RiskLimitsB3.model_validate(
        sc.limits.model_dump()
        | {
            "max_slippage_ticks": slip,
            "max_contracts_per_order": per_order,
            "max_contracts_per_position": draw(st.integers(per_order, 6)),
            "max_loss_per_trade_brl": max_loss,
            "daily_loss_limit_brl": daily,
            "alloc_per_trade_brl": draw(wide),
            "margin_use_max_pct": draw(
                st.decimals(min_value=D("0.05"), max_value=D("1"), places=2)
            ),
            "stop_slippage_ticks": draw(st.integers(0, 5)),
            "max_stop_ticks": 1000,
        }
    )
    step = draw(st.sampled_from([D("1"), D("2"), D("3")]))
    tick_value = draw(st.sampled_from([D("0.2"), D("1"), D("5"), D("10")]))
    spec = fx.spec(
        pin={"volume_step": step, "trade_tick_value": tick_value},
        now={"volume_step": step, "trade_tick_value": tick_value},
    )
    day = sc.ops.day.model_copy(
        update={"realized_gross_brl": realized, "equity_delta_brl": realized}
    )
    fee = draw(st.decimals(min_value=D("0"), max_value=D("3"), places=3))
    kill = st.just(K.ACTIVE) if approvable else states
    return sc.with_(
        proposal=sc.proposal.model_copy(update={
            "side": side, "ref_price": ref, "stop_price": stop,
            "requested_contracts": draw(st.integers(1, per_order)),
        }),
        quote=sc.quote.model_copy(update={"bid": bid, "ask": ask}),
        limits=limits,
        spec=spec,
        account=sc.account.model_copy(update={"margin_free": draw(wide)}),
        margin=fx.margin(
            per_volume={v: per_contract * v for v in range(1, max_volume + 1)},
            order_check={v: fx.OrderCheckResult(ok=True) for v in range(1, max_volume + 1)},
        ),
        kill_switch=sc.kill_switch.model_copy(update={
            "system": draw(kill), "organization": draw(kill), "robot": draw(kill),
        }),
        ops=sc.ops.model_copy(update={
            "day": day,
            "fee_schedule": FeeSchedule(per_leg_brl=fee, source="test fixture", valid=True),
        }),
    )  # fmt: skip


@SETTINGS
@given(scenarios(approvable=True))
def test_modelled_risk_never_exceeds_cap_or_allowance(sc: Scenario) -> None:
    decision = sc.evaluate()
    # filtering (not returning) makes Hypothesis fail its health check if approvals
    # were rare, so this property provably runs on the approved branch
    assume(decision.approved)
    sizing = decision.sizing
    assert sizing is not None
    assert sizing.n_final >= 1
    assert sizing.risk_per_contract_brl is not None
    assert sizing.allowance_brl is not None
    modelled = sizing.n_final * sizing.risk_per_contract_brl
    assert modelled == sizing.risk_modeled_brl
    assert modelled <= min(sc.limits.max_loss_per_trade_brl, sizing.allowance_brl)
    assert sizing.limit_price is not None
    # the risk is measured from the limit price, never from the reference
    ticks = abs(sizing.limit_price - (sc.proposal.stop_price or D(0))) / TICK
    assert sizing.risk_per_contract_brl >= ticks * sc.spec.pin.trade_tick_value


@SETTINGS
@given(scenarios())
def test_size_never_exceeds_any_ceiling(sc: Scenario) -> None:
    sizing = sc.evaluate().sizing
    assert sizing is not None
    for name, cap in sizing.caps.items():
        if cap is not None:
            assert sizing.n_final <= cap, name
    assert sizing.n_final <= sc.limits.max_contracts_per_order
    assert D(sizing.n_final) <= sc.spec.pin.volume_max


@SETTINGS
@given(scenarios())
def test_kill_at_or_above_disabled_never_approves(sc: Scenario) -> None:
    decision = sc.evaluate()
    ks = sc.kill_switch
    eff = most_restrictive(ks.system, ks.organization, ks.robot)
    if eff in (K.TRADING_DISABLED, K.EMERGENCY):
        assert not decision.approved
    assert len(decision.checks) == 25


@SETTINGS
@given(scenarios())
def test_warning_with_one_raw_contract_gives_zero(sc: Scenario) -> None:
    decision = sc.evaluate()
    sizing = decision.sizing
    assert sizing is not None
    if decision.kill_switch_effective is K.WARNING and sizing.n_raw == 1:
        assert sizing.n_final == 0
        assert not decision.approved


@SETTINGS
@given(scenarios())
def test_determinism(sc: Scenario) -> None:
    assert sc.evaluate().decision_hash() == sc.evaluate().decision_hash()


def _upd(attr: str, **u: object) -> Callable[[Scenario], Scenario]:
    return lambda sc: sc.with_(**{attr: getattr(sc, attr).model_copy(update=u)})


def _day(**u: object) -> Callable[[Scenario], Scenario]:
    return lambda sc: sc.with_(
        ops=sc.ops.model_copy(update={"day": sc.ops.day.model_copy(update=u)})
    )


UNAVAILABLE: list[tuple[int, Callable[[Scenario], Scenario]]] = [
    (2, _upd("account", read_ok=False)),
    (3, _upd("broker", terminal=fx.broker().terminal.model_copy(update={"read_ok": False}))),
    (4, _upd("calendar", current_contract=None)),
    (5, _upd("calendar", has_grid=False)),
    (7, _upd("session", flatten_at_utc=None)),
    (8, _upd("quote", read_ok=False, bid=None, ask=None, last=None, time_utc=None)),
    (10, _upd("broker", positions_ok=False)),
    (11, _upd("broker", orders_ok=False)),
    (13, _day(history_complete=False)),
    (14, _day(anchor_at=None)),
    (14, _day(cash_flows_brl=None)),
    (14, _day(mark_time=None)),
    (16, _upd("ops", fee_schedule=FeeSchedule(per_leg_brl=None, source=None, valid=False))),
    (18, _upd("margin", read_ok=False)),
    (20, _upd("ops", last_reconcile=None)),
    (23, lambda sc: sc.with_(spec=fx.spec(now={"status": fx.SpecStatus.UNREADABLE}))),
]


@SETTINGS
@given(scenarios(), st.sampled_from(UNAVAILABLE))
def test_an_unavailable_input_refuses_and_never_passes(
    sc: Scenario, case: tuple[int, Callable[[Scenario], Scenario]]
) -> None:
    check_id, mutate = case
    decision = mutate(sc).evaluate()
    assert not decision.approved
    assert decision.checks[check_id - 1].state is CheckState.UNAVAILABLE
    assert decision.checks[check_id - 1].reason in decision.reasons
