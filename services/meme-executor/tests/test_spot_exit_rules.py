"""T4.74-4 — the pure rules of the ``spot/1`` desk, by table: the exit order
(``emergency`` > ``sell_requested`` > ``stop`` > ``target`` > ``time``), the
slippage per attempt/reason, the backoff, the lane state (§8: 19 losing
trades are not a refutation, the 20th is; Σ pnl ≤ −0,15 at any count is; three
stops in a row cool the lane for 2 h), the post-simulation invariant of the
leg and the derived order keys."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor import exit_common, spot_send_rules
from hunter_meme_executor import spot_exit_rules as rules
from hunter_meme_executor.spot_repo import ClosedStats, spot_position_from_row

from .test_spot_repo import position_row

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)
ACTIVE, EMERGENCY = KillSwitchState.ACTIVE, KillSwitchState.EMERGENCY


def _position(**overrides: Any) -> Any:
    return spot_position_from_row({**position_row(), **overrides})


# ---- exits ----------------------------------------------------------------------------
def test_r_now_is_mark_minus_spent_over_the_r_unit() -> None:
    # spent 0,05, r_unit 0,00075: a mark of 0,04925 is exactly −1 R, 0,051125 is +1,5 R
    p = _position()
    assert rules.r_now(p, Decimal("0.04925")) == Decimal(-1)
    assert rules.r_now(p, Decimal("0.051125")) == Decimal("1.5")
    assert rules.r_now(p, None) is None
    assert rules.target_r(p.params) == Decimal("1.5")


@pytest.mark.parametrize(
    "mark,age_s,kill,auto_close,sell_requested,expected",
    [
        (Decimal("0.0505"), 60, ACTIVE, False, False, None),
        (Decimal("0.04925"), 60, ACTIVE, False, False, "stop"),
        (Decimal("0.049"), 60, ACTIVE, False, False, "stop"),
        (Decimal("0.051125"), 60, ACTIVE, False, False, "target"),
        (Decimal("0.06"), 60, ACTIVE, False, False, "target"),
        (Decimal("0.0505"), 14_400, ACTIVE, False, False, "time"),
        (Decimal("0.0505"), 14_399, ACTIVE, False, False, None),
        (None, 14_400, ACTIVE, False, False, "time"),
        (None, 60, ACTIVE, False, False, None),
        (Decimal("0.0505"), 60, ACTIVE, False, True, "sell_requested"),
        (Decimal("0.049"), 60, ACTIVE, False, True, "sell_requested"),
        (Decimal("0.049"), 20_000, EMERGENCY, True, True, "emergency"),
        (Decimal("0.049"), 60, EMERGENCY, False, False, "stop"),
        (Decimal("0.0505"), 60, EMERGENCY, False, False, None),
        (Decimal("0.0505"), 60, KillSwitchState.TRADING_DISABLED, True, False, None),
    ],
)
def test_decide_exit_in_the_design_s_order(
    mark: Decimal | None,
    age_s: int,
    kill: KillSwitchState,
    auto_close: bool,
    sell_requested: bool,
    expected: str | None,
) -> None:
    p = _position(
        entry_at=NOW - timedelta(seconds=age_s),
        sell_requested_at=NOW if sell_requested else None,
        sell_requested_by="everton" if sell_requested else None,
    )
    assert rules.decide_exit(p, mark, NOW, kill, auto_close_on_emergency=auto_close) == expected


def test_a_position_without_a_horizon_never_times_out_and_without_a_target_never_targets() -> None:
    p = _position(params={"stop_frac": "0.015"})
    assert rules.decide_exit(p, Decimal("0.06"), NOW + timedelta(days=2), ACTIVE) is None
    assert rules.decide_exit(p, Decimal("0.049"), NOW, ACTIVE) == "stop"


@pytest.mark.parametrize(
    "attempt,reason,expected",
    [
        (1, "target", 50),
        (2, "time", 50),
        (3, "target", 300),
        (6, "sell_requested", 300),
        (1, "stop", 300),
        (1, "emergency", 300),
    ],
)
def test_slippage_per_attempt_and_reason(attempt: int, reason: str, expected: int) -> None:
    assert rules.slippage_for(attempt, reason) == expected


def test_backoff_is_exit_common_s_ladder_and_the_last_step_repeats() -> None:
    assert rules.BACKOFF_S == exit_common.BACKOFF_S == (2, 4, 8, 16, 32, 60)
    assert [rules.backoff_s(n) for n in (0, 1, 2, 3, 6, 7, 99)] == [2, 2, 4, 8, 60, 60, 60]
    assert rules.MAX_EXIT_ATTEMPTS == 6


# ---- lane state (§8) ------------------------------------------------------------------
def _closed(n: int, pnl: str, r: str, stops: int = 0, last_s: int = 600) -> ClosedStats:
    return ClosedStats(
        n=n,
        sum_pnl_sol=Decimal(pnl),
        sum_r_net=Decimal(r),
        expectancy_r_net=None if n == 0 else Decimal(r) / n,
        consecutive_stops=stops,
        last_exit_at=NOW - timedelta(seconds=last_s),
    )


def _state(closed: ClosedStats, now: datetime = NOW) -> rules.LaneState:
    return rules.lane_state(
        closed,
        now=now,
        refute_min_trades=20,
        refute_max_loss_sol=Decimal("0.15"),
        consecutive_stops_pause_s=7_200,
    )


def test_nineteen_losing_trades_are_not_a_refutation_and_the_twentieth_is() -> None:
    assert _state(_closed(19, "-0.02", "-10")).state == "on"
    twentieth = _state(_closed(20, "-0.02", "-10"))
    assert (twentieth.state, twentieth.refusal) == ("refuted", "spot1_refuted")
    assert twentieth.reason is not None and twentieth.reason.startswith("n=20 expectancy_r_net=")
    assert _state(_closed(20, "-0.02", "0")).state == "refuted", "expectancy 0 R is not an edge"
    assert _state(_closed(20, "-0.02", "0.5")).state == "on"


def test_a_sum_loss_at_the_cap_refutes_at_any_count() -> None:
    assert _state(_closed(3, "-0.149999", "-3")).state == "on"
    assert _state(_closed(3, "-0.15", "-3")).state == "refuted"
    assert _state(_closed(0, "0", "0")).state == "on"


def test_three_stops_in_a_row_cool_the_lane_for_the_pause_after_the_last_exit() -> None:
    assert _state(_closed(5, "-0.003", "-3", stops=2)).state == "on"
    cooling = _state(_closed(5, "-0.003", "-3", stops=3, last_s=7_199))
    assert (cooling.state, cooling.refusal) == ("cooldown", "spot1_cooldown")
    assert cooling.cooldown_until == NOW - timedelta(seconds=7_199) + timedelta(seconds=7_200)
    assert _state(_closed(5, "-0.003", "-3", stops=3, last_s=7_200)).state == "on"


def test_refutation_is_checked_before_the_cooldown() -> None:
    assert _state(_closed(4, "-0.2", "-4", stops=4)).state == "refuted"


# ---- the leg's pure half ---------------------------------------------------------------
def test_order_keys_are_derived_from_the_signal_or_the_position_and_attempt() -> None:
    assert spot_send_rules.spot_client_order_id("sig-1", side="buy") == "spot:buy:sig-1"
    assert spot_send_rules.spot_client_order_id("sig-1", side="buy", attempt=3) == "spot:buy:sig-1"
    assert spot_send_rules.spot_client_order_id("pos-1", side="sell") == "spot:sell:pos-1:1"
    assert (
        spot_send_rules.spot_client_order_id("pos-1", side="sell", attempt=4) == "spot:sell:pos-1:4"
    )


def test_the_fee_allowance_follows_the_verified_transaction() -> None:
    assert spot_send_rules.fee_allowance_lamports(ata_creates=0, priority_fee_lamports=0) == 15_000
    two = spot_send_rules.fee_allowance_lamports(ata_creates=2, priority_fee_lamports=100_000)
    assert two == 2 * 2_039_280 + 100_000 + 5_000 + 10_000
    # the wallet's own WSOL account is opened and closed in the same transaction: no rent kept
    wrap = spot_send_rules.fee_allowance_lamports(
        ata_creates=2, priority_fee_lamports=100_000, transient_ata=1
    )
    assert wrap == 2_039_280 + 100_000 + 5_000 + 10_000
    only_wsol = spot_send_rules.fee_allowance_lamports(
        ata_creates=1, priority_fee_lamports=50, transient_ata=1
    )
    assert only_wsol == 15_050


def test_the_fill_is_read_from_the_signature_s_own_meta() -> None:
    from .spot_fakes import tx_meta
    from .spot_tx_fixtures import WALLET, WIF

    created = tx_meta(wallet_pre=500, wallet_post=440, token_pre=None, token_post=26, fee=5)
    fill = spot_send_rules.fill_from_transaction(created, wallet=WALLET, mint=WIF)
    assert fill is not None
    assert (fill.sol_delta_lamports, fill.token_delta_atoms) == (-60, 26)
    assert fill.ata_created is True and fill.network_fee_lamports == 5
    sold = tx_meta(wallet_pre=440, wallet_post=495, token_pre=26, token_post=0)
    fill = spot_send_rules.fill_from_transaction(sold, wallet=WALLET, mint=WIF)
    assert fill is not None and fill.ata_created is False
    assert (fill.sol_delta_lamports, fill.token_delta_atoms) == (55, -26)
    parsed = tx_meta(wallet_pre=500, wallet_post=440, token_pre=None, token_post=26)
    parsed["transaction"]["message"]["accountKeys"][0] = {"pubkey": WALLET, "signer": True}
    assert spot_send_rules.fill_from_transaction(parsed, wallet=WALLET, mint=WIF) is not None
    other_mint = spot_send_rules.fill_from_transaction(created, wallet=WALLET, mint="x" * 32)
    assert other_mint is not None and other_mint.token_delta_atoms == 0


def test_a_meta_that_cannot_be_trusted_is_none() -> None:
    from .spot_fakes import tx_meta
    from .spot_tx_fixtures import WALLET, WIF

    errored = tx_meta(wallet_pre=1, wallet_post=1, token_pre=None, token_post=1, err={"x": 1})
    other_payer = tx_meta(wallet_pre=1, wallet_post=1, token_pre=None, token_post=1, payer="B" * 32)
    no_balances = tx_meta(wallet_pre=1, wallet_post=1, token_pre=None, token_post=1)
    no_balances["meta"]["postBalances"] = []
    no_token_lists = tx_meta(wallet_pre=1, wallet_post=0, token_pre=None, token_post=1)
    no_token_lists["meta"]["preTokenBalances"] = None  # unreadable is not empty (Astra)
    for case in ({}, {"meta": None}, errored, other_payer, no_balances, no_token_lists):
        assert spot_send_rules.fill_from_transaction(case, wallet=WALLET, mint=WIF) is None


@pytest.mark.parametrize(
    "is_buy,sol_before,sol_after,token_before,token_after,amount,min_out,expected",
    [
        (True, 100, 60, 0, 10, 40, 10, None),
        (True, 100, 55, 0, 10, 40, 10, None),  # within the allowance of 5
        (True, 100, 54, 0, 10, 40, 10, "simulation_sol_overspent"),
        (True, 100, 60, 0, 9, 40, 10, "simulation_token_short"),
        (True, 100, 60, 5, 14, 40, 10, "simulation_token_short"),
        (False, 100, 135, 10, 0, 10, 40, None),
        (False, 100, 134, 10, 0, 10, 40, "simulation_sol_short"),
        (False, 100, 140, 10, 1, 10, 40, None),
        (False, 100, 140, 20, 9, 10, 40, "simulation_token_overspent"),
    ],
)
def test_the_simulated_invariant_by_table(
    is_buy: bool,
    sol_before: int,
    sol_after: int,
    token_before: int,
    token_after: int,
    amount: int,
    min_out: int,
    expected: str | None,
) -> None:
    got = spot_send_rules.check_simulated_leg(
        is_buy=is_buy,
        sol_before=sol_before,
        sol_after=sol_after,
        token_before=token_before,
        token_after=token_after,
        amount_atoms=amount,
        min_out=min_out,
        fee_allowance_lamports=5,
    )
    assert got == expected


def test_a_quote_for_another_pair_or_a_zero_out_is_a_mismatch() -> None:
    from .spot_tx_fixtures import OUT, TICKET, WIF, WSOL, quote

    good = quote(input_mint=WSOL, output_mint=WIF, amount=TICKET, out=OUT)
    assert spot_send_rules.quote_mismatch(good, WSOL, WIF, TICKET) is None
    assert spot_send_rules.quote_mismatch(good, WIF, WSOL, TICKET) == "quote_mismatch:input_mint"
    assert spot_send_rules.quote_mismatch(good, WSOL, WSOL, TICKET) == "quote_mismatch:output_mint"
    assert spot_send_rules.quote_mismatch(good, WSOL, WIF, TICKET + 1) == "quote_mismatch:in_amount"
    zero = replace(good, out_amount=Decimal(0), other_amount_threshold=Decimal(0))
    assert spot_send_rules.quote_mismatch(zero, WSOL, WIF, TICKET) == "quote_mismatch:out_amount"
