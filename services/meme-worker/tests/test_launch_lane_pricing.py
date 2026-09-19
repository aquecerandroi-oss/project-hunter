"""``launch_lane_pricing`` — the entry price, the born-full guard and the
three pre-registered exits (T4.67a), folded over the same
``MintEventState`` the event gate already uses. Pure, no Docker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_indicators.meme.curve import (
    INITIAL_REAL_TOKEN_RESERVES,
    INITIAL_VIRTUAL_SOL_RESERVES,
    INITIAL_VIRTUAL_TOKEN_RESERVES,
    marginal_price_sol,
)
from hunter_meme_worker.event_state import CurvePoint, MintEventState
from hunter_meme_worker.features_tape import TapeTrade
from hunter_meme_worker.launch_lane_pricing import (
    EXIT_FIRST_THIRD_PARTY_SELL,
    EXIT_MAX_DRAWDOWN_FROM_PEAK,
    EXIT_TIME_STOP,
    born_full,
    entry_point,
    exit_trigger,
    standard_reserves,
)

CREATED_AT = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
MINT = "4k3Dyjzvzp8eYnbNBGVfL5V1Z6VpAmoEsFmPtnxJhMKZ"
CREATOR = "CreatorWa11etAddress1111111111111111111111"
BUYER = "ThirdPartyBuyerAddress111111111111111111111"


def _trade(
    *, at: datetime, side: str, trader: str, real_sol: Decimal, real_token: Decimal
) -> NormalizedCurveTrade:
    return NormalizedCurveTrade(
        mint=MINT,
        slot=1,
        signature=f"sig-{at.timestamp()}-{trader}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(1_000_000),
        virtual_sol_reserves=Decimal(31),
        virtual_token_reserves=Decimal(1_000_000_000),
        real_sol_reserves=real_sol,
        real_token_reserves=real_token,
        creator=CREATOR,
        mayhem=False,
        block_time=at,
        received_at=at,
    )


def _state() -> MintEventState:
    return MintEventState(mint=MINT, subscribed_at=CREATED_AT, first_seen_at=CREATED_AT)


def test_entry_point_is_the_first_point_after_the_one_second_delay() -> None:
    state = _state()
    state.apply_trade(
        _trade(
            at=CREATED_AT + timedelta(milliseconds=500),
            side="buy",
            trader=CREATOR,
            real_sol=Decimal(2),
            real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(1000),
        )
    )
    state.apply_trade(
        _trade(
            at=CREATED_AT + timedelta(seconds=1, milliseconds=200),
            side="buy",
            trader=BUYER,
            real_sol=Decimal(3),
            real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(2000),
        )
    )
    point = entry_point(
        state, created_at=CREATED_AT, entry_delay_s=1, as_of=CREATED_AT + timedelta(seconds=2)
    )
    assert point is not None
    assert point.real_sol == Decimal(3)


def test_entry_point_is_none_before_the_delay_has_a_point() -> None:
    state = _state()
    state.apply_trade(
        _trade(
            at=CREATED_AT + timedelta(milliseconds=200),
            side="buy",
            trader=CREATOR,
            real_sol=Decimal(2),
            real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(1000),
        )
    )
    assert (
        entry_point(
            state, created_at=CREATED_AT, entry_delay_s=1, as_of=CREATED_AT + timedelta(seconds=2)
        )
        is None
    )


def test_entry_point_never_anticipates_a_point_not_yet_received() -> None:
    state = _state()
    late = _trade(
        at=CREATED_AT + timedelta(seconds=1, milliseconds=100),
        side="buy",
        trader=BUYER,
        real_sol=Decimal(3),
        real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(2000),
    )
    state.apply_trade(late)
    assert (
        entry_point(
            state,
            created_at=CREATED_AT,
            entry_delay_s=1,
            as_of=CREATED_AT + timedelta(milliseconds=900),
        )
        is None
    )


def test_born_full_is_true_within_the_window_at_the_threshold() -> None:
    state = _state()
    state.apply_trade(
        _trade(
            at=CREATED_AT + timedelta(milliseconds=500),
            side="buy",
            trader=BUYER,
            real_sol=Decimal(50),
            real_token=INITIAL_REAL_TOKEN_RESERVES * Decimal("0.05"),
        )
    )
    assert (
        born_full(
            state,
            created_at=CREATED_AT,
            initial_real_token_reserves=INITIAL_REAL_TOKEN_RESERVES,
            window_s=2,
            threshold_pct=90,
            as_of=CREATED_AT + timedelta(seconds=2),
        )
        is True
    )


def test_born_full_is_false_outside_the_window() -> None:
    state = _state()
    state.apply_trade(
        _trade(
            at=CREATED_AT + timedelta(seconds=5),
            side="buy",
            trader=BUYER,
            real_sol=Decimal(50),
            real_token=INITIAL_REAL_TOKEN_RESERVES * Decimal("0.01"),
        )
    )
    assert (
        born_full(
            state,
            created_at=CREATED_AT,
            initial_real_token_reserves=INITIAL_REAL_TOKEN_RESERVES,
            window_s=2,
            threshold_pct=90,
            as_of=CREATED_AT + timedelta(seconds=5),
        )
        is False
    )


def test_born_full_is_false_without_a_denominator() -> None:
    state = _state()
    assert (
        born_full(
            state,
            created_at=CREATED_AT,
            initial_real_token_reserves=None,
            window_s=2,
            threshold_pct=90,
            as_of=CREATED_AT,
        )
        is False
    )


def _entered_state() -> MintEventState:
    state = _state()
    state.apply_trade(
        _trade(
            at=CREATED_AT + timedelta(seconds=1),
            side="buy",
            trader=CREATOR,
            real_sol=Decimal(2),
            real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(1000),
        )
    )
    return state


def test_exit_fires_on_the_time_stop() -> None:
    state = _entered_state()
    entered_at = CREATED_AT + timedelta(seconds=1)
    decision = exit_trigger(
        state,
        entered_at=entered_at,
        time_stop_s=6,
        exit_on_first_third_party_sell=True,
        max_drawdown_from_peak_pct=Decimal(20),
        creation_buyers={CREATOR},
        latest_trade=None,
        as_of=entered_at + timedelta(seconds=6),
    )
    assert decision is not None
    assert decision.reason == EXIT_TIME_STOP


def test_no_exit_before_any_trigger() -> None:
    state = _entered_state()
    entered_at = CREATED_AT + timedelta(seconds=1)
    assert (
        exit_trigger(
            state,
            entered_at=entered_at,
            time_stop_s=6,
            exit_on_first_third_party_sell=True,
            max_drawdown_from_peak_pct=Decimal(20),
            creation_buyers={CREATOR},
            latest_trade=None,
            as_of=entered_at + timedelta(seconds=2),
        )
        is None
    )


def test_exit_fires_on_the_first_third_party_sell() -> None:
    state = _entered_state()
    entered_at = CREATED_AT + timedelta(seconds=1)
    sell_at = entered_at + timedelta(seconds=2)
    trade = _trade(
        at=sell_at,
        side="sell",
        trader=BUYER,
        real_sol=Decimal(1),
        real_token=INITIAL_REAL_TOKEN_RESERVES,
    )
    state.apply_trade(trade)
    tape_trade = TapeTrade(
        block_time=sell_at, received_at=sell_at, trader=BUYER, side="sell", sol_lamports=1_000_000
    )
    decision = exit_trigger(
        state,
        entered_at=entered_at,
        time_stop_s=6,
        exit_on_first_third_party_sell=True,
        max_drawdown_from_peak_pct=Decimal(20),
        creation_buyers={CREATOR},
        latest_trade=tape_trade,
        as_of=sell_at,
    )
    assert decision is not None
    assert decision.reason == EXIT_FIRST_THIRD_PARTY_SELL


def test_a_sell_by_a_creation_block_buyer_is_not_a_third_party_exit() -> None:
    state = _entered_state()
    entered_at = CREATED_AT + timedelta(seconds=1)
    sell_at = entered_at + timedelta(seconds=1)
    state.apply_trade(
        _trade(
            at=sell_at,
            side="sell",
            trader=CREATOR,
            real_sol=Decimal("1.9"),
            real_token=INITIAL_REAL_TOKEN_RESERVES,
        )
    )
    tape_trade = TapeTrade(
        block_time=sell_at, received_at=sell_at, trader=CREATOR, side="sell", sol_lamports=1_000_000
    )
    assert (
        exit_trigger(
            state,
            entered_at=entered_at,
            time_stop_s=6,
            exit_on_first_third_party_sell=True,
            max_drawdown_from_peak_pct=Decimal(20),
            creation_buyers={CREATOR},
            latest_trade=tape_trade,
            as_of=sell_at,
        )
        is None
    )


def test_exit_fires_on_the_drawdown_from_peak() -> None:
    state = _entered_state()
    entered_at = CREATED_AT + timedelta(seconds=1)
    peak_at = entered_at + timedelta(seconds=1)
    state.apply_trade(
        _trade(
            at=peak_at,
            side="buy",
            trader=BUYER,
            real_sol=Decimal(20),
            real_token=INITIAL_REAL_TOKEN_RESERVES,
        )
    )
    fall_at = peak_at + timedelta(seconds=1)
    state.apply_trade(
        _trade(
            at=fall_at,
            side="sell",
            trader=BUYER,
            real_sol=Decimal(15),
            real_token=INITIAL_REAL_TOKEN_RESERVES,
        )
    )
    decision = exit_trigger(
        state,
        entered_at=entered_at,
        time_stop_s=6,
        exit_on_first_third_party_sell=False,
        max_drawdown_from_peak_pct=Decimal(20),
        creation_buyers={CREATOR},
        latest_trade=None,
        as_of=fall_at,
    )
    assert decision is not None
    assert decision.reason == EXIT_MAX_DRAWDOWN_FROM_PEAK


def test_standard_reserves_at_genesis_matches_the_documented_constants() -> None:
    point = CurvePoint(
        observed_at=CREATED_AT,
        received_at=CREATED_AT,
        mcap_sol=None,
        real_sol=Decimal(0),
        real_token=INITIAL_REAL_TOKEN_RESERVES,
        mayhem=False,
    )
    reserves = standard_reserves(point)
    assert reserves.virtual_sol_reserves == INITIAL_VIRTUAL_SOL_RESERVES
    assert reserves.virtual_token_reserves == INITIAL_VIRTUAL_TOKEN_RESERVES


def test_standard_reserves_preserves_the_constant_product_after_a_buy() -> None:
    k = INITIAL_VIRTUAL_SOL_RESERVES * INITIAL_VIRTUAL_TOKEN_RESERVES
    after_buy = CurvePoint(
        observed_at=CREATED_AT,
        received_at=CREATED_AT,
        mcap_sol=None,
        real_sol=Decimal(5),
        real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(10_000_000),
        mayhem=False,
    )
    reserves = standard_reserves(after_buy)
    assert reserves.virtual_sol_reserves * reserves.virtual_token_reserves == k
    assert (
        marginal_price_sol(reserves) > INITIAL_VIRTUAL_SOL_RESERVES / INITIAL_VIRTUAL_TOKEN_RESERVES
    )
