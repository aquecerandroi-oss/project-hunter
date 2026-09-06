"""``evaluate`` and ``evaluate_exit``: one table, a pass and a failure per check."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import ExitReason, KillSwitchState, MarketType, TradeDirection
from hunter_risk.decision import CheckState, RiskDecision
from hunter_risk.evaluate import ENTRY_CHECKS, evaluate, evaluate_exit
from hunter_risk.kill_switch import KillSwitchInputs
from hunter_risk.limits import PAPER_V1

from .factories import (
    NOW,
    beta,
    exit_proposal,
    liquidity,
    market,
    pending,
    portfolio,
    position,
    proposal,
    spec,
)

pytestmark = pytest.mark.unit


def decide(**over: Any) -> RiskDecision:
    kwargs: dict[str, Any] = {
        "proposal": proposal(),
        "portfolio": portfolio(),
        "limits": PAPER_V1,
        "liquidity": liquidity(),
        "kill_switch": KillSwitchInputs(),
        "beta": beta(),
        "spec": spec(),
    }
    return evaluate(**(kwargs | over))


def state_of(decision: RiskDecision, name: str) -> CheckState:
    return next(check.state for check in decision.checks if check.name == name)


class TestTheHappyCase:
    def test_a_clean_proposal_is_approved_and_sized(self) -> None:
        got = decide()
        assert got.approved is True
        assert got.rejection_reasons == ()
        assert got.sizing is not None
        assert got.sizing.qty == Decimal("18.518")
        assert got.binding_limit is not None
        assert got.binding_limit.name == "risk_per_trade"

    def test_every_check_of_the_contract_is_recorded_in_a_fixed_order(self) -> None:
        assert tuple(check.name for check in decide().checks) == ENTRY_CHECKS

    def test_the_decision_is_serialisable_for_trade_proposals(self) -> None:
        body = decide().to_jsonable()
        assert body["approved"] is True
        assert body["sizing"]["binding_limit"]["name"] == "risk_per_trade"
        assert body["sizing"]["qty"] == "18.518"

    def test_evaluate_is_deterministic(self) -> None:
        assert decide().to_jsonable() == decide().to_jsonable()


class TestEveryCheckFails:
    """One failing case per check; the passing case is the happy path above."""

    def test_market_identity_mismatch_between_proposal_and_book(self) -> None:
        got = decide(liquidity=liquidity(market=market("ETHUSDT", "ETH")))
        assert state_of(got, "market_identity") is CheckState.FAILED
        assert got.approved is False

    def test_a_perpetual_is_refused_because_the_wallet_is_spot_only(self) -> None:
        perp = market().model_copy(update={"market_type": MarketType.PERPETUAL})
        got = decide(
            proposal=proposal(market=perp), liquidity=liquidity(market=perp), spec=spec(market=perp)
        )
        assert state_of(got, "modality") is CheckState.FAILED

    def test_a_short_is_refused(self) -> None:
        got = decide(proposal=proposal(direction=TradeDirection.SHORT))
        assert state_of(got, "modality") is CheckState.FAILED

    def test_the_kill_switch_blocks_entries(self) -> None:
        got = decide(kill_switch=KillSwitchInputs(system=KillSwitchState.TRADING_DISABLED))
        assert state_of(got, "kill_switch") is CheckState.FAILED
        assert got.cancel_pending is True

    def test_degraded_market_data_rejects(self) -> None:
        got = decide(liquidity=liquidity(data_quality="degraded"))
        assert state_of(got, "data_quality") is CheckState.FAILED

    def test_a_price_older_than_ten_seconds_rejects(self) -> None:
        got = decide(liquidity=liquidity(price_ts=NOW - timedelta(seconds=11)))
        assert state_of(got, "data_quality") is CheckState.FAILED

    def test_an_absent_book_is_unavailable_not_skipped(self) -> None:
        got = decide(liquidity=liquidity(asks=(), book_ts=None))
        assert state_of(got, "book_depth") is CheckState.UNAVAILABLE
        assert state_of(got, "slippage_estimate") is CheckState.UNAVAILABLE
        assert got.approved is False

    def test_a_stale_book_rejects(self) -> None:
        got = decide(liquidity=liquidity(book_ts=NOW - timedelta(seconds=30)))
        assert state_of(got, "book_depth") is CheckState.FAILED

    def test_a_wide_spread_rejects(self) -> None:
        got = decide(liquidity=liquidity(best_bid=Decimal("99.9"), best_ask=Decimal("100.1")))
        assert state_of(got, "spread") is CheckState.FAILED

    def test_an_incomplete_volume_window_is_unavailable(self) -> None:
        got = decide(liquidity=liquidity(volume_window_complete=False))
        assert state_of(got, "participation") is CheckState.UNAVAILABLE
        assert got.sizing is None

    def test_a_market_below_the_fifty_million_floor_rejects(self) -> None:
        got = decide(liquidity=liquidity(quote_volume_24h=Decimal("40000000")))
        assert state_of(got, "liquidity_24h") is CheckState.FAILED

    def test_an_unknown_24h_volume_is_unavailable(self) -> None:
        got = decide(liquidity=liquidity(quote_volume_24h=None))
        assert state_of(got, "liquidity_24h") is CheckState.UNAVAILABLE

    def test_an_unvalidated_beta_keeps_the_asset_in_shadow(self) -> None:
        got = decide(beta=beta(validated=False))
        assert state_of(got, "beta_validity") is CheckState.UNAVAILABLE
        assert got.shadow_only is True
        assert got.approved is False

    def test_a_stale_beta_keeps_the_asset_in_shadow(self) -> None:
        got = decide(beta=beta(as_of=NOW - timedelta(hours=5)))
        assert state_of(got, "beta_validity") is CheckState.UNAVAILABLE
        assert got.shadow_only is True

    def test_a_held_position_without_a_beta_makes_the_aggregate_unknown(self) -> None:
        state = portfolio(
            open_positions=(position(market=market("ETHUSDT", "ETH"), beta_btc=None),)
        )
        got = decide(portfolio=state)
        assert state_of(got, "beta_validity") is CheckState.UNAVAILABLE
        assert state_of(got, "exposure_after") is CheckState.UNAVAILABLE

    def test_incomplete_marks_make_the_equity_unusable(self) -> None:
        got = decide(portfolio=portfolio(marks_complete=False))
        assert state_of(got, "portfolio_status") is CheckState.UNAVAILABLE

    def test_a_paused_portfolio_or_a_disabled_agent_rejects(self) -> None:
        assert state_of(decide(portfolio=portfolio(is_active=False)), "portfolio_status") is (
            CheckState.FAILED
        )
        assert (
            state_of(decide(proposal=proposal(agent_enabled=False)), "portfolio_status")
            is CheckState.FAILED
        )

    def test_an_unrecovered_collection_gap_rejects(self) -> None:
        assert state_of(decide(liquidity=liquidity(gap_state="open_gap")), "market_gap") is (
            CheckState.FAILED
        )
        assert state_of(decide(liquidity=liquidity(gap_state=None)), "market_gap") is (
            CheckState.UNAVAILABLE
        )

    def test_a_market_that_left_the_universe_rejects(self) -> None:
        assert (
            state_of(decide(liquidity=liquidity(in_universe=False)), "market_in_universe")
            is CheckState.FAILED
        )
        assert (
            state_of(decide(liquidity=liquidity(in_universe=None)), "market_in_universe")
            is CheckState.UNAVAILABLE
        )

    def test_an_invalidated_signal_rejects(self) -> None:
        got = decide(proposal=proposal(signal_valid=False))
        assert state_of(got, "signal_validity") is CheckState.FAILED

    def test_a_stop_outside_the_declared_band_rejects_on_both_sides(self) -> None:
        assert (
            state_of(decide(proposal=proposal(stop=Decimal("99.9"))), "stop_distance")
            is CheckState.FAILED
        )
        assert (
            state_of(decide(proposal=proposal(stop=Decimal("95"))), "stop_distance")
            is CheckState.FAILED
        )

    def test_a_stop_above_the_entry_rejects_instead_of_dividing_by_zero(self) -> None:
        got = decide(proposal=proposal(stop=Decimal("101")))
        assert state_of(got, "signal_validity") is CheckState.FAILED
        assert got.sizing is None

    def test_the_daily_loss_limit_rejects_entries(self) -> None:
        state = portfolio(
            equity=Decimal("19600"), peak_equity=Decimal("20000"), cash=Decimal("19600")
        ).model_copy(
            update={"day_start_equity": Decimal("20000"), "daily_realized_pnl": Decimal("-400")}
        )
        got = decide(portfolio=state)
        assert state_of(got, "daily_loss") is CheckState.FAILED
        assert state_of(got, "kill_switch") is CheckState.FAILED

    def test_the_drawdown_limit_rejects_entries(self) -> None:
        state = portfolio(equity=Decimal("18400"), peak_equity=Decimal("20000")).model_copy(
            update={"day_start_equity": Decimal("18400")}
        )
        got = decide(portfolio=state)
        assert state_of(got, "drawdown") is CheckState.FAILED

    def test_the_sixth_slot_does_not_exist(self) -> None:
        state = portfolio(
            open_positions=tuple(
                position(
                    position_id=uuid.UUID(int=i),
                    market=market(f"C{i}USDT", f"C{i}"),
                    notional=Decimal("100"),
                    planned_risk_quote=Decimal("1"),
                )
                for i in range(4)
            ),
            pending_entries=(
                pending(
                    market=market("C9USDT", "C9"),
                    reserved_notional=Decimal("100"),
                    planned_risk_quote=Decimal("1"),
                ),
            ),
        )
        got = decide(portfolio=state)
        assert state_of(got, "concurrent_positions") is CheckState.FAILED

    def test_a_coin_is_never_held_twice(self) -> None:
        state = portfolio(
            open_positions=(position(notional=Decimal("100"), planned_risk_quote=Decimal("1")),)
        )
        got = decide(portfolio=state)
        assert state_of(got, "duplicate_position") is CheckState.FAILED

    def test_a_pending_entry_on_the_same_coin_also_blocks(self) -> None:
        state = portfolio(
            pending_entries=(
                pending(reserved_notional=Decimal("100"), planned_risk_quote=Decimal("1")),
            )
        )
        assert state_of(decide(portfolio=state), "duplicate_position") is CheckState.FAILED

    def test_the_aggregate_risk_budget_rejects_when_it_is_spent(self) -> None:
        state = portfolio(
            open_positions=(
                position(
                    market=market("ETHUSDT", "ETH"),
                    notional=Decimal("100"),
                    planned_risk_quote=Decimal("200"),
                ),
            )
        )
        got = decide(portfolio=state)
        assert state_of(got, "aggregate_risk_budget") is CheckState.FAILED

    def test_a_size_below_the_exchange_minimum_is_refused_with_a_reason(self) -> None:
        got = decide(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("300"), median_30m_quote_volume=Decimal("300")
            ),
            spec=spec(min_notional=Decimal("10")),
        )
        assert got.sizing is not None
        assert got.sizing.notional == Decimal("3.000")
        assert state_of(got, "sizing") is CheckState.FAILED
        assert got.approved is False

    def test_a_size_that_rounds_to_nothing_is_refused(self) -> None:
        got = decide(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("100"), median_30m_quote_volume=Decimal("100")
            ),
            spec=spec(step_size=Decimal("1")),
        )
        assert state_of(got, "sizing") is CheckState.FAILED

    def test_no_cash_no_entry(self) -> None:
        got = decide(portfolio=portfolio(cash=Decimal("0")))
        assert got.sizing is not None
        assert got.sizing.binding_limit.name == "cash"
        assert state_of(got, "sizing") is CheckState.FAILED
        assert got.approved is False


class TestCeilingsPassAfterSizing:
    """The exposure checks pass by construction, and are recorded anyway."""

    @pytest.mark.parametrize(
        "name",
        [
            "sizing",
            "participation",
            "slippage_estimate",
            "cash",
            "exposure_after",
        ],
    )
    def test_each_post_sizing_check_passes_on_the_happy_path(self, name: str) -> None:
        assert state_of(decide(), name) is CheckState.PASSED


class TestAllChecksAreRecordedAfterTheFirstFailure:
    def test_a_blocked_kill_switch_does_not_stop_the_other_checks(self) -> None:
        got = decide(kill_switch=KillSwitchInputs(organization=KillSwitchState.EMERGENCY))
        assert tuple(check.name for check in got.checks) == ENTRY_CHECKS
        assert state_of(got, "liquidity_24h") is CheckState.PASSED
        assert state_of(got, "duplicate_position") is CheckState.PASSED

    def test_several_failures_are_all_named(self) -> None:
        got = decide(
            liquidity=liquidity(quote_volume_24h=Decimal("1"), data_quality="degraded"),
            proposal=proposal(direction=TradeDirection.SHORT),
        )
        assert set(got.rejection_reasons) >= {"modality", "data_quality", "liquidity_24h"}


class TestKillSwitchWarningActuallyReduces:
    """R-KS-1: the multiplier has to multiply, whatever the binding ceiling was."""

    @pytest.mark.parametrize(
        "over",
        [
            {},
            {"proposal": proposal(stop=Decimal("99.5"))},
            {
                "liquidity": liquidity(
                    last_minute_quote_volume=Decimal("4605.10"),
                    median_30m_quote_volume=Decimal("4605.10"),
                )
            },
            {"proposal": proposal(requested_notional=Decimal("800"))},
        ],
        ids=["risk", "tight-stop", "participation", "requested"],
    )
    def test_every_approved_size_halves_in_warning(self, over: dict[str, Any]) -> None:
        full = decide(**over)
        assert full.approved is True
        assert full.sizing is not None

        warned = decide(**over, kill_switch=KillSwitchInputs(portfolio=KillSwitchState.WARNING))
        assert warned.approved is True
        assert warned.sizing is not None
        assert warned.sizing.kill_switch_multiplier == Decimal("0.5")
        assert warned.sizing.notional < full.sizing.notional
        assert warned.sizing.binding_limit.name == full.sizing.binding_limit.name

    def test_an_automatic_warning_reduces_without_anybody_pressing_a_button(self) -> None:
        losing = portfolio(
            equity=Decimal("19800"), peak_equity=Decimal("20000"), cash=Decimal("19800")
        ).model_copy(
            update={"day_start_equity": Decimal("20000"), "daily_realized_pnl": Decimal("-200")}
        )
        got = decide(portfolio=losing)
        assert got.effective_kill_switch is KillSwitchState.WARNING
        assert got.approved is True
        assert got.sizing is not None
        assert got.sizing.kill_switch_multiplier == Decimal("0.5")


class TestBlockedNeverDisarms:
    def test_blocking_cancels_pending_entries_and_nothing_else(self) -> None:
        got = decide(kill_switch=KillSwitchInputs(portfolio=KillSwitchState.TRADING_DISABLED))
        assert got.approved is False
        assert got.cancel_pending is True
        # The decision record has no way to express "close positions": the only
        # obligation a block produces is cancelling what has not filled yet.
        assert "close" not in got.to_jsonable()

    def test_a_protective_exit_is_approved_while_entries_are_blocked(self) -> None:
        state = portfolio(open_positions=(position(),))
        got = evaluate_exit(
            exit_proposal(),
            state,
            PAPER_V1,
            KillSwitchInputs(system=KillSwitchState.TRADING_DISABLED),
        )
        assert got.approved is True
        assert got.exit_plan is not None
        assert got.exit_plan.approved_qty == Decimal("10")

    def test_a_protective_exit_is_approved_under_emergency_too(self) -> None:
        state = portfolio(open_positions=(position(),))
        got = evaluate_exit(
            exit_proposal(), state, PAPER_V1, KillSwitchInputs(portfolio=KillSwitchState.EMERGENCY)
        )
        assert got.approved is True
        assert got.effective_kill_switch is KillSwitchState.EMERGENCY

    def test_an_exit_is_approved_with_the_daily_loss_limit_breached(self) -> None:
        state = portfolio(
            equity=Decimal("19000"), peak_equity=Decimal("20000"), open_positions=(position(),)
        ).model_copy(
            update={"day_start_equity": Decimal("20000"), "daily_realized_pnl": Decimal("-1000")}
        )
        assert evaluate_exit(exit_proposal(), state, PAPER_V1, KillSwitchInputs()).approved is True

    def test_an_exit_never_sells_more_than_the_position_holds(self) -> None:
        state = portfolio(open_positions=(position(qty=Decimal("4")),))
        got = evaluate_exit(exit_proposal(qty=Decimal("10")), state, PAPER_V1, KillSwitchInputs())
        assert got.approved is True
        assert got.exit_plan is not None
        assert got.exit_plan.approved_qty == Decimal("4")
        assert got.exit_plan.clamped is True

    def test_an_exit_for_a_position_the_wallet_does_not_hold_is_a_caller_bug(self) -> None:
        with pytest.raises(ValueError, match="position"):
            evaluate_exit(exit_proposal(), portfolio(), PAPER_V1, KillSwitchInputs())

    def test_an_exit_carries_its_reason(self) -> None:
        state = portfolio(open_positions=(position(),))
        got = evaluate_exit(
            exit_proposal(reason=ExitReason.KILL_SWITCH), state, PAPER_V1, KillSwitchInputs()
        )
        assert got.exit_plan is not None
        assert got.exit_plan.reason is ExitReason.KILL_SWITCH


class TestSimultaneousProposals:
    def test_two_agents_in_the_same_market_share_one_participation_budget(self) -> None:
        thin = {
            "last_minute_quote_volume": Decimal("4605.10"),
            "median_30m_quote_volume": Decimal("4605.10"),
        }
        first = decide(liquidity=liquidity(**thin))
        assert first.sizing is not None
        assert first.sizing.notional == Decimal("46.000")

        # The caller reserves what the first proposal took, then evaluates the second.
        second = decide(
            proposal=proposal(proposal_id=uuid.UUID(int=7)),
            liquidity=liquidity(**thin, participation_used_quote=first.sizing.notional),
            portfolio=portfolio(
                pending_entries=(
                    pending(
                        market=market("ETHUSDT", "ETH"),
                        reserved_notional=first.sizing.notional,
                        planned_risk_quote=first.sizing.planned_risk_quote,
                    ),
                )
            ),
        )
        assert second.sizing is not None
        assert second.sizing.binding_limit.name == "market_participation"
        assert second.sizing.notional == Decimal("0.000")
        assert state_of(second, "sizing") is CheckState.FAILED

    def test_pending_entries_of_other_markets_still_consume_slots_and_risk(self) -> None:
        state = portfolio(
            pending_entries=(
                pending(
                    market=market("ETHUSDT", "ETH"),
                    reserved_notional=Decimal("1900"),
                    planned_risk_quote=Decimal("190"),
                ),
            )
        )
        got = decide(portfolio=state)
        assert got.sizing is not None
        assert got.sizing.binding_limit.name == "aggregate_risk"


class TestTheCeilingIsNotATarget:
    def test_the_engine_never_sizes_above_any_ceiling(self) -> None:
        cases = [
            decide(),
            decide(portfolio=portfolio(cash=Decimal("500"))),
            decide(
                liquidity=liquidity(
                    last_minute_quote_volume=Decimal("4605.10"),
                    median_30m_quote_volume=Decimal("4605.10"),
                )
            ),
            decide(kill_switch=KillSwitchInputs(portfolio=KillSwitchState.WARNING)),
            decide(proposal=proposal(requested_notional=Decimal("120"))),
        ]
        for decision in cases:
            assert decision.sizing is not None
            for cap in decision.sizing.caps:
                if cap.notional is not None:
                    assert decision.sizing.notional <= cap.notional

    def test_the_planned_stop_is_carried_and_never_promised_as_a_fill(self) -> None:
        got = decide(proposal=proposal(stop=Decimal("96")))
        assert got.sizing is not None
        assert got.sizing.stop == Decimal("96")
        # The record is a plan, not an execution: nothing here claims a fill price.
        assert "fill" not in got.to_jsonable()["sizing"]

    def test_a_worse_stop_than_planned_is_not_fabricated_by_the_engine(self) -> None:
        # Two proposals differing only in the stop produce different planned risk;
        # the engine reports what it planned, and never rewrites the stop to make
        # the planned risk equal the budget.
        tight = decide(proposal=proposal(stop=Decimal("99.5")))
        wide = decide(proposal=proposal(stop=Decimal("95")))
        assert tight.sizing is not None
        assert wide.sizing is not None
        assert tight.sizing.stop_distance_pct < wide.sizing.stop_distance_pct
        assert tight.sizing.planned_risk_pct <= PAPER_V1.risk_per_trade_pct
        assert wide.sizing.planned_risk_pct <= PAPER_V1.risk_per_trade_pct


class TestTheStateBelongsToTheProposal:
    """Astra, diff review of T3.1: nothing tied the wallet to the proposal."""

    def test_evaluating_a_proposal_against_another_wallet_is_refused(self) -> None:
        # The failure it closes: proposal of portfolio A, whose aggregate risk
        # budget is spent, is evaluated against the state of portfolio B, which
        # is empty. Every check passes on B's numbers and the approval is then
        # stamped with A's portfolio_id.
        other = portfolio().model_copy(update={"portfolio_id": uuid.UUID(int=99)})
        with pytest.raises(ValueError, match="portfolio"):
            decide(portfolio=other)

    def test_an_exit_against_another_wallet_is_refused_too(self) -> None:
        state = portfolio(open_positions=(position(),)).model_copy(
            update={"portfolio_id": uuid.UUID(int=99)}
        )
        with pytest.raises(ValueError, match="portfolio"):
            evaluate_exit(exit_proposal(), state, PAPER_V1, KillSwitchInputs())
