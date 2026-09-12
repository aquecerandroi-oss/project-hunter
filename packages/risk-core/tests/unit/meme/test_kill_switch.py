"""VM3 in the pure engine: the daily latch blocks entries and never exits,
``resume`` is OWNER-only and refused while the assessment still blocks, and the
effective state is the most restrictive scope."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import (
    MemeExitProposal,
    MemeKillSwitchInputs,
    MemeResumeAuthorization,
    MemeResumeRefused,
    OpenMemePosition,
    assess,
    evaluate_meme_exit,
    most_restrictive,
    resume,
)

from .factories import MINT, limits, wallet

pytestmark = pytest.mark.unit

POSITION = OpenMemePosition(
    position_id="pos",
    mint=MINT,
    sol_spent=Decimal("0.05"),
    token_amount=1000,
    mark_sol=Decimal("0.03"),
)


def test_ordering_is_declared_not_alphabetical() -> None:
    assert (
        most_restrictive(KillSwitchState.WARNING, KillSwitchState.TRADING_DISABLED)
        is KillSwitchState.TRADING_DISABLED
    )
    assert (
        most_restrictive(KillSwitchState.EMERGENCY, KillSwitchState.WARNING)
        is KillSwitchState.EMERGENCY
    )


def test_the_daily_cap_latches_and_blocks_entries() -> None:
    lost = wallet(sol_balance=Decimal("0.79"), day_start_sol_equity=Decimal("1.0"))
    a = assess(lost, limits(), MemeKillSwitchInputs())
    assert a.automatic is KillSwitchState.TRADING_DISABLED
    assert a.latched and a.blocks_entries and a.cancel_pending
    assert a.trigger == "daily_loss"
    assert a.entry_size_multiplier == Decimal("0")


def test_the_latch_holds_after_the_mark_recovers() -> None:
    recovered = wallet(
        sol_balance=Decimal("1.2"),
        day_start_sol_equity=Decimal("1.0"),
        peak_sol_equity=Decimal("1.2"),
    )
    a = assess(recovered, limits(), MemeKillSwitchInputs(daily_loss_latched=True))
    assert a.effective is KillSwitchState.TRADING_DISABLED
    assert a.latched


def test_half_the_cap_is_a_warning_with_half_size() -> None:
    a = assess(wallet(sol_balance=Decimal("0.9")), limits(), MemeKillSwitchInputs())
    assert a.effective is KillSwitchState.WARNING
    assert a.entry_size_multiplier == Decimal("0.5")
    assert not a.latched


def test_resume_requires_the_owner() -> None:
    with pytest.raises(MemeResumeRefused, match="resume_requires_owner"):
        resume(
            wallet(),
            limits(),
            MemeKillSwitchInputs(daily_loss_latched=True),
            MemeResumeAuthorization(wallet_id="w1", actor_role="ADMIN", actor_id="u", reason="r"),
        )


def test_resume_is_refused_while_the_day_still_blocks() -> None:
    lost = wallet(sol_balance=Decimal("0.79"), day_start_sol_equity=Decimal("1.0"))
    with pytest.raises(MemeResumeRefused, match="still_blocked_by_daily_loss"):
        resume(
            lost,
            limits(),
            MemeKillSwitchInputs(daily_loss_latched=True),
            MemeResumeAuthorization(wallet_id="w1", actor_role="OWNER", actor_id="u", reason="r"),
        )


def test_resume_releases_the_latch_once_the_day_no_longer_blocks() -> None:
    released = resume(
        wallet(sol_balance=Decimal("0.9")),
        limits(),
        MemeKillSwitchInputs(daily_loss_latched=True),
        MemeResumeAuthorization(wallet_id="w1", actor_role="OWNER", actor_id="u", reason="r"),
    )
    assert released.daily_loss_latched is False


@pytest.mark.parametrize("state", list(KillSwitchState))
def test_an_exit_is_approved_in_every_kill_switch_state(state: KillSwitchState) -> None:
    decision = evaluate_meme_exit(
        MemeExitProposal(
            proposal_id="x",
            wallet_id="w1",
            position_id="pos",
            mint=MINT,
            token_amount=1000,
            reason="target",
        ),
        POSITION,
        limits(),
        MemeKillSwitchInputs(system=state, daily_loss_latched=True),
    )
    assert decision.approved
    assert decision.exit_plan is not None and decision.exit_plan.approved_tokens == 1000
    assert decision.effective_kill_switch is most_restrictive(state, KillSwitchState.ACTIVE)


def test_an_exit_never_sells_more_than_the_position_and_routes_after_migration() -> None:
    migrated = POSITION.model_copy(update={"migrated": True})
    decision = evaluate_meme_exit(
        MemeExitProposal(
            proposal_id="x",
            wallet_id="w1",
            position_id="pos",
            mint=MINT,
            token_amount=5000,
            reason="sell_now",
        ),
        migrated,
        limits(),
        MemeKillSwitchInputs(),
        wallet=wallet(positions=(POSITION.model_copy(update={"token_amount": 400}),)),
    )
    assert decision.exit_plan is not None
    assert decision.exit_plan.approved_tokens == 400 and decision.exit_plan.clamped
    assert decision.exit_plan.route == "pumpswap"
