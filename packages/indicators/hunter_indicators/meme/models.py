"""Value objects of the paper curve wallet: caps, position, ledger line, fill.

Split out of :mod:`hunter_indicators.meme.paper` for the 350-line budget, not
because they are a different idea: the wallet is these four shapes plus the
rules that move between them. Everything monetary is ``Decimal``, everything
temporal is timezone-aware UTC, and every dataclass is frozen so a ledger can
be compared byte for byte between two runs of the same simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from hunter_indicators.meme.curve import CurveReserves

__all__ = [
    "Fill",
    "LedgerEvent",
    "LedgerKind",
    "PaperPosition",
    "PaperWalletLimits",
    "accepted_fill",
    "refused_fill",
    "require_utc",
    "utc_day",
]


class LedgerKind(StrEnum):
    """What a ledger line is. ``REFUSED`` is a first-class event, not a log line."""

    OPEN = "open"
    BUY = "buy"
    SELL = "sell"
    REFUSED = "refused"
    HALTED = "halted"
    RESUMED = "resumed"


@dataclass(frozen=True, slots=True)
class PaperWalletLimits:
    """The caps, by the names ``docs/RISK_ENGINE_MEME.md`` (T4.4) gives them.

    ``max_balance_sol`` is ``MEME_WALLET_MAX_SOL``, ``max_sol_per_trade`` is
    ``MEME_MAX_SOL_PER_TRADE``, ``daily_loss_cap_sol`` is
    ``MEME_DAILY_LOSS_CAP_SOL``. They are **parameters** here: this package never
    reads an env var and ships no default cap, so a simulation cannot silently
    run under a limit nobody chose.

    ``fee_pct`` is the **total** proportional fee of the path being simulated,
    not only the curve's: 1,25 % of the curve today, plus the fee of whatever
    execution path the doctrine picks (``docs/RISK_ENGINE_MEME.md`` §10.2 — "o
    papel nunca simula um caminho mais barato do que o live vai usar"; the
    PumpPortal local path adds 0,5 %). ``fill_delay_snapshots`` is how many
    snapshots after the intent the fill is priced at — at least one, by
    construction.
    """

    max_balance_sol: Decimal
    max_sol_per_trade: Decimal
    daily_loss_cap_sol: Decimal
    max_open_positions: int
    max_exposure_per_mint_sol: Decimal
    fee_pct: Decimal
    fill_delay_snapshots: int

    def __post_init__(self) -> None:
        for name in (
            "max_balance_sol",
            "max_sol_per_trade",
            "daily_loss_cap_sol",
            "max_exposure_per_mint_sol",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.fee_pct < 0:
            raise ValueError("fee_pct cannot be negative")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
        if self.fill_delay_snapshots < 1:
            raise ValueError(
                "fill_delay_snapshots must be at least 1: a fill cannot be priced at the "
                "state that produced the intent"
            )


@dataclass(frozen=True, slots=True)
class PaperPosition:
    """One open position. ``cost_basis_sol`` is everything the wallet paid for it."""

    mint: str
    tokens: Decimal
    cost_basis_sol: Decimal
    curve_cost_sol: Decimal
    fees_sol: Decimal
    priority_fees_sol: Decimal
    entry_reserves: CurveReserves
    entry_ts: datetime
    peak_mark_sol: Decimal
    """Highest mark-to-curve seen since entry — the reference of the trailing rule."""


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    """One line of the wallet's history, accepted or refused."""

    seq: int
    ts: datetime
    kind: LedgerKind
    mint: str | None
    sol_delta: Decimal
    tokens_delta: Decimal
    fee_sol: Decimal
    priority_fee_sol: Decimal
    balance_after: Decimal
    reason: str | None
    marginal_price_sol: Decimal | None
    realized_pnl_sol: Decimal | None


@dataclass(frozen=True, slots=True)
class Fill:
    """The answer to one intent: accepted with numbers, or refused with a name."""

    accepted: bool
    reason: str | None
    mint: str
    ts: datetime
    tokens: Decimal
    sol_delta: Decimal
    fee_sol: Decimal
    priority_fee_sol: Decimal
    balance_after: Decimal
    reserves_after: CurveReserves | None
    realized_pnl_sol: Decimal | None


def accepted_fill(
    event: LedgerEvent, *, mint: str, tokens: Decimal, reserves_after: CurveReserves
) -> Fill:
    """The fill an accepted ledger line describes — one place, so the two never drift."""
    return Fill(
        accepted=True,
        reason=None,
        mint=mint,
        ts=event.ts,
        tokens=tokens,
        sol_delta=event.sol_delta,
        fee_sol=event.fee_sol,
        priority_fee_sol=event.priority_fee_sol,
        balance_after=event.balance_after,
        reserves_after=reserves_after,
        realized_pnl_sol=event.realized_pnl_sol,
    )


def refused_fill(event: LedgerEvent, *, mint: str) -> Fill:
    """The fill a refusal describes: no tokens, no SOL, and the name of the no."""
    return Fill(
        accepted=False,
        reason=event.reason,
        mint=mint,
        ts=event.ts,
        tokens=Decimal(0),
        sol_delta=Decimal(0),
        fee_sol=Decimal(0),
        priority_fee_sol=Decimal(0),
        balance_after=event.balance_after,
        reserves_after=None,
        realized_pnl_sol=None,
    )


def require_utc(ts: datetime, what: str) -> None:
    """A naive timestamp is a programming error, never a market refusal."""
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{what} must be timezone-aware UTC")


def utc_day(ts: datetime) -> str:
    """UTC calendar day of a timestamp — the block of the day-block CI."""
    return ts.astimezone(UTC).date().isoformat()
