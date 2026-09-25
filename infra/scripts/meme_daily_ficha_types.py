"""Shared, pure dataclasses of the daily ficha (T4.92) — the contract between
``meme_daily_ficha_queries.py`` (fills them from Postgres) and
``meme_daily_ficha_render.py`` (turns them into Markdown). No database import
here, no clock: a value this ficha could not prove is ``None``, never a
guessed number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

__all__ = [
    "DayFicha",
    "DecisionFeatures",
    "PaperArm",
    "RealPosition",
    "SpotPosition",
]


@dataclass(frozen=True, slots=True)
class DecisionFeatures:
    """What the desk saw at the decision instant — ``None`` where this ficha
    could not prove a value, never a guessed zero."""

    curve_progress_pct: Decimal | None
    snipers: int | None
    dev_share_pct: Decimal | None
    buys_1m: int | None
    sells_1m: int | None
    unique_buyers: int | None
    net_flow_sol: Decimal | None
    creation_bundle_sol: Decimal | None
    creation_bundle_wallets: int | None


@dataclass(frozen=True, slots=True)
class RealPosition:
    """One real meme position (``meme_live_positions``), one row of the ficha."""

    mint: str
    symbol: str | None
    operator: str
    entry_at: datetime
    exit_at: datetime | None
    cost_sol: Decimal
    sol_out: Decimal | None
    pnl_sol: Decimal | None
    high_water_sol: Decimal | None
    exit_reason: str | None
    sell_attempts: int
    fees_sol: Decimal | None
    rent_refund_sol: Decimal | None
    round_trip_cost_sol: Decimal | None
    distinct_sellers_one_slot: int | None
    since_prior_exit: timedelta | None
    features: DecisionFeatures


@dataclass(frozen=True, slots=True)
class SpotPosition:
    """One real ``spot/1`` position (``spot_positions``)."""

    market_symbol: str
    mint: str
    entry_at: datetime
    exit_at: datetime | None
    entry_price: Decimal | None
    target_price: Decimal | None
    stop_price: Decimal | None
    pnl_sol: Decimal | None


@dataclass(frozen=True, slots=True)
class PaperArm:
    """One rule set's last-24h paper record (``meme_paper_bets``)."""

    rule_set: str
    entries: int
    wins: int
    pnl_sol: Decimal
    avg_pct_per_ticket: Decimal | None


@dataclass(frozen=True, slots=True)
class DayFicha:
    day: date
    generated_at: datetime
    positions: Sequence[RealPosition]
    spot: Sequence[SpotPosition]
    paper_arms: Sequence[PaperArm]
    cumulative_pnl_sol: Decimal | None
