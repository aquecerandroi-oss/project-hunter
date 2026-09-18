"""T4.60 — the daily loss is blind to treasury inflows unless they are an input.

The real case (18/09/2026 13:12 BRT): position YOU lost 0.0395 SOL (bought
0.0516, sold 0.0121); at 13:12:06 the treasury swapped 5.75 USDC into 0.0516
SOL because the wallet had fallen below the floor. The executor then published
``daily_loss_sol = 0`` (``equity_sol 0.732 > day_start_sol_equity 0.686``):
``day_start − equity`` cannot see a top-up, so the cap never trips while USDC
keeps refilling the wallet. ``MemeWalletState.treasury_inflow_today_sol`` is
the input that fixes it: ``daily_loss = day_start + inflow − equity``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import MemeKillSwitchInputs, assess

from .factories import decide, limits, wallet

pytestmark = pytest.mark.unit

DAY_START = Decimal("0.686")
LOSS_YOU = Decimal("0.0395")
INFLOW_YOU = Decimal("0.0516")
# What the heartbeat published after the sell and the swap, both settled:
EQUITY_AFTER = DAY_START - LOSS_YOU + INFLOW_YOU  # 0.6981 (the log said 0.732 with marks)


def test_the_you_case_loss_is_the_loss_not_zero() -> None:
    blind = wallet(sol_balance=EQUITY_AFTER, day_start_sol_equity=DAY_START)
    assert blind.daily_loss_sol == Decimal(0), "the defect: the top-up hides the loss"
    seen = wallet(
        sol_balance=EQUITY_AFTER,
        day_start_sol_equity=DAY_START,
        treasury_inflow_today_sol=INFLOW_YOU,
    )
    assert seen.daily_loss_sol == LOSS_YOU


def test_an_inflow_never_turns_a_gain_into_a_loss_below_zero() -> None:
    up = wallet(
        sol_balance=Decimal("1.2"),
        day_start_sol_equity=Decimal("1.0"),
        peak_sol_equity=Decimal("1.2"),
        treasury_inflow_today_sol=Decimal("0.05"),
    )
    assert up.daily_loss_sol == Decimal(0)


def test_the_cap_trips_at_0_15_only_when_the_inflow_is_counted() -> None:
    """Three top-ups of 0.0516 SOL refilled 0.1548 SOL; the desk lost 0.15 SOL
    on the day. Without the inflow the equity looks *up* by 0.0048 SOL."""
    cap = limits(daily_loss_cap_sol=Decimal("0.15"))
    inflow = INFLOW_YOU * 3
    equity = Decimal("1.0") - Decimal("0.15") + inflow
    blind = assess(
        wallet(sol_balance=equity, day_start_sol_equity=Decimal("1.0"), peak_sol_equity=equity),
        cap,
        MemeKillSwitchInputs(),
    )
    assert blind.automatic is KillSwitchState.ACTIVE and blind.daily_loss_sol == 0
    seen = assess(
        wallet(
            sol_balance=equity,
            day_start_sol_equity=Decimal("1.0"),
            peak_sol_equity=equity,
            treasury_inflow_today_sol=inflow,
        ),
        cap,
        MemeKillSwitchInputs(),
    )
    assert seen.daily_loss_sol == Decimal("0.15")
    assert seen.automatic is KillSwitchState.TRADING_DISABLED
    assert seen.latched and seen.blocks_entries
    assert seen.trigger == "daily_loss"


def test_the_admission_check_18_refuses_by_name_with_the_inflow_counted() -> None:
    cap = limits(daily_loss_cap_sol=Decimal("0.15"))
    equity = Decimal("1.0") - Decimal("0.15") + INFLOW_YOU * 3
    passing = decide(
        w=wallet(sol_balance=equity, day_start_sol_equity=Decimal("1.0"), peak_sol_equity=equity),
        lim=cap,
    )
    assert passing.approved
    refused = decide(
        w=wallet(
            sol_balance=equity,
            day_start_sol_equity=Decimal("1.0"),
            peak_sol_equity=equity,
            treasury_inflow_today_sol=INFLOW_YOU * 3,
        ),
        lim=cap,
    )
    assert not refused.approved
    # Check 1 sees the automatic TRADING_DISABLED first; check 18 is still
    # recorded, failed and by name, with the inflow-corrected loss as its value.
    assert refused.first_refusal == "kill_switch_blocked"
    assert refused.effective_kill_switch is KillSwitchState.TRADING_DISABLED
    daily = next(c for c in refused.checks if c.name == "daily_loss")
    assert not daily.passed and daily.refusal == "daily_loss_cap_reached"
    assert daily.value == Decimal("0.15") and daily.limit == Decimal("0.15")


def test_a_negative_inflow_is_not_an_input() -> None:
    with pytest.raises(ValueError):
        wallet(treasury_inflow_today_sol=Decimal("-0.01"))
