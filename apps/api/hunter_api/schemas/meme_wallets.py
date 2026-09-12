"""The "Reais — carteira observada" section of ``GET /meme/lab`` and ``GET
/meme/desk`` (T4.12): the observed wallets' real fills and positions, read
from the chain by the meme-worker, **never executed by this system**.

The label travels in the payload. Every money field is ``DecimalStr``; every
"no value" is ``None`` with a reason (``ObservedValueOut``): a position without
a mark says why, a dollar figure without an observed SOL/USD quote says
``no_sol_usd_quote`` — never a ``0`` that reads as a loss.

Defined apart from ``meme_lab.py``/``meme_desk.py`` (which import this module
to add their ``real_observed`` field) so the two payloads share one shape and
no import cycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr

__all__ = [
    "MEME_REAL_OBSERVED_LABEL",
    "WalletLabContextOut",
    "LabVerdictOut",
    "ObservedSolUsdOut",
    "ObservedValueOut",
    "RealObservedOut",
    "WalletDecode",
    "WalletMarkSource",
    "WalletObservedOut",
    "WalletPositionOut",
    "WalletPositionStatus",
    "WalletTradeOut",
    "WalletTradeSide",
    "WalletVenue",
]

MEME_REAL_OBSERVED_LABEL = "REAL — observado na cadeia, não executado por este sistema"

WalletTradeSide = Literal["buy", "sell", "unknown"]
WalletVenue = Literal["curve", "pool"]
WalletDecode = Literal["trade_event", "balance_delta", "none"]
WalletPositionStatus = Literal["open", "closed"]
WalletMarkSource = Literal["curve_snapshot", "tape"]


class ObservedValueOut(BaseModel):
    """A number that is ``null`` with a reason instead of a zero."""

    value: DecimalStr | None
    reason: str | None = None


class ObservedSolUsdOut(BaseModel):
    """The observed SOL/USD quote the dollar figures below were priced with."""

    price_usd: DecimalStr
    source: str
    observed_at: datetime


class LabVerdictOut(BaseModel):
    kind: str
    accepted: bool | None
    """``None`` when the Lab had no features row for the mint at that minute."""
    refusals: list[str]


class WalletLabContextOut(BaseModel):
    """What every active rule set's gate said in the last closed minute before
    a real buy — the answer to "would the Lab have done the same?"."""

    minute: datetime | None
    features_version: str | None
    reason: str | None
    """``no_features_row`` when the Lab never folded that mint's minute."""
    rule_sets: dict[str, LabVerdictOut]
    hype_score: DecimalStr | None
    hype_reason: str | None
    line_reason: str | None
    evaluated_at: datetime | None


class WalletPositionOut(BaseModel):
    wallet: str
    wallet_short: str
    mint: str
    name: str | None
    symbol: str | None
    status: WalletPositionStatus
    tokens_held: DecimalStr
    sol_spent: DecimalStr
    """Σ buys, fees included — the risk of the position."""
    sol_received: DecimalStr
    open_cost_sol: DecimalStr
    avg_cost_sol_per_token: DecimalStr | None
    realized_pnl_sol: DecimalStr
    realized_pnl_usd: ObservedValueOut
    unrealized_pnl_sol: ObservedValueOut
    unrealized_pnl_usd: ObservedValueOut
    unmatched_sell_tokens: DecimalStr
    buys: int
    sells: int
    first_buy_at: datetime | None
    last_trade_at: datetime
    mark_sol: DecimalStr | None
    mark_at: datetime | None
    mark_source: WalletMarkSource | None
    mark_reason: str | None
    r_multiple: ObservedValueOut
    lab_context: WalletLabContextOut | None
    """Of the position's first buy; ``None`` while the loop has not written it."""
    hype_score: DecimalStr | None
    line_reason: str | None


class WalletTradeOut(BaseModel):
    wallet: str
    wallet_short: str
    signature: str
    event_index: int
    slot: int
    block_time: datetime | None
    received_at: datetime
    mint: str | None
    side: WalletTradeSide
    venue: WalletVenue | None
    sol_lamports: int | None
    fee_lamports: int | None
    sol_total: ObservedValueOut
    """A buy: ``sol + fee`` spent; a sell: ``sol − fee`` netted; in SOL."""
    token_amount: DecimalStr | None
    decode: WalletDecode
    reason: str | None
    """Why an ``unknown`` row decoded nothing."""
    lab_context: WalletLabContextOut | None
    hype_score: DecimalStr | None
    line_reason: str | None


class WalletObservedOut(BaseModel):
    wallet: str
    wallet_short: str
    trades: int
    fills: int
    unknown: int
    first_seen_at: datetime
    last_trade_at: datetime | None
    realized_total_sol: DecimalStr
    realized_total_usd: ObservedValueOut
    realized_today_sol: DecimalStr
    open_positions: int
    closed_positions: int
    open_cost_sol: DecimalStr
    open_marks_sol: DecimalStr
    unmarked_open: int
    """Open positions with no mark (no snapshot, no tape) — ``open_marks_sol``
    is a floor, not the equity."""


class RealObservedOut(BaseModel):
    label: str = MEME_REAL_OBSERVED_LABEL
    watched: int | None
    """Wallets in ``MEME_WATCH_WALLETS``, from the worker's heartbeat."""
    watched_reason: str | None = None
    wallets: list[WalletObservedOut]
    positions: list[WalletPositionOut]
    trades: list[WalletTradeOut]
    sol_usd: ObservedSolUsdOut | None
    sol_usd_reason: str | None = None
    reason: str | None = None
    """``no_wallet_observed`` when no watched wallet has a row yet."""
