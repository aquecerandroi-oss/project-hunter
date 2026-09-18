"""Assembles ``GET /meme/live/wallet-summary`` (T4.57, Everton 18/09/2026: "a
carteira precisa estar mostrando o resultado real agora ... e o que estamos
perdendo no dia"): the executor's heartbeat, the radar's SOL/USD quote, the
FX cache, and :class:`WalletSummaryRow`'s bounded SQL aggregates — combined
into one honest snapshot, never a number this module invented.

Pure except for its inputs: every heartbeat/quote/row is read once by the
router and handed in, so this whole module is unit-testable with fakes (the
``services/meme_live.py`` / ``services/meme_lab_goal.py`` convention).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from hunter_api.repositories.meme_live import LivePositionRow
from hunter_api.repositories.meme_live_wallet import WalletSummaryRow
from hunter_api.schemas.meme_live_wallet import (
    WalletAllTimeOut,
    WalletBestWorstOut,
    WalletClosedPositionOut,
    WalletFxOut,
    WalletNowOut,
    WalletOpenPositionOut,
    WalletSummaryOut,
    WalletTodayOut,
)
from hunter_api.services.fx_rate import UsdBrlQuote
from hunter_api.services.meme_lab_goal import resolve_sol_usd
from hunter_api.services.meme_live import read_executor

__all__ = ["build_wallet_summary"]

LAMPORTS = Decimal(1_000_000_000)


def _decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _treasury_wallet_usdc(fields: Mapping[str, str]) -> Decimal | None:
    raw = fields.get("treasury")
    if not raw:
        return None
    try:
        parsed: Any = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return _decimal(cast(dict[str, Any], parsed).get("wallet_usdc"))


def _daily_loss_cap_sol(policy: dict[str, Any] | None) -> Decimal | None:
    if not policy:
        return None
    return _decimal(policy.get("daily_loss_cap_sol"))


def _now_block(
    *,
    wallet_sol_balance: Decimal | None,
    wallet_balance_stale_s: Decimal | None,
    wallet_usdc: Decimal | None,
    sol_usd: Any,
    sol_usd_reason: str | None,
    fx: WalletFxOut,
    row: WalletSummaryRow,
) -> WalletNowOut:
    total_usd: Decimal | None = None
    total_usd_reason: str | None = None
    if wallet_sol_balance is None:
        total_usd_reason = "no_wallet_balance"
    elif sol_usd is None:
        total_usd_reason = sol_usd_reason or "no_sol_usd_quote"
    else:
        total_usd = wallet_sol_balance * sol_usd.price_usd + (wallet_usdc or Decimal(0))

    total_brl: Decimal | None = None
    total_brl_reason: str | None = None
    if total_usd is None:
        total_brl_reason = total_usd_reason
    elif fx.usd_brl is None:
        total_brl_reason = fx.reason or "no_fx_quote"
    else:
        total_brl = total_usd * fx.usd_brl

    reserve_sol: Decimal | None = None
    reserve_sol_reason: str | None = None
    if wallet_sol_balance is None:
        reserve_sol_reason = "no_wallet_balance"
    else:
        reserve_sol = wallet_sol_balance - row.open_marked_sol

    return WalletNowOut(
        wallet_sol_balance=wallet_sol_balance,
        wallet_sol_balance_reason=None if wallet_sol_balance is not None else "no_wallet_balance",
        wallet_balance_stale_s=wallet_balance_stale_s,
        wallet_usdc_balance=wallet_usdc,
        wallet_usdc_balance_reason=None if wallet_usdc is not None else "no_treasury_reading",
        sol_usd=sol_usd,
        sol_usd_reason=sol_usd_reason,
        fx=fx,
        total_usd=total_usd,
        total_usd_reason=total_usd_reason,
        total_brl=total_brl,
        total_brl_reason=total_brl_reason,
        open_positions=row.open_positions,
        open_marked_sol=row.open_marked_sol,
        open_unmarked_positions=row.open_unmarked_positions,
        reserve_sol=reserve_sol,
        reserve_sol_reason=reserve_sol_reason,
    )


def _open_pnl(row: WalletSummaryRow) -> tuple[Decimal | None, str | None]:
    marked_open = row.open_positions - row.open_unmarked_positions
    if marked_open <= 0:
        return None, "no_open_positions" if row.open_positions == 0 else "positions_without_mark"
    pnl = row.open_marked_sol - (Decimal(row.open_spent_lamports_marked) / LAMPORTS)
    reason = "positions_without_mark" if row.open_unmarked_positions > 0 else None
    return pnl, reason


def _pnl_to_brl(
    pnl_sol: Decimal, sol_usd: Any, sol_usd_reason: str | None, fx: WalletFxOut
) -> tuple[Decimal | None, str | None]:
    if sol_usd is None:
        return None, sol_usd_reason or "no_sol_usd_quote"
    if fx.usd_brl is None:
        return None, fx.reason or "no_fx_quote"
    return pnl_sol * sol_usd.price_usd * fx.usd_brl, None


def _today_block(
    *,
    day: date,
    row: WalletSummaryRow,
    daily_loss_sol: Decimal | None,
    daily_loss_cap_sol: Decimal | None,
    small_test_remaining_sol: Decimal | None,
    sol_usd: Any,
    sol_usd_reason: str | None,
    fx: WalletFxOut,
) -> WalletTodayOut:
    realized_brl, realized_brl_reason = _pnl_to_brl(
        row.realized_pnl_today_sol, sol_usd, sol_usd_reason, fx
    )
    open_pnl_sol, open_pnl_reason = _open_pnl(row)
    return WalletTodayOut(
        day=day,
        bought=row.bought_today,
        sold=row.sold_today,
        won=row.won_today,
        lost=row.lost_today,
        realized_pnl_sol=row.realized_pnl_today_sol,
        realized_pnl_brl=realized_brl,
        realized_pnl_brl_reason=realized_brl_reason,
        open_pnl_sol=open_pnl_sol,
        open_pnl_sol_reason=open_pnl_reason,
        fees_sol=Decimal(row.fees_lamports_today) / LAMPORTS,
        rent_sol=Decimal(row.rent_lamports_today) / LAMPORTS,
        treasury_swaps=row.treasury_swaps_today,
        treasury_usdc_spent=row.treasury_usdc_spent_today,
        treasury_sol_bought=row.treasury_sol_bought_today,
        daily_loss_sol=daily_loss_sol,
        daily_loss_cap_sol=daily_loss_cap_sol,
        daily_loss_reason=None
        if daily_loss_sol is not None and daily_loss_cap_sol is not None
        else "no_daily_loss_reading",
        small_test_remaining_sol=small_test_remaining_sol,
    )


def _starting_equity(
    row: WalletSummaryRow,
) -> tuple[Decimal | None, str | None, datetime | None, str | None]:
    """The earliest wallet-equity reading this database actually kept — never
    an invented "first day" the tables have no row for."""
    anchor_ok = (
        row.kill_switch_day_start_sol_equity is not None
        and row.kill_switch_day_start_utc is not None
    )
    swap_ok = (
        row.first_treasury_swap_wallet_sol_before is not None
        and row.first_treasury_swap_at is not None
    )
    if not anchor_ok and not swap_ok:
        return None, None, None, "no_starting_equity_reading"
    if anchor_ok and (not swap_ok or row.kill_switch_day_start_utc <= row.first_treasury_swap_at):  # type: ignore[operator]
        return (
            row.kill_switch_day_start_sol_equity,
            "kill_switch_anchor",
            row.kill_switch_day_start_utc,
            None,
        )
    return (
        row.first_treasury_swap_wallet_sol_before,
        "first_treasury_swap",
        row.first_treasury_swap_at,
        None,
    )


def _all_time_block(
    row: WalletSummaryRow, sol_usd: Any, sol_usd_reason: str | None, fx: WalletFxOut
) -> WalletAllTimeOut:
    total_pnl_brl: Decimal | None = None
    total_pnl_brl_reason: str | None = None
    if row.total_pnl_sol is None:
        total_pnl_brl_reason = "no_closed_positions"
    else:
        total_pnl_brl, total_pnl_brl_reason = _pnl_to_brl(
            row.total_pnl_sol, sol_usd, sol_usd_reason, fx
        )
    starting_equity, starting_source, starting_at, starting_reason = _starting_equity(row)
    best = (
        None
        if row.best_trade_mint is None or row.best_trade_pnl_sol is None
        else WalletBestWorstOut(mint=row.best_trade_mint, pnl_sol=row.best_trade_pnl_sol)
    )
    worst = (
        None
        if row.worst_trade_mint is None or row.worst_trade_pnl_sol is None
        else WalletBestWorstOut(mint=row.worst_trade_mint, pnl_sol=row.worst_trade_pnl_sol)
    )
    return WalletAllTimeOut(
        total_bought=row.total_bought,
        total_won=row.total_won,
        total_lost=row.total_lost,
        total_pnl_sol=row.total_pnl_sol,
        total_pnl_sol_reason=None if row.total_pnl_sol is not None else "no_closed_positions",
        total_pnl_brl=total_pnl_brl,
        total_pnl_brl_reason=total_pnl_brl_reason,
        best_trade=best,
        worst_trade=worst,
        starting_equity_sol=starting_equity,
        starting_equity_source=starting_source,
        starting_equity_at=starting_at,
        starting_equity_reason=starting_reason,
    )


def build_wallet_summary(
    *,
    as_of: datetime,
    day: date,
    row: WalletSummaryRow,
    positions: list[LivePositionRow],
    executor_heartbeat: Mapping[str, str] | None,
    executor_heartbeat_error: str | None,
    executor_heartbeat_key: str,
    radar_heartbeat: Mapping[str, str] | None,
    fx: tuple[UsdBrlQuote | None, str | None],
) -> WalletSummaryOut:
    fields = executor_heartbeat or {}
    executor = read_executor(
        executor_heartbeat, as_of=as_of, key=executor_heartbeat_key, error=executor_heartbeat_error
    )
    sol_usd, sol_usd_reason = resolve_sol_usd(radar_heartbeat, None)
    fx_quote, fx_reason = fx
    fx_out = WalletFxOut(
        usd_brl=None if fx_quote is None else fx_quote.rate,
        observed_at=None if fx_quote is None else fx_quote.observed_at,
        source=None if fx_quote is None else fx_quote.source,
        stale=fx_reason == "stale",
        reason=fx_reason,
    )

    now = _now_block(
        wallet_sol_balance=executor.wallet_sol_balance,
        wallet_balance_stale_s=_decimal(fields.get("wallet_balance_stale_s")),
        wallet_usdc=_treasury_wallet_usdc(fields),
        sol_usd=sol_usd,
        sol_usd_reason=sol_usd_reason,
        fx=fx_out,
        row=row,
    )
    today = _today_block(
        day=day,
        row=row,
        daily_loss_sol=executor.daily_loss_sol,
        daily_loss_cap_sol=_daily_loss_cap_sol(executor.policy),
        small_test_remaining_sol=executor.small_test_remaining_sol,
        sol_usd=sol_usd,
        sol_usd_reason=sol_usd_reason,
        fx=fx_out,
    )
    all_time = _all_time_block(row, sol_usd, sol_usd_reason, fx_out)

    closed_today = [
        WalletClosedPositionOut(
            id=p.id,
            mint=p.mint,
            exit_at=p.exit_at,
            r_multiple=p.r_multiple,
            pnl_sol=p.pnl_sol,
            exit_reason=None
            if not p.exit
            else (p.exit.get("reason") if isinstance(p.exit.get("reason"), str) else None),
        )
        for p in positions
        if p.status == "closed" and p.exit_at is not None
    ]
    open_positions = [
        WalletOpenPositionOut(
            id=p.id, mint=p.mint, entry_at=p.entry_at, mark_sol=p.mark_sol, mark_at=p.mark_at
        )
        for p in positions
        if p.status == "open"
    ]

    return WalletSummaryOut(
        server_now=as_of,
        executor_status=executor.status,
        now=now,
        today=today,
        all_time=all_time,
        closed_today=closed_today,
        open=open_positions,
    )
