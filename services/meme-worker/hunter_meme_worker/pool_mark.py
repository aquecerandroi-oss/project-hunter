"""Marking and selling a paper position on the PumpSwap pool's tape — pure
(T4.11, EXP-M4: a bet that held through the migration).

The arithmetic is :mod:`hunter_indicators.meme.pool`; this module binds it to
the Lab's shapes: a :class:`~hunter_meme_worker.lab_models.BetState`, the
``Mark`` the exit rules read, and the ``BetExit`` a close writes.

Three rules, mirrored from the curve engine (``paper_engine.py``):

1. **The mark is what a full sell would net now** — the last trade's price
   minus our impact (participation in the last five minutes, capped 1 %),
   minus the PumpSwap fee of the market-cap band that price sits in, minus the
   path's own fee — never price × quantity.
2. **A sale is priced on the trade *after* the one the rule fired on**
   (``lab_bets_pool.py`` walks the tape in order and closes on the first
   trade past the intent), so no exit is ever filled at the price that
   motivated it.
3. **No trade to sell into is not a fabricated fill.** A ``dead`` intent that
   the window closes on without a single trade is written off at zero
   (``docs/RISK_ENGINE_MEME.md`` §5: the plausible outcome is the whole stake)
   — with ``reason = dead`` and ``fill = none``, so the diary says the market
   was gone, not that a rug detector fired.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CURVE_TRADE_FEE_PCT
from hunter_indicators.meme.pool import PoolSellQuote, PoolTrade, quote_pool_sell, volume_sol
from hunter_meme_worker.lab_models import (
    MARK_POOL_TAPE,
    BetExit,
    BetState,
    SolUsd,
    money_str,
    optional_money_str,
)
from hunter_meme_worker.paper_engine import Mark

__all__ = [
    "POOL_VENUE",
    "PUMP_TOTAL_SUPPLY",
    "PoolMark",
    "close_dead_without_trade",
    "close_on_pool",
    "mark_on_pool",
    "path_fee_pct",
    "stale_seconds",
    "trade_json",
]

POOL_VENUE: Final = "pump_amm"
PUMP_TOTAL_SUPPLY: Final = Decimal(1_000_000_000)
"""The supply the fee table is written against ("preço × 1 bi de tokens",
``docs/PUMPFUN.md`` §4.1) — the fallback when ``meme_tokens.total_supply`` is
unknown, **named** in the payload (``total_supply_source``)."""

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class PoolMark:
    """One mark on one pool trade: the number, the quote behind it, the trade."""

    mark: Mark
    quote: PoolSellQuote
    trade: PoolTrade
    total_supply_source: str


def path_fee_pct(fee_pct: Decimal) -> Decimal:
    """What the rule set's ``fee_pct`` carries **above** the curve's 1,25 %: the
    execution path's own cut (0,5 % for the PumpPortal local path), charged on
    the pool exactly as on the curve. Never negative."""
    with localcontext(CONTEXT):
        return max(ZERO, fee_pct - CURVE_TRADE_FEE_PCT)


def mark_on_pool(
    bet: BetState,
    trade: PoolTrade,
    known: Sequence[PoolTrade],
    *,
    total_supply: Decimal | None,
) -> PoolMark:
    """The honest mark on ``trade``: its price, our impact against the five
    minutes of volume ending at it (``known`` = every trade the instant could
    see), the band's fee at that price, the path's fee, the priority fee."""
    supply, source = (
        (total_supply, "meme_tokens")
        if total_supply is not None and total_supply > 0
        else (PUMP_TOTAL_SUPPLY, "assumed_1e9")
    )
    quote = quote_pool_sell(
        bet.tokens,
        trade.price_sol,
        volume_5m_sol=volume_sol(known, at=trade.block_time),
        total_supply=supply,
        path_fee_pct=path_fee_pct(bet.fee_pct),
    )
    with localcontext(CONTEXT):
        mark_sol = quote.net_sol - bet.priority_fee_sol
        high_water = max(bet.high_water_x, mark_sol / bet.sol_spent)
    return PoolMark(
        mark=Mark(mark_sol=mark_sol, high_water_x=high_water),
        quote=quote,
        trade=trade,
        total_supply_source=source,
    )


def stale_seconds(now: datetime, last_seen: datetime) -> int:
    """Seconds since the last trade the tick could see — never negative."""
    return max(0, int((now - last_seen).total_seconds()))


def trade_json(trade: PoolTrade) -> dict[str, Any]:
    return {
        "block_time": trade.block_time.isoformat(),
        "received_at": trade.received_at.isoformat(),
        "side": trade.side,
        "sol": money_str(trade.sol),
        "tokens": money_str(trade.tokens),
        "price_sol": money_str(trade.price_sol),
    }


def _quote_json(pool_mark: PoolMark) -> dict[str, Any]:
    quote = pool_mark.quote
    return {
        "venue": POOL_VENUE,
        "mark_source": MARK_POOL_TAPE,
        "trade": trade_json(pool_mark.trade),
        "price_sol": money_str(quote.price_sol),
        "gross_sol": money_str(quote.gross_sol),
        "volume_5m_sol": money_str(quote.volume_5m_sol),
        "mcap_sol": money_str(quote.mcap_sol),
        "total_supply_source": pool_mark.total_supply_source,
        "impact_pct": money_str(quote.impact_pct),
        "impact_reason": quote.impact_reason,
        "impact_sol": money_str(quote.impact_sol),
        "tier_fee_pct": money_str(quote.tier_fee_pct),
        "path_fee_pct": money_str(quote.path_fee_pct),
        "fee_sol": money_str(quote.fee_sol),
    }


def close_on_pool(
    bet: BetState,
    pool_mark: PoolMark,
    reason: str,
    sol_usd: SolUsd | None,
    *,
    intent_trade_at: datetime | None,
    mark_stale_s: int,
) -> BetExit:
    """Sell everything on ``pool_mark.trade`` — the one after the rule fired."""
    quote = pool_mark.quote
    with localcontext(CONTEXT):
        received = quote.net_sol - bet.priority_fee_sol
        pnl = received - bet.sol_spent
        r_multiple = pnl / bet.initial_risk_sol
    exit_payload: dict[str, Any] = {
        "reason": reason,
        "fill": "next_trade",
        **_quote_json(pool_mark),
        "snapshot": None,
        "intent_snapshot_at": None,
        "intent_trade_at": None if intent_trade_at is None else intent_trade_at.isoformat(),
        "mark_stale_s": mark_stale_s,
        "priority_fee_sol": money_str(bet.priority_fee_sol),
        "sol_received": money_str(received),
        "sol_usd": None if sol_usd is None else sol_usd.as_json(),
        "sol_usd_source": None if sol_usd is None else sol_usd.source,
        "sol_usd_reason": None if sol_usd is not None else "quote_unavailable",
    }
    return BetExit(
        exit_at=pool_mark.trade.block_time,
        exit=exit_payload,
        pnl_sol=pnl,
        r_multiple=r_multiple,
        sol_usd_at_exit=None if sol_usd is None else sol_usd.price_usd,
    )


def close_dead_without_trade(
    bet: BetState,
    *,
    now: datetime,
    mark_stale_s: int,
    last_trade_at: datetime | None,
    last_mark_sol: Decimal | None,
) -> BetExit:
    """The ``dead`` intent found no trade to sell into inside the window: the
    position is worth what nobody will pay — zero. ``last_mark_sol`` is kept
    on the payload as what the stale tape *said*, never as what was received."""
    with localcontext(CONTEXT):
        pnl = -bet.sol_spent
        r_multiple = pnl / bet.initial_risk_sol
    return BetExit(
        exit_at=now,
        exit={
            "reason": "dead",
            "fill": "none",
            "venue": POOL_VENUE,
            "mark_source": MARK_POOL_TAPE,
            "snapshot": None,
            "trade": None,
            "last_trade_at": None if last_trade_at is None else last_trade_at.isoformat(),
            "last_mark_sol": optional_money_str(last_mark_sol),
            "mark_stale_s": mark_stale_s,
            "sol_received": "0",
            "sol_usd": None,
            "sol_usd_source": None,
            "sol_usd_reason": "no_sale_to_price",
        },
        pnl_sol=pnl,
        r_multiple=r_multiple,
        sol_usd_at_exit=None,
    )
