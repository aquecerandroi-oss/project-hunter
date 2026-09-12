"""The observed wallet's position per mint, derived from its fills — pure (T4.12).

**FIFO, and the cost is everything paid.** A buy opens a lot of ``tokens`` at
``(sol + fee) / 1e9`` SOL (RISK_ENGINE_MEME §5: on a curve the risk is what was
spent, never a stop distance); a sell consumes the oldest lots first and
realizes ``proceeds − cost`` on the matched part. A sell that finds no lot —
tokens the wallet held before the watch began — is **unmatched**: its proceeds
count in ``sol_received`` and in nothing else, because its cost was never seen.
No number here is invented to close the gap.

**The mark is what a full sell would net now**, the Lab's own definition
(``paper_engine.py``): on a live curve, ``quote_sell`` at the fee rate the
wallet's own fills showed; after the curve is done, tokens × the last tape
price; neither → ``None`` with a reason. R = ``(realized + unrealized) /
sol_spent`` (closed: ``realized / sol_spent``).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any, cast

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves, quote_sell

__all__ = [
    "DEFAULT_FEE_PCT",
    "LAMPORTS_PER_SOL",
    "Fill",
    "Mark",
    "Position",
    "SnapshotPoint",
    "TapePoint",
    "fee_pct_from_raw",
    "fold_position",
    "mark_of",
    "unrealized_and_r",
]

LAMPORTS_PER_SOL = Decimal(10**9)
DEFAULT_FEE_PCT = Decimal("1.25")
"""The curve's protocol fee (95 bps) plus cashback (30 bps) as observed on every
fill of 12/09 — the fallback when a position has no curve fill of its own."""

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class Fill:
    """One decoded fill of the ledger, in chronological key order."""

    at: datetime
    slot: int
    event_index: int
    side: str
    sol_lamports: int
    fee_lamports: int
    token_amount: Decimal

    @property
    def cost_sol(self) -> Decimal:
        """A buy: what left the wallet."""
        with localcontext(CONTEXT):
            return Decimal(self.sol_lamports + self.fee_lamports) / LAMPORTS_PER_SOL

    @property
    def proceeds_sol(self) -> Decimal:
        """A sell: what reached the wallet."""
        with localcontext(CONTEXT):
            return Decimal(self.sol_lamports - self.fee_lamports) / LAMPORTS_PER_SOL


@dataclass(frozen=True, slots=True)
class Position:
    tokens_held: Decimal
    sol_spent: Decimal
    sol_received: Decimal
    open_cost_sol: Decimal
    avg_cost_sol_per_token: Decimal | None
    realized_pnl_sol: Decimal
    unmatched_sell_tokens: Decimal
    buys: int
    sells: int
    first_buy_at: datetime | None
    last_trade_at: datetime

    @property
    def status(self) -> str:
        return "closed" if self.tokens_held == 0 else "open"


@dataclass(frozen=True, slots=True)
class SnapshotPoint:
    reserves: CurveReserves
    observed_at: datetime
    complete: bool


@dataclass(frozen=True, slots=True)
class TapePoint:
    price_sol_per_token: Decimal
    at: datetime


@dataclass(frozen=True, slots=True)
class Mark:
    mark_sol: Decimal | None
    mark_at: datetime | None
    mark_source: str | None
    mark_reason: str | None


def fold_position(fills: Iterable[Fill]) -> Position:
    """FIFO over the fills in ``(at, slot, event_index)`` order. Raises on none."""
    ordered = sorted(fills, key=lambda f: (f.at, f.slot, f.event_index))
    if not ordered:
        raise ValueError("a position needs at least one fill")
    lots: deque[tuple[Decimal, Decimal]] = deque()  # (tokens, cost_sol)
    spent = received = realized = unmatched = ZERO
    buys = sells = 0
    first_buy: datetime | None = None
    with localcontext(CONTEXT):
        for fill in ordered:
            if fill.side == "buy":
                buys += 1
                first_buy = first_buy or fill.at
                spent += fill.cost_sol
                if fill.token_amount > 0:
                    lots.append((fill.token_amount, fill.cost_sol))
                continue
            sells += 1
            proceeds = fill.proceeds_sol
            received += proceeds
            remaining = fill.token_amount
            matched_cost = ZERO
            matched_tokens = ZERO
            while remaining > 0 and lots:
                lot_tokens, lot_cost = lots[0]
                take = min(lot_tokens, remaining)
                cost = lot_cost * take / lot_tokens
                matched_cost += cost
                matched_tokens += take
                remaining -= take
                if take == lot_tokens:
                    lots.popleft()
                else:
                    lots[0] = (lot_tokens - take, lot_cost - cost)
            if fill.token_amount > 0:
                realized += proceeds * matched_tokens / fill.token_amount - matched_cost
            unmatched += remaining
        held = sum((tokens for tokens, _ in lots), ZERO)
        open_cost = sum((cost for _, cost in lots), ZERO)
        avg = open_cost / held if held > 0 else None
    return Position(
        tokens_held=held,
        sol_spent=spent,
        sol_received=received,
        open_cost_sol=open_cost,
        avg_cost_sol_per_token=avg,
        realized_pnl_sol=realized,
        unmatched_sell_tokens=unmatched,
        buys=buys,
        sells=sells,
        first_buy_at=first_buy,
        last_trade_at=ordered[-1].at,
    )


def fee_pct_from_raw(raw: Mapping[str, Any] | None) -> Decimal | None:
    """The fee rate a curve fill paid (protocol + creator + cashback bps), as a
    percentage — the rate the mark sells at. ``None`` when the raw has none."""
    if raw is None:
        return None
    bps_any = raw.get("fee_bps")
    if not isinstance(bps_any, Mapping):
        return None
    bps = cast(Mapping[str, Any], bps_any)
    try:
        total = sum(int(value) for value in bps.values())
    except (TypeError, ValueError):
        return None
    with localcontext(CONTEXT):
        return Decimal(total) / Decimal(100)


def mark_of(
    position: Position,
    *,
    snapshot: SnapshotPoint | None,
    tape: TapePoint | None,
    fee_pct: Decimal,
) -> Mark:
    """The newer of a live-curve quote and a tape price; a done curve is not a price."""
    if position.tokens_held <= 0:
        return Mark(None, None, None, "closed")
    curve_ok = snapshot is not None and not snapshot.complete
    use_tape = tape is not None and (
        not curve_ok or snapshot is None or tape.at > snapshot.observed_at
    )
    if use_tape and tape is not None:
        with localcontext(CONTEXT):
            return Mark(position.tokens_held * tape.price_sol_per_token, tape.at, "tape", None)
    if curve_ok and snapshot is not None:
        quote = quote_sell(snapshot.reserves, position.tokens_held, fee_pct)
        return Mark(quote.net_sol, snapshot.observed_at, "curve_snapshot", None)
    reason = "curve_complete_no_tape" if snapshot is not None else "no_snapshot_no_tape"
    return Mark(None, None, None, reason)


def unrealized_and_r(position: Position, mark: Mark) -> tuple[Decimal | None, Decimal | None]:
    """``unrealized = mark − open cost``; R over the SOL spent (``None`` at zero risk)."""
    with localcontext(CONTEXT):
        unrealized = None if mark.mark_sol is None else mark.mark_sol - position.open_cost_sol
        if position.sol_spent <= 0:
            return unrealized, None
        if position.tokens_held == 0:
            return unrealized, position.realized_pnl_sol / position.sol_spent
        if unrealized is None:
            return None, None
        return unrealized, (position.realized_pnl_sol + unrealized) / position.sol_spent
