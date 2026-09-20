"""T4.78 — check 28 ``mint_cooldown_after_loss``: after a live position on a mint
closed with ``pnl_sol < 0``, a new buy on the **same** mint is refused for
``mint_cooldown_after_loss_s`` seconds (300 by default; ``0`` disables).

Everton's decision, 20/09/2026 ("eu exijo que mexa pelo menos um pouco na
estratégia"), applied as a repeated-exposure limit, not as a demonstrated edge
(Astra, ``.claude/state/astra-review-estrategia-2026-09-20.md`` item 2; EXP-M21).
Pure: the instant is ``wallet.as_of``; the losses arrive as an input
(``MemeWalletState.recent_losses``), read by the executor, never by the engine.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_risk_meme import (
    MINT_COOLDOWN_AFTER_LOSS,
    MemeCheck,
    MemeDecision,
    MemeExitProposal,
    MemeKillSwitchInputs,
    MemeLaunchProfile,
    MemePolicyMissing,
    MemeWalletState,
    OpenMemePosition,
    evaluate_meme_exit,
    limits_from_env,
)
from hunter_risk_meme.checks_wallet import mint_cooldown_after_loss_check
from hunter_risk_meme.limits import ENV_MINT_COOLDOWN_AFTER_LOSS

from .factories import AS_OF, MINT, decide, limits, proposal, wallet

pytestmark = pytest.mark.unit

OTHER = "So11111111111111111111111111111111111111112"
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.05",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "1800",
}
LAUNCH = MemeLaunchProfile(
    ticket_sol=Decimal("0.01"),
    max_open=2,
    max_participation_pct=Decimal("0.5"),
    max_token_age_s=600,
)


def _lost(seconds_ago: float, mint: str = MINT) -> MemeWalletState:
    return wallet(recent_losses={mint: AS_OF - timedelta(seconds=seconds_ago)})


def _check(decision: MemeDecision, name: str = "mint_cooldown_after_loss") -> MemeCheck:
    return next(c for c in decision.checks if c.name == name)


class TestTheCheck:
    def test_a_loss_one_hundred_seconds_ago_refuses_with_the_seconds_left(self) -> None:
        decision = decide(w=_lost(100))
        assert not decision.approved
        assert decision.refusals == (f"{MINT_COOLDOWN_AFTER_LOSS}:200",)
        assert decision.first_refusal == "mint_cooldown_after_loss:200"
        recorded = _check(decision)
        assert recorded.state == "failed"
        assert recorded.value == Decimal(100) and recorded.limit == Decimal(300)
        assert recorded.input_ts == (AS_OF - timedelta(seconds=100)).isoformat()

    def test_the_seconds_left_round_up_never_down(self) -> None:
        """199,6 s left is 200 — a refusal never claims the window is shorter."""
        decision = decide(w=_lost(100.4))
        assert decision.first_refusal == "mint_cooldown_after_loss:200"

    def test_the_last_second_of_the_window_still_refuses(self) -> None:
        decision = decide(w=_lost(299.5))
        assert decision.first_refusal == "mint_cooldown_after_loss:1"

    def test_allowed_once_the_window_has_elapsed(self) -> None:
        for seconds_ago in (300, 301, 3600):
            decision = decide(w=_lost(seconds_ago))
            assert decision.approved, (seconds_ago, decision.refusals)
            recorded = _check(decision)
            assert recorded.state == "passed" and recorded.refusal is None
            assert recorded.value == Decimal(seconds_ago)

    def test_zero_disables_the_check(self) -> None:
        decision = decide(w=_lost(1), lim=limits(mint_cooldown_after_loss_s=0))
        assert decision.approved, decision.refusals
        assert _check(decision).message == "disabled"

    def test_a_loss_on_mint_a_does_not_block_mint_b(self) -> None:
        decision = decide(w=_lost(10, mint=OTHER))
        assert decision.approved, decision.refusals

    def test_no_loss_passes_with_the_window_published(self) -> None:
        decision = decide()
        recorded = _check(decision)
        assert recorded.state == "passed" and recorded.limit == Decimal(300)

    def test_a_close_stamped_in_the_future_refuses_for_the_whole_window_at_most(self) -> None:
        """Two clocks disagreeing is not a fresh loss, but it is not "no loss"
        either: fail closed, bounded by the window."""
        decision = decide(w=wallet(recent_losses={MINT: AS_OF + timedelta(seconds=90)}))
        assert decision.first_refusal == "mint_cooldown_after_loss:300"

    def test_the_window_is_the_limits_own(self) -> None:
        decision = decide(w=_lost(100), lim=limits(mint_cooldown_after_loss_s=120))
        assert decision.first_refusal == "mint_cooldown_after_loss:20"
        assert decide(w=_lost(121), lim=limits(mint_cooldown_after_loss_s=120)).approved

    def test_the_pure_function_alone(self) -> None:
        recorded = mint_cooldown_after_loss_check(_lost(250), proposal(), limits())
        assert recorded.refusal == "mint_cooldown_after_loss:50"
        assert recorded.message == "closed with a loss 250s ago; window 300s"


class TestWhereItRuns:
    def test_it_is_the_last_check_so_its_refusal_means_everything_else_passed(self) -> None:
        """Evaluated after the sizing and the conviction: ``reason ==
        mint_cooldown_after_loss:*`` on a refused order says the cooldown was
        the **only** thing between the desk and the buy — the number the
        shadow measurement (EXP-M21) needs."""
        decision = decide(w=_lost(100))
        assert decision.checks[-1].name == "mint_cooldown_after_loss"
        assert all(c.passed for c in decision.checks[:-1])

    def test_it_is_recorded_after_an_earlier_refusal_too(self) -> None:
        blocked = decide(w=_lost(100), ks=MemeKillSwitchInputs(daily_loss_latched=True))
        assert blocked.refusals[0] == "daily_loss_cap_latched"
        assert blocked.refusals[-1] == "mint_cooldown_after_loss:200"

    def test_the_launch_profile_refuses_too(self) -> None:
        """A launch on a mint that just lost is the same re-entry — the lane does
        not skip this check (``LAUNCH_SKIPPED_CHECKS`` does not name it)."""
        decision = decide(
            w=_lost(30, mint=MINT), launch=LAUNCH, p=proposal(requested_sol=Decimal("0.01"))
        )
        assert decision.profile == "launch"
        assert "mint_cooldown_after_loss:270" in decision.refusals
        assert _check(decision).state == "failed"

    def test_a_sell_is_never_touched(self) -> None:
        """Exits are always allowed (§6): the cooldown is an entry limit."""
        position = OpenMemePosition(
            position_id="pos", mint=MINT, sol_spent=Decimal("0.02"), token_amount=10
        )
        decision = evaluate_meme_exit(
            MemeExitProposal(
                proposal_id="x1",
                wallet_id="w1",
                position_id="pos",
                mint=MINT,
                token_amount=10,
                reason="trailing",
            ),
            position,
            limits(),
            MemeKillSwitchInputs(),
            wallet=_lost(5),
        )
        assert decision.approved and decision.kind == "exit"
        assert decision.refusals == ()


class TestTheEnvironment:
    def test_absent_is_three_hundred_seconds(self) -> None:
        assert limits_from_env(POLICY).mint_cooldown_after_loss_s == 300
        assert ENV_MINT_COOLDOWN_AFTER_LOSS == "MEME_MINT_COOLDOWN_AFTER_LOSS_S"

    @pytest.mark.parametrize(("raw", "expected"), [("0", 0), ("600", 600), (" 45 ", 45)])
    def test_the_owner_s_number_is_the_one_applied(self, raw: str, expected: int) -> None:
        live = limits_from_env({**POLICY, ENV_MINT_COOLDOWN_AFTER_LOSS: raw})
        assert live.mint_cooldown_after_loss_s == expected

    @pytest.mark.parametrize("raw", ["abc", "-1", "1.5", "nan"])
    def test_unreadable_or_negative_refuses_the_boot_by_name(self, raw: str) -> None:
        with pytest.raises(MemePolicyMissing) as info:
            limits_from_env({**POLICY, ENV_MINT_COOLDOWN_AFTER_LOSS: raw})
        assert info.value.invalid == (ENV_MINT_COOLDOWN_AFTER_LOSS,)
        assert info.value.missing == ()
