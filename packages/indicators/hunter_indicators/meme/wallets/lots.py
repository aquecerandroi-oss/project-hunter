"""FIFO lots per (owner, mint) and the realized PnL net of fees (design §1, W-PnL).

``owner_of`` maps a wallet to whoever owns the inventory: the wallet itself for
the per-wallet book (``meme_wallet_lots``), or the entity of the version in force
at the cut, so twin A's buy is matched by twin B's sell.

Rules this module keeps:

- a buy's lot cost is ``sol + fee`` plus the tx fee (once per owner and
  signature); a sell nets ``sol − fee`` minus the same tx fee;
- the oldest lot is consumed first; partial takes split cost and proceeds with
  floor division and give the remainder to the last piece, so lamports are
  conserved exactly;
- a sell beyond the inventory is **unmatched**: it never creates a free lot and
  never counts as realized (transfers are not swaps);
- a preserved lot with unknown cost (``cost_lamports=None``) yields an
  **incomplete** match — it gets no zero cost and does not vanish.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from hunter_indicators.meme.wallets.tape import Fill, event_order

__all__ = ["TX_FEE_LAMPORTS", "FifoResult", "Lot", "Match", "Unmatched", "fifo", "net_cash"]

TX_FEE_LAMPORTS = 5_000
"""Base signature fee per transaction (design §1). Priority fees are unknown here."""


@dataclass(frozen=True, slots=True)
class Lot:
    owner: str
    mint: str
    atoms: int
    cost_lamports: int | None
    opened_slot: int
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class Match:
    """One FIFO piece: part of a lot closed by part of a sell."""

    owner: str
    mint: str
    atoms: int
    cost_lamports: int | None
    proceeds_lamports: int
    opened_slot: int
    opened_at: datetime
    closed_slot: int
    closed_at: datetime

    @property
    def hold_slots(self) -> int:
        return self.closed_slot - self.opened_slot

    @property
    def hold_seconds(self) -> float:
        return (self.closed_at - self.opened_at).total_seconds()


@dataclass(frozen=True, slots=True)
class Unmatched:
    owner: str
    mint: str
    atoms: int
    proceeds_lamports: int
    slot: int


@dataclass(frozen=True, slots=True)
class FifoResult:
    matches: tuple[Match, ...]
    unmatched: tuple[Unmatched, ...]
    open_lots: tuple[Lot, ...]

    @property
    def realized_lamports(self) -> int:
        """W-PnL: proceeds − cost over the complete matches only."""
        return sum(
            m.proceeds_lamports - m.cost_lamports
            for m in self.matches
            if m.cost_lamports is not None
        )

    @property
    def incomplete_matches(self) -> int:
        return sum(1 for m in self.matches if m.cost_lamports is None)

    @property
    def unmatched_atoms(self) -> int:
        return sum(u.atoms for u in self.unmatched)

    @property
    def sold_atoms(self) -> int:
        return sum(m.atoms for m in self.matches) + self.unmatched_atoms


def net_cash(fill: Fill, tx_fee: int) -> int:
    """Signed lamports for the owner: a buy is ``−(sol+fee+tx)``, a sell ``sol−fee−tx``."""
    if fill.side == "buy":
        return -(fill.sol_lamports + fill.fee_lamports + tx_fee)
    return fill.sol_lamports - fill.fee_lamports - tx_fee


class _TxFees:
    """Charges the tx fee once per (owner, signature)."""

    def __init__(self, per_tx: int, charged: Iterable[tuple[str, str]] = ()) -> None:
        self.per_tx = per_tx
        self.seen: set[tuple[str, str]] = set(charged)

    def charge(self, owner: str, signature: str) -> int:
        key = (owner, signature)
        if key in self.seen:
            return 0
        self.seen.add(key)
        return self.per_tx


def _split(total: int | None, part: int, whole: int) -> int | None:
    return None if total is None else total * part // whole


def fifo(
    fills: Iterable[Fill],
    *,
    owner_of: Callable[[str], str],
    opening: Iterable[Lot] = (),
    tx_fee_lamports: int = TX_FEE_LAMPORTS,
    charged: Iterable[tuple[str, str]] = (),
) -> FifoResult:
    """Run ``fills`` (any order; sorted here) through FIFO books per (owner, mint).

    ``charged``: (owner, signature) pairs whose tx fee was already charged elsewhere (a fill of
    the same transaction in another mint, wave 1c-bis); they pay no fee here.
    """
    books: dict[tuple[str, str], deque[Lot]] = {}
    for lot in sorted(opening, key=lambda x: (x.opened_slot, x.opened_at)):
        books.setdefault((lot.owner, lot.mint), deque()).append(lot)
    fees = _TxFees(tx_fee_lamports, charged)
    matches: list[Match] = []
    unmatched: list[Unmatched] = []
    for f in sorted(fills, key=event_order):
        owner = owner_of(f.wallet)
        book = books.setdefault((owner, f.mint), deque())
        cash = net_cash(f, fees.charge(owner, f.signature))
        if f.side == "buy":
            book.append(Lot(owner, f.mint, f.token_atoms, -cash, f.slot, f.block_time))
            continue
        remaining, left_cash = f.token_atoms, cash
        while remaining and book:
            lot = book[0]
            take = min(remaining, lot.atoms)
            last_piece = take == remaining
            proceeds = left_cash if last_piece else cash * take // f.token_atoms
            cost = (
                lot.cost_lamports
                if take == lot.atoms
                else _split(lot.cost_lamports, take, lot.atoms)
            )
            matches.append(
                Match(
                    owner,
                    f.mint,
                    take,
                    cost,
                    proceeds,
                    lot.opened_slot,
                    lot.opened_at,
                    f.slot,
                    f.block_time,
                )
            )
            remaining -= take
            left_cash -= proceeds
            if take == lot.atoms:
                book.popleft()
            else:
                rest_cost = (
                    None if lot.cost_lamports is None or cost is None else lot.cost_lamports - cost
                )
                book[0] = Lot(
                    owner, f.mint, lot.atoms - take, rest_cost, lot.opened_slot, lot.opened_at
                )
        if remaining:
            unmatched.append(Unmatched(owner, f.mint, remaining, left_cash, f.slot))
    open_lots = tuple(lot for book in books.values() for lot in book)
    return FifoResult(tuple(matches), tuple(unmatched), open_lots)
