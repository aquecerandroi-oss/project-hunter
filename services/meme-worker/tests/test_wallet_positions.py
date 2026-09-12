"""T4.12 — the observed wallet's position, FIFO, pure: lots consumed oldest
first, the realized PnL of the matched part, a sell with no lot behind it
left unmatched, the mark by the newer of snapshot and tape (a done curve is
not a price), R over the SOL spent. No database, no clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.curve import CurveReserves, quote_sell
from hunter_meme_worker.wallet_positions import (
    DEFAULT_FEE_PCT,
    Fill,
    SnapshotPoint,
    TapePoint,
    fee_pct_from_raw,
    fold_position,
    mark_of,
    unrealized_and_r,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)
SOL = 10**9


def _fill(minute: int, side: str, sol: int, fee: int, tokens: str, index: int = 0) -> Fill:
    return Fill(
        at=T0 + timedelta(minutes=minute),
        slot=1000 + minute,
        event_index=index,
        side=side,
        sol_lamports=sol,
        fee_lamports=fee,
        token_amount=Decimal(tokens),
    )


BUY_1 = _fill(0, "buy", 990_000_000, 10_000_000, "10")  # 10 tokens for 1 SOL all-in
BUY_2 = _fill(1, "buy", 1_980_000_000, 20_000_000, "10")  # 10 tokens for 2 SOL all-in
SELL_15 = _fill(2, "sell", 4_600_000_000, 100_000_000, "15")  # nets 4.5 SOL


def test_fifo_realizes_against_the_oldest_lots_first() -> None:
    position = fold_position([SELL_15, BUY_2, BUY_1])  # order of arrival is irrelevant
    assert (position.buys, position.sells, position.status) == (2, 1, "open")
    assert position.sol_spent == Decimal(3) and position.sol_received == Decimal("4.5")
    assert position.tokens_held == Decimal(5)
    # lot 1 (10 @ 1 SOL) fully, half of lot 2 (5 @ 1 SOL): cost 2, proceeds 4.5
    assert position.realized_pnl_sol == Decimal("2.5")
    assert position.open_cost_sol == Decimal(1) and position.avg_cost_sol_per_token == Decimal(
        "0.2"
    )
    assert position.unmatched_sell_tokens == 0
    assert position.first_buy_at == T0 and position.last_trade_at == T0 + timedelta(minutes=2)


def test_the_last_sell_closes_the_position_and_the_realized_carries_over() -> None:
    closing = _fill(3, "sell", 1_050_000_000, 50_000_000, "5")  # nets 1 SOL for a 1 SOL lot
    position = fold_position([BUY_1, BUY_2, SELL_15, closing])
    assert position.status == "closed" and position.tokens_held == 0
    assert position.realized_pnl_sol == Decimal("2.5") and position.sol_received == Decimal("5.5")
    assert position.avg_cost_sol_per_token is None and position.open_cost_sol == 0
    unrealized, r_multiple = unrealized_and_r(
        position, mark_of(position, snapshot=None, tape=None, fee_pct=DEFAULT_FEE_PCT)
    )
    assert unrealized is None and r_multiple == Decimal("2.5") / Decimal(3)


def test_a_sell_with_no_lot_behind_it_is_unmatched_and_realizes_nothing() -> None:
    orphan = _fill(0, "sell", 1_000_000_000, 0, "10")
    position = fold_position([orphan])
    assert position.unmatched_sell_tokens == Decimal(10) and position.realized_pnl_sol == 0
    assert position.sol_received == Decimal(1) and position.sol_spent == 0
    assert position.buys == 0 and position.first_buy_at is None and position.status == "closed"
    # Partly matched: 10 bought, 15 sold — 5 unmatched, and only the matched third
    # of the proceeds is realized against the lot.
    partial = fold_position([BUY_1, _fill(1, "sell", 3_000_000_000, 0, "15")])
    assert partial.unmatched_sell_tokens == Decimal(5)
    assert partial.realized_pnl_sol == Decimal(3) * Decimal(10) / Decimal(15) - Decimal(1)


def test_the_mark_prefers_the_newer_source_and_a_done_curve_is_not_a_price() -> None:
    position = fold_position([BUY_1, BUY_2, SELL_15])  # 5 tokens held, open cost 1 SOL
    reserves = CurveReserves(
        virtual_sol_reserves=Decimal(30), virtual_token_reserves=Decimal(1_073_000_000)
    )
    snapshot = SnapshotPoint(
        reserves=reserves, observed_at=T0 + timedelta(minutes=5), complete=False
    )
    tape = TapePoint(price_sol_per_token=Decimal("0.3"), at=T0 + timedelta(minutes=6))
    by_tape = mark_of(position, snapshot=snapshot, tape=tape, fee_pct=DEFAULT_FEE_PCT)
    assert (by_tape.mark_sol, by_tape.mark_source, by_tape.mark_at) == (
        Decimal("1.5"),
        "tape",
        tape.at,
    )
    unrealized, r_multiple = unrealized_and_r(position, by_tape)
    assert unrealized == Decimal("0.5") and r_multiple == (
        Decimal("2.5") + Decimal("0.5")
    ) / Decimal(3)
    older_tape = TapePoint(price_sol_per_token=Decimal("0.3"), at=T0 + timedelta(minutes=4))
    by_curve = mark_of(position, snapshot=snapshot, tape=older_tape, fee_pct=Decimal("1.25"))
    assert by_curve.mark_source == "curve_snapshot"
    assert by_curve.mark_sol == quote_sell(reserves, Decimal(5), Decimal("1.25")).net_sol
    done = SnapshotPoint(reserves=reserves, observed_at=snapshot.observed_at, complete=True)
    absent = mark_of(position, snapshot=done, tape=None, fee_pct=DEFAULT_FEE_PCT)
    assert absent.mark_sol is None and absent.mark_reason == "curve_complete_no_tape"
    assert (
        mark_of(position, snapshot=None, tape=None, fee_pct=DEFAULT_FEE_PCT).mark_reason
        == "no_snapshot_no_tape"
    )
    assert unrealized_and_r(position, absent) == (None, None)
    assert (
        mark_of(position, snapshot=done, tape=tape, fee_pct=DEFAULT_FEE_PCT).mark_source == "tape"
    )


def test_the_fee_rate_of_the_mark_is_the_wallets_own_when_it_exists() -> None:
    assert fee_pct_from_raw({"fee_bps": {"protocol": 95, "creator": 0, "cashback": 30}}) == Decimal(
        "1.25"
    )
    assert fee_pct_from_raw({"fee_bps": {"protocol": 95, "creator": 30, "cashback": 0}}) == Decimal(
        "1.25"
    )
    assert fee_pct_from_raw(None) is None and fee_pct_from_raw({"fee_bps": "x"}) is None
    assert fee_pct_from_raw({"fee_bps": {"protocol": "nope"}}) is None


def test_a_position_needs_a_fill() -> None:
    with pytest.raises(ValueError, match="at least one fill"):
        fold_position([])
