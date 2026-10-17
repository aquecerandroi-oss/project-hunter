"""§7.1: effective state = the most restrictive of system / organization / robot, by the
explicit order ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY (never ``max()`` over the
StrEnum, which sorts "WARNING" above "EMERGENCY"), and what each state does."""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState as K
from hunter_risk_b3 import automatic_state, blocks_entries, kill_policy, most_restrictive

from . import factories as fx

pytestmark = pytest.mark.unit

ORDER = [K.ACTIVE, K.WARNING, K.TRADING_DISABLED, K.EMERGENCY]


@pytest.mark.parametrize("states", list(itertools.product(ORDER, repeat=3)))
def test_most_restrictive_is_the_highest_rank(states: tuple[K, K, K]) -> None:
    assert most_restrictive(*states) is max(states, key=ORDER.index)


def test_string_order_would_be_wrong_and_is_not_used() -> None:
    assert max(K.WARNING.value, K.EMERGENCY.value) == "WARNING"  # the trap
    assert most_restrictive(K.WARNING, K.EMERGENCY) is K.EMERGENCY


def test_entries_blocked_from_trading_disabled_up() -> None:
    assert [blocks_entries(s) for s in ORDER] == [False, False, True, True]


def test_policy_per_state() -> None:
    active, warning, disabled, emergency = (kill_policy(s) for s in ORDER)
    assert (active.entries_allowed, active.size_halved) == (True, False)
    assert (warning.entries_allowed, warning.size_halved) == (True, True)
    assert (disabled.entries_allowed, disabled.cancel_entry_orders) == (False, True)
    assert disabled.flatten_positions is False
    assert (emergency.cancel_entry_orders, emergency.flatten_positions) == (True, True)


def test_automatic_state_from_the_days_loss() -> None:
    limits = fx.limits()  # 9000, warning at 0.5
    assert automatic_state(Decimal("4499.99"), limits) is K.ACTIVE
    assert automatic_state(Decimal("4500"), limits) is K.WARNING
    assert automatic_state(Decimal("9000"), limits) is K.TRADING_DISABLED


@pytest.mark.parametrize("state", [K.TRADING_DISABLED, K.EMERGENCY])
@pytest.mark.parametrize("scope", ["system", "organization", "robot"])
def test_any_scope_at_or_above_disabled_rejects_the_entry(scope: str, state: K) -> None:
    sc = fx.scenario()
    sc = sc.with_(kill_switch=sc.kill_switch.model_copy(update={scope: state}))
    decision = sc.evaluate()
    assert not decision.approved
    assert decision.kill_switch_effective is state


def test_daily_loss_failure_emits_the_trigger() -> None:
    sc = fx.scenario()
    day = sc.ops.day.model_copy(
        update={"realized_gross_brl": Decimal("-9500"), "equity_delta_brl": Decimal("-9500")}
    )
    decision = sc.with_(ops=sc.ops.model_copy(update={"day": day})).evaluate()
    assert "daily_loss_limit" in decision.triggers
    assert decision.kill_switch_effective is K.TRADING_DISABLED


def test_breaker_trips_once_and_a_latched_breaker_does_not_re_emit() -> None:
    sc = fx.scenario()
    rejects = (fx.NOW,) * 3
    tripped = sc.with_(ops=sc.ops.model_copy(update={"entry_rejects": rejects})).evaluate()
    assert tripped.triggers == ("broker_reject_breaker",)
    latched = sc.with_(ops=sc.ops.model_copy(update={"breaker_latched": True})).evaluate()
    assert latched.triggers == ()
    assert latched.checks[18].reason == "broker_reject_breaker"
