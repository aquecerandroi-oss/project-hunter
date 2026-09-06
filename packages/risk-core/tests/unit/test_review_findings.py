"""The adversarial review of T3.2 (`bf4924b`), transcribed as a table of cases.

Every test here is one finding of `.claude/state/review-T3.2-risk-core.md`, with
the numbers the reviewer reproduced. They are kept in one file on purpose: each
one failed before the fix and passes after it, so the file is the evidence that
the finding is closed and the regression that keeps it closed.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.decision import CheckState, RiskDecision
from hunter_risk.evaluate import evaluate, evaluate_exit
from hunter_risk.kill_switch import (
    KillSwitchInputs,
    ResumeAuthorization,
    assess,
    resume,
)
from hunter_risk.limits import PAPER_V1

from .factories import (
    COSTS,
    NOW,
    beta,
    deep_book,
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

PORTFOLIO_ID = uuid.UUID("00000000-0000-7000-8000-0000000000aa")


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


def cap_of(decision: RiskDecision, name: str) -> Any:
    assert decision.sizing is not None
    return next(cap for cap in decision.sizing.caps if cap.name == name)


def market_at(price: str, **over: Any) -> Any:
    """A coherent market picture at one price: quote, book and mid all agree."""
    value = Decimal(price)
    return liquidity(
        last_price=value,
        mid_price=value,
        best_bid=value - Decimal("0.001"),
        best_ask=value + Decimal("0.001"),
        asks=deep_book(value),
        **over,
    )


class TestFinding1DailyLossComesFromTheEquity:
    """`exposure.py:104-149` - the day's loss was read from optional PnL fields.

    Reviewer's scenario: the day opened at 20.000, the wallet is at 19.500
    (-2,5 %), the peak is 20.000 and the PnL fields were never filled. The old
    code answered `daily_loss PASSED value=0`, the kill switch stayed ACTIVE and
    a full-size entry (1.805,5) was approved with the blocking threshold of 2 %
    already breached.
    """

    def _opened_at_20000_now_19500(self) -> Any:
        return portfolio(
            equity=Decimal("19500"),
            peak_equity=Decimal("20000"),
            cash=Decimal("19500"),
            day_start_equity=Decimal("20000"),
        )

    def test_a_day_down_two_and_a_half_percent_blocks_even_with_no_pnl_fields(self) -> None:
        state = self._opened_at_20000_now_19500()
        assert state.daily_loss_pct == Decimal("0.025")

        got = decide(portfolio=state)
        assert state_of(got, "daily_loss") is CheckState.FAILED
        assert state_of(got, "kill_switch") is CheckState.FAILED
        assert got.effective_kill_switch is KillSwitchState.TRADING_DISABLED
        assert got.approved is False

    def test_the_assessment_reads_the_same_loss_the_check_does(self) -> None:
        got = assess(self._opened_at_20000_now_19500(), PAPER_V1, KillSwitchInputs())
        assert got.daily_loss_pct == Decimal("0.025")
        assert got.automatic is KillSwitchState.TRADING_DISABLED
        assert got.trigger == "daily_loss"

    def test_a_decomposition_that_disagrees_with_the_equity_is_measured_not_obeyed(self) -> None:
        # 19.500 against an opening of 20.000 is -500; a caller claiming -100 is
        # describing a wallet that does not exist. The gap is published, the
        # loss still comes from the equity, and the state still builds - a state
        # that refused to exist would take the protective exit down with it
        # (Astra, review of this diff).
        state = portfolio(
            equity=Decimal("19500"),
            peak_equity=Decimal("20000"),
            cash=Decimal("19500"),
            day_start_equity=Decimal("20000"),
            daily_realized_pnl=Decimal("-100"),
            daily_unrealized_pnl=Decimal("0"),
            daily_costs=Decimal("0"),
        )
        assert state.daily_decomposition_gap == Decimal("400")
        assert state.daily_loss_pct == Decimal("0.025")
        assert state_of(decide(portfolio=state), "daily_loss") is CheckState.FAILED

    def test_a_wallet_whose_ledger_disagrees_can_still_be_protected(self) -> None:
        state = portfolio(
            equity=Decimal("19500"),
            peak_equity=Decimal("20000"),
            cash=Decimal("19500"),
            day_start_equity=Decimal("20000"),
            daily_realized_pnl=Decimal("-100"),
            daily_unrealized_pnl=Decimal("0"),
            daily_costs=Decimal("0"),
            open_positions=(position(),),
        )
        got = evaluate_exit(
            exit_proposal(), position(), PAPER_V1, KillSwitchInputs(), portfolio=state
        )
        assert got.approved is True

    def test_a_decomposition_that_agrees_with_the_equity_is_accepted(self) -> None:
        state = portfolio(
            equity=Decimal("19500"),
            peak_equity=Decimal("20000"),
            cash=Decimal("19500"),
            day_start_equity=Decimal("20000"),
            daily_realized_pnl=Decimal("-450"),
            daily_unrealized_pnl=Decimal("-30"),
            daily_costs=Decimal("20"),
        )
        assert state.daily_pnl == Decimal("-500")
        assert state.daily_loss_pct == Decimal("0.025")


class TestFinding2TheEntryReferenceIsConfrontedWithTheMarket:
    """`inputs.py:92` + `sizing.py:250-251` - `last_price` was never read.

    Reviewer's scenario: `entry_ref=100`, stop 97,5, market at 110. The old code
    approved it, recorded a notional of 1.851,80 while the real spend was
    2.036,98, and the real loss at the stop was 235,55 = 1,18 % of the equity -
    against a ceiling of 0,25 %.
    """

    def test_an_entry_reference_ten_percent_under_the_market_is_refused(self) -> None:
        got = decide(liquidity=market_at("110"))
        assert state_of(got, "signal_validity") is CheckState.FAILED
        assert got.approved is False

    def test_the_refused_reference_is_never_sized_at_the_stale_price(self) -> None:
        got = decide(liquidity=market_at("110"))
        assert got.sizing is not None
        # The size, if the panel shows one, is priced at the worse of the two:
        # 1,18 % of planned risk can never be reported as 0,25 %.
        assert got.sizing.sizing_price == Decimal("110")
        assert got.sizing.planned_risk_pct <= PAPER_V1.risk_per_trade_pct

    def test_a_long_whose_stop_sits_above_the_market_is_refused(self) -> None:
        # entry_ref 100, stop 97,5, market 90: the stop is already breached and
        # the old engine approved the entry anyway.
        got = decide(liquidity=market_at("90"))
        assert state_of(got, "signal_validity") is CheckState.FAILED
        assert got.approved is False

    def test_a_reference_inside_the_half_percent_band_is_accepted(self) -> None:
        got = decide(liquidity=market_at("100.4"))
        assert state_of(got, "signal_validity") is CheckState.PASSED
        assert got.approved is True

    def test_inside_the_band_the_sizing_still_uses_the_worse_price(self) -> None:
        got = decide(liquidity=market_at("100.4"))
        assert got.sizing is not None
        assert got.sizing.sizing_price == Decimal("100.4")
        # A stale, cheaper reference must never buy more units than the market
        # would actually sell.
        at_par = decide(liquidity=market_at("100"))
        assert at_par.sizing is not None
        assert got.sizing.qty <= at_par.sizing.qty

    def test_a_reference_just_outside_the_band_is_refused(self) -> None:
        got = decide(liquidity=market_at("100.6"))
        assert state_of(got, "signal_validity") is CheckState.FAILED
        assert got.approved is False

    def test_the_band_bites_on_the_cheap_side_too(self) -> None:
        # The market fell away from the reference: 100 against 99,4 is 0,60 % of
        # the observed price. The sizing then keeps the reference, which is the
        # worse price - the ceiling never widens because the market dipped.
        got = decide(liquidity=market_at("99.4"))
        assert state_of(got, "signal_validity") is CheckState.FAILED
        assert got.sizing is not None
        assert got.sizing.sizing_price == Decimal("100")
        assert got.approved is False

    def test_the_edge_of_the_band_is_inside_it(self) -> None:
        # 100 against 100,5 is 0,4975 % of the observed price: inside ±0,5 %.
        got = decide(liquidity=market_at("100.5"))
        assert state_of(got, "signal_validity") is CheckState.PASSED
        assert got.approved is True


class TestFinding3TheVolumeSnapshotHasAMaximumAge:
    """`limits.py:81` - `max_volume_age_s` (120 s) existed and was never used.

    Reviewer's scenario: the minute volume is a photograph from 45 minutes ago,
    participation is computed against it, and the proposal is approved.
    """

    def test_a_volume_snapshot_from_45_minutes_ago_rejects(self) -> None:
        stale = liquidity(volume_ts=NOW - timedelta(minutes=45))
        got = decide(liquidity=stale)
        assert state_of(got, "liquidity_24h") is CheckState.UNAVAILABLE
        assert state_of(got, "participation") is CheckState.UNAVAILABLE
        assert got.approved is False
        assert got.sizing is None

    def test_a_volume_without_a_timestamp_rejects(self) -> None:
        got = decide(liquidity=liquidity(volume_ts=None))
        assert state_of(got, "liquidity_24h") is CheckState.UNAVAILABLE
        assert got.approved is False

    def test_a_volume_inside_the_declared_age_passes(self) -> None:
        got = decide(liquidity=liquidity(volume_ts=NOW - timedelta(seconds=119)))
        assert state_of(got, "liquidity_24h") is CheckState.PASSED
        assert state_of(got, "participation") is CheckState.PASSED
        assert got.approved is True


class TestFinding4CashIsNetOfPendingReservations:
    """`exposure.py:98` - cash was the only limit that ignored the reservations.

    Reviewer's scenario: 500 of cash, 400 already reserved by a pending entry,
    and the engine approved another 499,5 - 900 committed against 500.
    """

    def _wallet(self) -> Any:
        return portfolio(
            cash=Decimal("500"),
            pending_entries=(
                pending(
                    market=market("ETHUSDT", "ETH"),
                    reserved_notional=Decimal("400"),
                    planned_risk_quote=Decimal("0"),
                ),
            ),
        )

    def test_the_pending_reservation_is_subtracted_from_the_cash_ceiling(self) -> None:
        state = self._wallet()
        assert state.available_cash == Decimal("99.599904")

        got = decide(portfolio=state)
        assert got.sizing is not None
        assert got.sizing.binding_constraint == "cash"
        # The old engine sized 499,5 here: 400 + 499,5 = 899,5 against 500.
        assert got.sizing.notional < Decimal("100")
        assert got.sizing.notional + Decimal("400") < Decimal("500")

    def test_the_cash_ceiling_publishes_the_cash_not_the_leverage(self) -> None:
        """Finding 7: the ceiling used to publish `limit=max_leverage` (1)."""
        cap = cap_of(decide(portfolio=self._wallet()), "cash")
        assert cap.limit == Decimal("99.599904")

    def test_a_zero_cost_candidate_cannot_shrink_somebody_else_reservation(self) -> None:
        # Astra, review of this diff: the hold belongs to the reservation, not to
        # the next candidate's cost hypothesis. With costs declared at zero the
        # 400,400096 already held stays held, and 500 stays the hard limit.
        free = COSTS.model_copy(
            update={
                "spread_bps": Decimal("0"),
                "slippage_bps": Decimal("0"),
                "fee_bps": Decimal("0"),
            }
        )
        got = decide(portfolio=self._wallet(), proposal=proposal(assumed_costs=free))
        assert got.sizing is not None
        assert got.sizing.binding_constraint == "cash"
        assert got.sizing.notional <= Decimal("99.599904")
        assert got.sizing.notional + Decimal("400.400096") <= Decimal("500")

    def test_a_reservation_larger_than_the_cash_leaves_nothing_to_size(self) -> None:
        state = portfolio(
            cash=Decimal("300"),
            pending_entries=(
                pending(
                    market=market("ETHUSDT", "ETH"),
                    reserved_notional=Decimal("400"),
                    planned_risk_quote=Decimal("0"),
                ),
            ),
        )
        got = decide(portfolio=state)
        assert got.sizing is not None
        assert got.sizing.notional == Decimal("0")
        assert state_of(got, "sizing") is CheckState.FAILED
        assert got.approved is False


class TestFinding5ResumeUsesTheAssessment:
    """`kill_switch.py:169-194` - `assessment` was a dead parameter.

    An unlock granted while the automatic triggers still bite changes nothing:
    the next `assess` blocks again. Refusing it keeps the audit trail honest.
    T3.6 owns the persisted latch and the transition record.
    """

    def _still_losing(self) -> Any:
        return portfolio(
            equity=Decimal("19500"),
            peak_equity=Decimal("20000"),
            cash=Decimal("19500"),
            day_start_equity=Decimal("20000"),
        )

    def _authorization(self) -> ResumeAuthorization:
        return ResumeAuthorization(
            authorized_by="everton",
            portfolio_id=PORTFOLIO_ID,
            from_state=KillSwitchState.TRADING_DISABLED,
            to_state=KillSwitchState.ACTIVE,
            reason="revisado manualmente",
        )

    def test_resume_is_refused_while_the_automatic_trigger_still_bites(self) -> None:
        assessment = assess(self._still_losing(), PAPER_V1, KillSwitchInputs())
        with pytest.raises(ValueError, match="automatic|automatico|gatilho"):
            resume(
                KillSwitchState.TRADING_DISABLED,
                self._authorization(),
                assessment,
                PORTFOLIO_ID,
            )

    def test_resume_is_granted_once_the_trigger_stopped_biting(self) -> None:
        recovered = portfolio(equity=Decimal("20000"), peak_equity=Decimal("20000"))
        assessment = assess(recovered, PAPER_V1, KillSwitchInputs())
        got = resume(
            KillSwitchState.TRADING_DISABLED, self._authorization(), assessment, PORTFOLIO_ID
        )
        assert got is KillSwitchState.ACTIVE


class TestFinding6TiedCeilingsNameAStableWinner:
    """`sizing.py:262-268` - `tied_limits` was correct and untested.

    The caller asks for exactly the participation ceiling: 1 % of a reference of
    100.000 is 1.000, and `requested_notional` is 1.000 too.
    """

    def _tied(self) -> RiskDecision:
        return decide(
            proposal=proposal(requested_notional=Decimal("1000")),
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("100000"),
                median_30m_quote_volume=Decimal("100000"),
            ),
        )

    def test_the_earlier_ceiling_in_the_declared_order_wins_the_tie(self) -> None:
        got = self._tied()
        assert got.sizing is not None
        assert cap_of(got, "requested").notional == Decimal("1000")
        assert cap_of(got, "market_participation").notional == Decimal("1000")
        assert got.sizing.binding_constraint == "requested"
        assert got.sizing.tied_limits == ("market_participation",)

    def test_the_tie_break_is_stable_across_runs(self) -> None:
        assert self._tied().to_jsonable() == self._tied().to_jsonable()


class TestTheWorsePriceCanAlsoAdmitAProposal:
    """Astra, review of this diff: the worse price is not only conservative.

    The claim "the engine never gets more permissive" is true of the **size**,
    not of the stop geometry - and saying so is cheaper than discovering it in
    production. With the reference at 100, a stop at 99,8 and the market at
    100,2, the stop really is 0,3992 % away from the price the order will meet,
    so the minimum distance of 0,3 % is met. It is the same measurement the
    sizing uses, which is the point: one price, one geometry.
    """

    def test_a_stop_too_close_to_the_reference_can_be_far_enough_from_the_market(self) -> None:
        near = proposal(stop=Decimal("99.8"))
        at_par = decide(proposal=near)
        assert state_of(at_par, "stop_distance") is CheckState.FAILED

        against_the_market = decide(proposal=near, liquidity=market_at("100.2"))
        assert state_of(against_the_market, "stop_distance") is CheckState.PASSED
        assert against_the_market.sizing is not None
        assert against_the_market.sizing.sizing_price == Decimal("100.2")
        assert against_the_market.sizing.stop_distance_pct > PAPER_V1.min_stop_distance_pct


class TestFinding8UnavailableStatesAreExercised:
    """`checks.py:118-120,193-195` - two `unavailable` branches had no test."""

    def test_a_book_without_bid_and_ask_makes_the_spread_unmeasurable(self) -> None:
        got = decide(liquidity=liquidity(best_bid=None, best_ask=None, mid_price=None))
        assert state_of(got, "spread") is CheckState.UNAVAILABLE
        assert got.approved is False

    def test_an_invalid_stop_geometry_makes_the_distance_unmeasurable(self) -> None:
        got = decide(proposal=proposal(stop=Decimal("101")))
        assert state_of(got, "stop_distance") is CheckState.UNAVAILABLE
        assert got.approved is False
