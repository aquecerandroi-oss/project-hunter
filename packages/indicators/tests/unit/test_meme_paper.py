"""T4.5 — the paper wallet on the curve, with every number hand-checkable.

Same tiny curve as ``test_meme_curve.py`` (30 SOL against 300 tokens, ``k =
9000``) and the same budget, 15,1875 SOL, which at 1,25 % puts exactly 15 SOL
into the curve and buys exactly 100 tokens. Priority fee 0,001 SOL per trade.
Every expected value below is written out rather than recomputed by the test, so
a change of formula fails here instead of being absorbed.

The rule this file exists to protect: **a fill is priced against reserves
observed strictly after the intent.** A wallet that filled at the last seen
price would make every concurrency-slippage number in EXP-M1 a fabrication.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.curve import CurveReserves, quote_sell
from hunter_indicators.meme.paper import (
    LedgerEvent,
    LedgerKind,
    PaperCurveWallet,
    PaperWalletLimits,
)

TINY = CurveReserves(
    virtual_sol_reserves=Decimal(30),
    virtual_token_reserves=Decimal(300),
    real_token_reserves=Decimal(200),
    initial_real_token_reserves=Decimal(240),
)
AFTER_BUY = CurveReserves(
    virtual_sol_reserves=Decimal(45),
    virtual_token_reserves=Decimal(200),
    real_token_reserves=Decimal(100),
    initial_real_token_reserves=Decimal(240),
)
T0 = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(seconds=3)
T2 = T0 + timedelta(seconds=6)
BUDGET = Decimal("15.1875")
PRIORITY = Decimal("0.001")
MINT = "5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38"

LIMITS = PaperWalletLimits(
    max_balance_sol=Decimal(20),
    max_sol_per_trade=Decimal(16),
    daily_loss_cap_sol=Decimal(5),
    max_open_positions=2,
    max_exposure_per_mint_sol=Decimal(16),
    fee_pct=Decimal("1.25"),
    fill_delay_snapshots=1,
)


def _wallet(limits: PaperWalletLimits = LIMITS, balance: Decimal = Decimal(20)) -> PaperCurveWallet:
    return PaperCurveWallet(limits=limits, balance_sol=balance, opened_at=T0)


def test_the_wallet_refuses_to_open_above_its_own_sol_cap() -> None:
    with pytest.raises(ValueError, match="max_balance_sol"):
        PaperCurveWallet(limits=LIMITS, balance_sol=Decimal(21), opened_at=T0)


def test_limits_refuse_a_fill_delay_that_would_price_at_the_last_seen_state() -> None:
    with pytest.raises(ValueError, match="fill_delay_snapshots"):
        PaperWalletLimits(
            max_balance_sol=Decimal(20),
            max_sol_per_trade=Decimal(16),
            daily_loss_cap_sol=Decimal(5),
            max_open_positions=2,
            max_exposure_per_mint_sol=Decimal(16),
            fee_pct=Decimal("1.25"),
            fill_delay_snapshots=0,
        )


def test_a_buy_is_priced_against_the_reserves_it_was_handed() -> None:
    wallet = _wallet()
    fill = wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    assert fill.accepted
    assert fill.reason is None
    assert fill.tokens == Decimal(100)
    assert fill.fee_sol == Decimal("0.1875")
    assert fill.priority_fee_sol == PRIORITY
    assert fill.sol_delta == Decimal("-15.1885")
    assert fill.balance_after == Decimal("4.8115")
    assert wallet.balance_sol == Decimal("4.8115")
    assert fill.reserves_after is not None
    assert fill.reserves_after.virtual_sol_reserves == Decimal(45)

    position = wallet.position(MINT)
    assert position is not None
    assert position.tokens == Decimal(100)
    assert position.cost_basis_sol == Decimal("15.1885")  # curve + fee + priority fee
    assert position.curve_cost_sol == Decimal(15)
    assert position.fees_sol == Decimal("0.1875")
    assert position.priority_fees_sol == PRIORITY
    assert position.entry_reserves == TINY
    assert position.entry_ts == T1


@pytest.mark.parametrize("fill_ts", [T0, T0 - timedelta(seconds=1)])
def test_a_fill_priced_at_or_before_the_intent_is_refused_by_name(fill_ts: datetime) -> None:
    wallet = _wallet()
    fill = wallet.buy(MINT, BUDGET, TINY, ts=fill_ts, intent_ts=T0, priority_fee_sol=PRIORITY)
    assert not fill.accepted
    assert fill.reason == "fill_not_after_intent"
    assert wallet.balance_sol == Decimal(20)
    assert wallet.position(MINT) is None


def test_the_named_refusals_of_a_buy() -> None:
    small = PaperWalletLimits(
        max_balance_sol=Decimal(20),
        max_sol_per_trade=Decimal(1),
        daily_loss_cap_sol=Decimal(5),
        max_open_positions=1,
        max_exposure_per_mint_sol=Decimal("0.5"),
        fee_pct=Decimal("1.25"),
        fill_delay_snapshots=1,
    )
    wallet = _wallet(small)
    assert wallet.buy(MINT, Decimal(0), TINY, ts=T1, intent_ts=T0).reason == "size_not_positive"
    assert wallet.buy(MINT, Decimal(2), TINY, ts=T1, intent_ts=T0).reason == "per_trade_cap"
    assert (
        wallet.buy(
            MINT, Decimal("0.4"), TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY
        ).reason
        is None
    )
    assert (
        wallet.buy(MINT, Decimal("0.4"), AFTER_BUY, ts=T2, intent_ts=T1).reason
        == "exposure_per_mint_cap"
    )
    assert wallet.buy("other", Decimal("0.4"), TINY, ts=T2, intent_ts=T1).reason == (
        "max_open_positions"
    )
    broke = _wallet(balance=Decimal("0.2"))
    assert broke.buy(MINT, Decimal(1), TINY, ts=T1, intent_ts=T0).reason == "balance_insufficient"


def test_buying_a_completed_curve_is_refused_by_name() -> None:
    wallet = _wallet()
    done = CurveReserves(Decimal(45), Decimal(200), real_token_reserves=Decimal(0), complete=True)
    fill = wallet.buy(MINT, Decimal(1), done, ts=T1, intent_ts=T0)
    assert fill.reason == "curve_complete"


def test_mark_to_curve_is_what_a_full_sell_would_yield_now_fees_included() -> None:
    wallet = _wallet()
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    mark = wallet.mark_to_curve(MINT, AFTER_BUY)
    assert mark == Decimal("14.8125")
    assert mark == quote_sell(AFTER_BUY, Decimal(100), LIMITS.fee_pct).net_sol
    # The honest unrealized right after entry is negative: two fees and the impact.
    assert wallet.unrealized_pnl_sol(MINT, AFTER_BUY) == Decimal("-0.376")
    assert wallet.mark_to_curve("never-held", AFTER_BUY) is None


def test_peak_mark_only_goes_up_and_is_the_trailing_reference() -> None:
    wallet = _wallet()
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    higher = CurveReserves(Decimal(90), Decimal(200), real_token_reserves=Decimal(100))
    assert wallet.record_mark(MINT, AFTER_BUY, ts=T2) == Decimal("14.8125")
    peak = wallet.record_mark(MINT, higher, ts=T2)
    assert peak is not None
    assert peak > Decimal("14.8125")
    wallet.record_mark(MINT, AFTER_BUY, ts=T2)
    position = wallet.position(MINT)
    assert position is not None
    assert position.peak_mark_sol == peak


def test_realized_pnl_of_a_round_trip_is_the_two_fees_and_the_two_priority_fees() -> None:
    wallet = _wallet()
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    sell = wallet.sell(
        MINT, Decimal(100), AFTER_BUY, ts=T2, intent_ts=T1, priority_fee_sol=PRIORITY
    )
    assert sell.accepted
    assert sell.sol_delta == Decimal("14.8115")  # 14,8125 net minus the priority fee
    assert wallet.position(MINT) is None
    assert wallet.realized_pnl_sol == Decimal("-0.377")
    assert wallet.realized_pnl_sol == Decimal("-0.375") - 2 * PRIORITY
    assert wallet.balance_sol == Decimal(20) + wallet.realized_pnl_sol
    assert wallet.realized_pnl_by_day == {"2026-09-12": Decimal("-0.377")}


def test_a_partial_sell_splits_the_cost_basis_proportionally() -> None:
    wallet = _wallet()
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    sell = wallet.sell(MINT, Decimal(50), AFTER_BUY, ts=T2, intent_ts=T1, priority_fee_sol=PRIORITY)
    assert sell.accepted
    assert sell.fee_sol == Decimal("0.1125")
    assert sell.sol_delta == Decimal("8.8865")  # 9 gross - 0,1125 fee - 0,001 priority
    position = wallet.position(MINT)
    assert position is not None
    assert position.tokens == Decimal(50)
    assert position.cost_basis_sol == Decimal("7.59425")
    assert wallet.realized_pnl_sol == Decimal("1.29225")


def test_selling_what_the_wallet_does_not_hold_is_refused_by_name() -> None:
    wallet = _wallet()
    assert wallet.sell(MINT, Decimal(1), AFTER_BUY, ts=T1, intent_ts=T0).reason == "no_position"
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    assert (
        wallet.sell(MINT, Decimal(101), AFTER_BUY, ts=T2, intent_ts=T1).reason
        == "tokens_exceed_position"
    )
    assert wallet.sell(MINT, Decimal(0), AFTER_BUY, ts=T2, intent_ts=T1).reason == (
        "size_not_positive"
    )
    assert (
        wallet.sell(MINT, Decimal(50), AFTER_BUY, ts=T1, intent_ts=T1).reason
        == "fill_not_after_intent"
    )


def test_the_daily_loss_cap_latches_and_only_an_explicit_resume_clears_it() -> None:
    limits = PaperWalletLimits(
        max_balance_sol=Decimal(20),
        max_sol_per_trade=Decimal(16),
        daily_loss_cap_sol=Decimal("0.3"),
        max_open_positions=2,
        max_exposure_per_mint_sol=Decimal(16),
        fee_pct=Decimal("1.25"),
        fill_delay_snapshots=1,
    )
    wallet = _wallet(limits)
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    wallet.sell(MINT, Decimal(100), AFTER_BUY, ts=T2, intent_ts=T1, priority_fee_sol=PRIORITY)
    assert wallet.halted_reason == "daily_loss_cap_latched"
    blocked = wallet.buy(MINT, Decimal(1), TINY, ts=T2, intent_ts=T1)
    assert blocked.reason == "daily_loss_cap_latched"
    wallet.resume(ts=T2, note="OWNER cleared it in the test")
    assert wallet.halted_reason is None
    assert wallet.buy(MINT, Decimal(1), TINY, ts=T2, intent_ts=T1).accepted


def test_the_ledger_records_every_event_including_refusals_in_order() -> None:
    wallet = _wallet()
    wallet.buy(MINT, Decimal(0), TINY, ts=T1, intent_ts=T0)
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    wallet.sell(MINT, Decimal(100), AFTER_BUY, ts=T2, intent_ts=T1, priority_fee_sol=PRIORITY)
    kinds = [event.kind for event in wallet.ledger]
    assert kinds == [LedgerKind.OPEN, LedgerKind.REFUSED, LedgerKind.BUY, LedgerKind.SELL]
    assert [event.seq for event in wallet.ledger] == [0, 1, 2, 3]
    assert wallet.ledger[1].reason == "size_not_positive"
    assert wallet.ledger[-1].balance_after == wallet.balance_sol
    assert isinstance(wallet.ledger, tuple)


def test_two_wallets_fed_the_same_inputs_produce_the_same_ledger() -> None:
    """No clock, no randomness, no IO: same inputs, same bytes."""
    ledgers: list[tuple[LedgerEvent, ...]] = []
    for _ in range(2):
        wallet = _wallet()
        wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
        wallet.sell(MINT, Decimal(100), AFTER_BUY, ts=T2, intent_ts=T1, priority_fee_sol=PRIORITY)
        ledgers.append(wallet.ledger)
    assert ledgers[0] == ledgers[1]


def test_equity_is_the_balance_plus_every_honest_mark_and_names_what_it_cannot_price() -> None:
    """``docs/RISK_ENGINE_MEME.md`` §10.6, as an assertion instead of a sentence."""
    wallet = _wallet()
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    equity = wallet.equity({MINT: AFTER_BUY})
    assert equity.balance_sol == Decimal("4.8115")
    assert equity.marked_sol == Decimal("14.8125")
    assert equity.total_sol == Decimal("19.624")
    assert equity.unpriced_mints == ()
    # A position whose reserves nobody supplied is named, never valued at zero.
    blind = wallet.equity({})
    assert blind.total_sol == Decimal("4.8115")
    assert blind.unpriced_mints == (MINT,)
    assert blind.total_sol != equity.total_sol


def test_equity_equals_the_opening_balance_minus_the_round_trip_cost() -> None:
    wallet = _wallet()
    wallet.buy(MINT, BUDGET, TINY, ts=T1, intent_ts=T0, priority_fee_sol=PRIORITY)
    before = wallet.equity({MINT: AFTER_BUY}).total_sol
    wallet.sell(MINT, Decimal(100), AFTER_BUY, ts=T2, intent_ts=T1, priority_fee_sol=PRIORITY)
    after = wallet.equity({}).total_sol
    assert before == Decimal(20) - Decimal("0.376")  # two fees and one priority fee so far
    assert after == Decimal(20) - Decimal("0.377")  # the second priority fee on the way out
    assert after == wallet.balance_sol


def test_a_naive_timestamp_is_a_programming_error_not_a_market_refusal() -> None:
    wallet = _wallet()
    with pytest.raises(ValueError, match="UTC"):
        wallet.buy(MINT, BUDGET, TINY, ts=datetime(2026, 9, 12, 4, 0, 3), intent_ts=T0)  # noqa: DTZ001
