"""``GET /api/v1/orgs/{org_id}/meme/live/wallet-summary`` (T4.57) — "a carteira
mostrando o resultado real agora" (Everton, 18/09/2026): what is in the wallet
right now, what happened today (Brasília calendar day), and the all-time
ledger, in one call the desk polls every 10 s.

Every SOL/USD/BRL amount is ``DecimalStr`` (never a float over the wire, same
as ``schemas/meme_live.py``); every value this endpoint cannot honestly
compute is ``None`` with a named ``*_reason`` sitting next to it — never a
zero standing in for "unknown" (CLAUDE.md).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr
from hunter_api.schemas.meme_lab import SolUsdOut
from hunter_api.schemas.meme_live import MEME_LIVE_LABEL, ExecutorStatus

__all__ = [
    "WalletAllTimeOut",
    "WalletBestWorstOut",
    "WalletClosedPositionOut",
    "WalletFxOut",
    "WalletNowOut",
    "WalletOpenPositionOut",
    "WalletSummaryOut",
    "WalletTodayOut",
]


class WalletFxOut(BaseModel):
    """The USD/BRL rate this response priced with, or the honest reason it
    could not (``fx_rate.py``): never blocks the endpoint on the outside call."""

    usd_brl: DecimalStr | None
    observed_at: datetime | None
    source: str | None
    stale: bool
    reason: str | None = None


class WalletNowOut(BaseModel):
    """§1 "Dinheiro agora": chain-fresh balances, the open book's marked
    value, and the reserve left over."""

    wallet_sol_balance: DecimalStr | None
    wallet_sol_balance_reason: str | None = None
    wallet_balance_stale_s: DecimalStr | None
    wallet_usdc_balance: DecimalStr | None
    wallet_usdc_balance_reason: str | None = None
    sol_usd: SolUsdOut | None
    sol_usd_reason: str | None = None
    fx: WalletFxOut
    total_usd: DecimalStr | None
    total_usd_reason: str | None = None
    total_brl: DecimalStr | None
    total_brl_reason: str | None = None
    open_positions: int
    open_marked_sol: DecimalStr
    open_unmarked_positions: int
    """Open positions counted in ``open_positions`` but excluded from
    ``open_marked_sol`` — no ``mark_sol`` reading yet, never guessed at."""
    reserve_sol: DecimalStr | None
    reserve_sol_reason: str | None = None


class WalletTodayOut(BaseModel):
    """§2 "Hoje", since 00:00 America/Sao_Paulo."""

    day: date
    bought: int
    sold: int
    won: int
    lost: int
    realized_pnl_sol: DecimalStr
    realized_pnl_brl: DecimalStr | None
    realized_pnl_brl_reason: str | None = None
    open_pnl_sol: DecimalStr | None
    open_pnl_sol_reason: str | None = None
    fees_sol: DecimalStr
    rent_sol: DecimalStr
    treasury_swaps: int
    treasury_usdc_spent: DecimalStr
    treasury_sol_bought: DecimalStr
    daily_loss_sol: DecimalStr | None
    daily_loss_cap_sol: DecimalStr | None
    daily_loss_reason: str | None = None
    small_test_remaining_sol: DecimalStr | None


class WalletBestWorstOut(BaseModel):
    mint: str
    pnl_sol: DecimalStr


class WalletAllTimeOut(BaseModel):
    """§3 "Desde o início" — every number a plain aggregate over
    ``meme_live_positions``, never an inference across a gap in the data."""

    total_bought: int
    total_won: int
    total_lost: int
    total_pnl_sol: DecimalStr | None
    total_pnl_sol_reason: str | None = None
    total_pnl_brl: DecimalStr | None
    total_pnl_brl_reason: str | None = None
    best_trade: WalletBestWorstOut | None
    worst_trade: WalletBestWorstOut | None
    starting_equity_sol: DecimalStr | None
    starting_equity_source: str | None
    """``kill_switch_anchor`` (today's ``day_start_sol_equity``, the only
    reading this table keeps) or ``first_treasury_swap`` (the earliest
    ``wallet_sol_before`` on record) — named so the number is never read as
    older than it is."""
    starting_equity_at: datetime | None
    starting_equity_reason: str | None = None


class WalletClosedPositionOut(BaseModel):
    id: uuid.UUID
    mint: str
    exit_at: datetime
    r_multiple: DecimalStr | None
    pnl_sol: DecimalStr | None
    exit_reason: str | None


class WalletOpenPositionOut(BaseModel):
    id: uuid.UUID
    mint: str
    entry_at: datetime
    mark_sol: DecimalStr | None
    mark_at: datetime | None


class WalletSummaryOut(BaseModel):
    label: str = MEME_LIVE_LABEL
    server_now: datetime
    executor_status: ExecutorStatus
    now: WalletNowOut
    today: WalletTodayOut
    all_time: WalletAllTimeOut
    closed_today: list[WalletClosedPositionOut]
    open: list[WalletOpenPositionOut]
