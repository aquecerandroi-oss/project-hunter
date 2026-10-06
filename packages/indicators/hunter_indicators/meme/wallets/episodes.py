"""Episodes per (owner, mint) and the E-PnL of a window (design §1 item 2).

**E-PnL, as implemented** (errata of the design's wording, agreed with Astra in
``Revisoes-Astra/wallets-engine``): over a window ``[b0, bN)``

    E = Σ matched sale cash − Σ buy cash + V(bN) − V(b0)

where ``V(b)`` is the liquidation value of the owner's inventory at boundary
``b`` (a full sale against the valid state before ``b``, real-SOL ceiling, worst
state of the last slot, **0** without a valid state — :func:`.pricing.
liquidation_lamports`). The same rule values every boundary, so the daily
contributions telescope exactly to the window, a bag's loss enters once, and a
lot bought before the window enters at its start value, never at its old cost.
Read literally ("realized FIFO + Δ liquidation") the design would score a bag
bought at 1 and worth 0.2 as +0.2.

An **episode** is a stretch from a flat position to flat again in one mint;
its ``result_lamports`` is its contribution clipped to the window (open ones
included), so Σ episodes = E. ``hold`` is the **atom-weighted median** of its
matched FIFO pieces, so "buy 100, sell 99 a slot later, keep 1 an hour" is a
quick flip, not an hour's hold. Unmatched sale atoms bring no cash and are
counted against the owner (§1: > 20 % makes the accounting incomplete).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from hunter_indicators.meme.wallets.lots import TX_FEE_LAMPORTS, Lot, net_cash
from hunter_indicators.meme.wallets.pricing import (
    MintTape,
    liquidation_lamports,
    liquidation_or_none,
)
from hunter_indicators.meme.wallets.tape import Fill, Gap, event_order, touches_gap

__all__ = ["Episode", "OwnerBook", "window_books"]

_DAY = timedelta(days=1)


@dataclass(slots=True)
class Episode:
    owner: str
    mint: str
    opened_slot: int
    opened_at: datetime
    open_at_start: bool
    days: int
    first_buy_slot: int | None = None
    incomplete: bool = False
    """Opened with a preserved lot of unknown cost (§1: no zero cost, does not vanish)
    or without a valid state at the window start (V(start) = 0 would be optimistic)."""
    contaminated: bool = False
    """``[opened, closed]`` (open: to the cut) crosses a coverage gap (design §2)."""
    closed_slot: int | None = None
    closed_at: datetime | None = None
    cost_lamports: int = 0
    daily: tuple[int, ...] = ()
    hold_seconds: float | None = None
    hold_slots: int | None = None
    pieces: list[tuple[int, float, int]] = field(default_factory=list[tuple[int, float, int]])

    def __post_init__(self) -> None:
        if not self.daily:
            self.daily = (0,) * self.days

    @property
    def closed(self) -> bool:
        return self.closed_slot is not None

    @property
    def result_lamports(self) -> int:
        return sum(self.daily)

    def add(self, day: int, lamports: int) -> None:
        if 0 <= day < self.days:
            d = list(self.daily)
            d[day] += lamports
            self.daily = tuple(d)


@dataclass(slots=True)
class OwnerBook:
    owner: str
    episodes: list[Episode] = field(default_factory=list[Episode])
    sold_atoms: int = 0
    unmatched_atoms: int = 0

    @property
    def e_pnl_lamports(self) -> int:
        return sum(e.result_lamports for e in self.episodes)


def _weighted_median(pieces: list[tuple[int, float, int]]) -> tuple[float, int] | None:
    if not pieces:
        return None
    ordered = sorted(pieces, key=lambda p: (p[1], p[2]))
    half, run = sum(p[0] for p in ordered) / 2, 0
    for atoms, seconds, slots in ordered:
        run += atoms
        if run >= half:
            return seconds, slots
    return ordered[-1][1], ordered[-1][2]  # pragma: no cover - unreachable


class _Track:
    """One (owner, mint) replay with boundary valuations."""

    def __init__(self, owner: str, mint: str, tape: MintTape, bounds: list[datetime]) -> None:
        self.owner, self.mint, self.tape, self.bounds = owner, mint, tape, bounds
        self.days = len(bounds) - 1
        self.lots: deque[tuple[int, int, datetime]] = deque()  # (atoms, opened_slot, opened_at)
        self.current: Episode | None = None
        self.done: list[Episode] = []
        self.next_bound = 1
        self.sold = self.unmatched = 0

    def atoms(self) -> int:
        return sum(a for a, _, _ in self.lots)

    def open_with(self, opening: list[Lot]) -> None:
        for lot in sorted(opening, key=lambda x: (x.opened_slot, x.opened_at)):
            self.lots.append((lot.atoms, lot.opened_slot, lot.opened_at))
        if self.lots:
            _, slot, at = self.lots[0]
            ep = Episode(self.owner, self.mint, slot, at, open_at_start=True, days=self.days)
            start_value = liquidation_or_none(self.tape, self.bounds[0], self.atoms())
            ep.incomplete = start_value is None or any(lot.cost_lamports is None for lot in opening)
            v0 = start_value or 0
            ep.add(0, -v0)
            ep.cost_lamports += v0
            self.current = ep

    def pass_bounds(self, until: datetime | None) -> None:
        while self.next_bound <= self.days and (
            until is None or self.bounds[self.next_bound] <= until
        ):
            k = self.next_bound
            if self.current is not None:
                v = liquidation_lamports(self.tape, self.bounds[k], self.atoms())
                self.current.add(k - 1, v)
                self.current.add(k, -v)
            self.next_bound += 1

    def apply(self, f: Fill, cash: int) -> None:
        day = int((f.block_time - self.bounds[0]) // _DAY)
        if f.side == "buy":
            if self.current is None:
                self.current = Episode(
                    self.owner, self.mint, f.slot, f.block_time, open_at_start=False, days=self.days
                )
            if self.current.first_buy_slot is None:
                self.current.first_buy_slot = f.slot
            self.current.add(day, cash)
            self.current.cost_lamports -= cash
            self.lots.append((f.token_atoms, f.slot, f.block_time))
            return
        self.sold += f.token_atoms
        remaining = f.token_atoms
        ep = self.current
        while remaining and self.lots and ep is not None:
            atoms, slot, at = self.lots[0]
            take = min(atoms, remaining)
            ep.pieces.append((take, (f.block_time - at).total_seconds(), f.slot - slot))
            remaining -= take
            if take == atoms:
                self.lots.popleft()
            else:
                self.lots[0] = (atoms - take, slot, at)
        matched = f.token_atoms - remaining
        self.unmatched += remaining
        if ep is None or not matched:
            return
        ep.add(day, cash * matched // f.token_atoms)
        if not self.lots:
            ep.closed_slot, ep.closed_at = f.slot, f.block_time
            median = _weighted_median(ep.pieces)
            if median is not None:
                ep.hold_seconds, ep.hold_slots = median
            self.done.append(ep)
            self.current = None

    def finish(self, gaps: tuple[Gap, ...]) -> list[Episode]:
        self.pass_bounds(None)
        episodes = [*self.done, *([self.current] if self.current is not None else [])]
        for ep in episodes:
            end = (
                ep.closed_slot
                if ep.closed_slot is not None
                else max([ep.opened_slot, *(g.end_slot for g in gaps)])
            )
            ep.contaminated = touches_gap(ep.opened_slot, end, gaps)
        return episodes


def window_books(
    fills: Iterable[Fill],
    *,
    owner_of: Callable[[str], str],
    opening: Iterable[Lot],
    tapes: Mapping[str, MintTape],
    start: datetime,
    days: int,
    tx_fee_lamports: int = TX_FEE_LAMPORTS,
    gaps: Iterable[Gap] = (),
    charged: Iterable[tuple[str, str]] = (),
) -> dict[str, OwnerBook]:
    """Episodes and E-PnL per owner over ``[start, start + days)``.

    ``fills`` must already be the causal view of the window; ``opening`` are the
    preserved lots at ``start`` (keyed by their ``owner``, already mapped);
    ``charged`` as in :func:`.lots.fifo`.
    """
    bounds = [start + k * _DAY for k in range(days + 1)]
    holes = tuple(gaps)
    tracks: dict[tuple[str, str], _Track] = {}

    def track(owner: str, mint: str) -> _Track:
        key = (owner, mint)
        if key not in tracks:
            tracks[key] = _Track(owner, mint, tapes.get(mint, MintTape([])), bounds)
        return tracks[key]

    by_key: dict[tuple[str, str], list[Lot]] = {}
    for lot in opening:
        by_key.setdefault((lot.owner, lot.mint), []).append(lot)
    for (owner, mint), lots in by_key.items():
        track(owner, mint).open_with(lots)
    paid: set[tuple[str, str]] = set(charged)
    for f in sorted(fills, key=event_order):
        owner = owner_of(f.wallet)
        t = track(owner, f.mint)
        t.pass_bounds(f.block_time)
        fee = 0 if (owner, f.signature) in paid else tx_fee_lamports
        paid.add((owner, f.signature))
        t.apply(f, net_cash(f, fee))
    books: dict[str, OwnerBook] = {}
    for (owner, _mint), t in sorted(tracks.items()):
        book = books.setdefault(owner, OwnerBook(owner))
        book.episodes.extend(t.finish(holes))
        book.sold_atoms += t.sold
        book.unmatched_atoms += t.unmatched
    return books
