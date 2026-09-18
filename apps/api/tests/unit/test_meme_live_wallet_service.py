"""``services/meme_live_wallet.py`` (T4.57) — "Carteira real": the wallet's
now/today/all-time blocks assembled from a fake ``WalletSummaryRow``, fake
heartbeats and fake positions. Pure: no DB, no Redis, no outbound HTTP.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_api.repositories.meme_live import LivePositionRow
from hunter_api.repositories.meme_live_wallet import WalletSummaryRow
from hunter_api.services.fx_rate import UsdBrlQuote
from hunter_api.services.meme_live_wallet import build_wallet_summary

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)
DAY = date(2026, 9, 18)
HEARTBEAT_KEY = "hb:meme:executor"


def _row(**overrides: Any) -> WalletSummaryRow:
    base: dict[str, Any] = {
        "open_positions": 0,
        "open_marked_sol": Decimal("0"),
        "open_unmarked_positions": 0,
        "open_spent_lamports_marked": 0,
        "bought_today": 0,
        "sold_today": 0,
        "won_today": 0,
        "lost_today": 0,
        "realized_pnl_today_sol": Decimal("0"),
        "total_bought": 0,
        "total_won": 0,
        "total_lost": 0,
        "total_pnl_sol": None,
        "best_trade_mint": None,
        "best_trade_pnl_sol": None,
        "worst_trade_mint": None,
        "worst_trade_pnl_sol": None,
        "fees_lamports_today": 0,
        "rent_lamports_today": 0,
        "treasury_swaps_today": 0,
        "treasury_usdc_spent_today": Decimal("0"),
        "treasury_sol_bought_today": Decimal("0"),
        "kill_switch_day_start_sol_equity": None,
        "kill_switch_day_start_utc": None,
        "first_treasury_swap_wallet_sol_before": None,
        "first_treasury_swap_at": None,
    }
    base.update(overrides)
    return WalletSummaryRow(**base)


def _position(**overrides: Any) -> LivePositionRow:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "proposal_id": uuid.uuid4(),
        "mint": "9eoCKjVtEzehnnJSv9yYEwSSkYPANrxUZRq7U4HWpvzN",
        "status": "open",
        "entry_at": AS_OF - timedelta(hours=1),
        "tokens": 1_000_000,
        "sol_spent_lamports": 20_000_000,
        "initial_risk_sol": Decimal("0.02"),
        "params": {},
        "mark_sol": None,
        "mark_at": None,
        "mark_source": None,
        "mark_reason": None,
        "high_water_sol": None,
        "exit_intent": None,
        "sell_requested_at": None,
        "sell_requested_by": None,
        "exit_at": None,
        "exit": None,
        "sol_received_lamports": None,
        "pnl_sol": None,
        "r_multiple": None,
        "migrated": False,
    }
    base.update(overrides)
    return LivePositionRow(**base)


ALIVE_EXECUTOR: dict[str, str] = {
    "ts": AS_OF.isoformat(),
    "executor_ts": AS_OF.isoformat(),
    "last_entries_tick_at": (AS_OF - timedelta(seconds=5)).isoformat(),
    "wallet_sol_balance": "1.5",
    "wallet_balance_stale_s": "2.3",
    "treasury": json.dumps({"wallet_usdc": "10.5"}),
    "policy": json.dumps({"daily_loss_cap_sol": "0.1"}),
    "day_start_sol_equity": "1.6",
    "equity_sol": "1.5",
    "daily_loss_sol": "0.1",
    "small_test_remaining_sol": "0.05",
}
RADAR_WITH_QUOTE: dict[str, str] = {
    "lab_sol_usd": "150.0",
    "lab_sol_usd_source": "jupiter",
    "lab_sol_usd_observed_at": AS_OF.isoformat(),
}
FX_OK = (UsdBrlQuote(rate=Decimal("5.4"), observed_at=AS_OF), None)
FX_MISSING = (None, "no_fx_quote")


def test_a_healthy_wallet_totals_sol_usdc_usd_and_brl() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.executor_status == "alive"
    assert out.now.wallet_sol_balance == Decimal("1.5")
    assert out.now.wallet_balance_stale_s == Decimal("2.3")
    assert out.now.wallet_usdc_balance == Decimal("10.5")
    assert out.now.sol_usd is not None
    assert out.now.sol_usd.price_usd == Decimal("150.0")
    # 1.5 SOL * 150 USD/SOL + 10.5 USDC = 235.5 USD
    assert out.now.total_usd == Decimal("235.5")
    assert out.now.total_brl == Decimal("235.5") * Decimal("5.4")
    assert out.now.reserve_sol == Decimal("1.5")  # no open positions locked


def test_a_missing_sol_usd_quote_names_the_reason_never_a_partial_total() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=None,
        fx=FX_OK,
    )
    assert out.now.sol_usd is None
    assert out.now.total_usd is None
    assert out.now.total_usd_reason == "no_sol_usd_quote"
    assert out.now.total_brl is None
    assert out.now.total_brl_reason == "no_sol_usd_quote"


def test_a_missing_fx_quote_leaves_usd_intact_and_names_brl_apart() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_MISSING,
    )
    assert out.now.total_usd is not None
    assert out.now.total_brl is None
    assert out.now.total_brl_reason == "no_fx_quote"
    assert out.now.fx.usd_brl is None
    assert out.now.fx.reason == "no_fx_quote"


def test_a_heartbeat_missing_entirely_names_every_now_field_absent() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=None,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=None,
        fx=FX_MISSING,
    )
    assert out.executor_status == "heartbeat_missing"
    assert out.now.wallet_sol_balance is None
    assert out.now.wallet_sol_balance_reason == "no_wallet_balance"
    assert out.now.reserve_sol is None
    assert out.now.reserve_sol_reason == "no_wallet_balance"


def test_todays_realized_pnl_converts_to_brl_and_the_open_pnl_excludes_unmarked_positions() -> None:
    row = _row(
        open_positions=2,
        open_unmarked_positions=1,
        open_marked_sol=Decimal("0.03"),
        open_spent_lamports_marked=20_000_000,  # 0.02 SOL
        realized_pnl_today_sol=Decimal("0.01"),
        bought_today=3,
        sold_today=1,
        won_today=1,
        lost_today=0,
    )
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=row,
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.today.bought == 3
    assert out.today.sold == 1
    assert out.today.won == 1
    # 0.01 SOL * 150 USD/SOL * 5.4 BRL/USD
    assert out.today.realized_pnl_brl == Decimal("0.01") * Decimal("150.0") * Decimal("5.4")
    assert out.today.open_pnl_sol == Decimal("0.03") - Decimal("0.02")
    assert out.today.open_pnl_sol_reason == "positions_without_mark"
    assert out.today.daily_loss_sol == Decimal("0.1")
    assert out.today.daily_loss_cap_sol == Decimal("0.1")


def test_no_open_positions_names_the_open_pnl_reason_apart_from_unmarked_ones() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.today.open_pnl_sol is None
    assert out.today.open_pnl_sol_reason == "no_open_positions"


def test_the_starting_equity_picks_whichever_reading_is_earlier() -> None:
    anchor_time = AS_OF - timedelta(days=1)
    swap_time = AS_OF - timedelta(days=5)
    row = _row(
        kill_switch_day_start_sol_equity=Decimal("2.0"),
        kill_switch_day_start_utc=anchor_time,
        first_treasury_swap_wallet_sol_before=Decimal("0.5"),
        first_treasury_swap_at=swap_time,
    )
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=row,
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.all_time.starting_equity_sol == Decimal("0.5")
    assert out.all_time.starting_equity_source == "first_treasury_swap"
    assert out.all_time.starting_equity_at == swap_time


def test_no_starting_equity_reading_at_all_names_the_reason() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.all_time.starting_equity_sol is None
    assert out.all_time.starting_equity_reason == "no_starting_equity_reading"


def test_best_and_worst_trade_and_the_closed_vs_open_lists() -> None:
    closed = _position(
        status="closed",
        exit_at=AS_OF - timedelta(hours=2),
        pnl_sol=Decimal("0.05"),
        r_multiple=Decimal("2.5"),
        exit={"reason": "target"},
    )
    open_pos = _position(status="open", mark_sol=Decimal("0.03"), mark_at=AS_OF)
    row = _row(
        total_bought=2,
        total_won=1,
        total_lost=0,
        total_pnl_sol=Decimal("0.05"),
        best_trade_mint=closed.mint,
        best_trade_pnl_sol=Decimal("0.05"),
        worst_trade_mint=closed.mint,
        worst_trade_pnl_sol=Decimal("0.05"),
    )
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=row,
        positions=[closed, open_pos],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.all_time.best_trade is not None
    assert out.all_time.best_trade.mint == closed.mint
    assert len(out.closed_today) == 1
    assert out.closed_today[0].exit_reason == "target"
    assert out.closed_today[0].r_multiple == Decimal("2.5")
    assert len(out.open) == 1
    assert out.open[0].mark_sol == Decimal("0.03")


def test_no_closed_positions_ever_names_the_total_pnl_reason() -> None:
    out = build_wallet_summary(
        as_of=AS_OF,
        day=DAY,
        row=_row(),
        positions=[],
        executor_heartbeat=ALIVE_EXECUTOR,
        executor_heartbeat_error=None,
        executor_heartbeat_key=HEARTBEAT_KEY,
        radar_heartbeat=RADAR_WITH_QUOTE,
        fx=FX_OK,
    )
    assert out.all_time.total_pnl_sol is None
    assert out.all_time.total_pnl_sol_reason == "no_closed_positions"
    assert out.all_time.best_trade is None
    assert out.all_time.worst_trade is None
