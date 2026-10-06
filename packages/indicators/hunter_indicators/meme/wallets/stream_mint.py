"""One mint of the nightly replay (wave 1c-bis, :mod:`.stream` pass 3) and its next carry.

The mint's tape is reduced to the carried **frontier** (every event of the highest slot received
before the window start ``S``) plus every event received from ``S`` on. That is enough for each
query the snapshot makes of the tape, given the contract of :mod:`.carry`:

- ``valid_states_at(b)`` for ``b ≥ S`` — an event received before ``S`` and not in the frontier has
  a lower slot than the frontier, so it can never be the last slot before ``b``;
- landing states of a window trigger — the landing slot and the slot before it are at or above the
  frontier slot (one time per slot, time never decreasing with the slot), so all their events are
  in the reduced tape; the stop only scans slots after the entry;
- the leader's "> half sold" — the frontier's and every earlier arrival's atoms come from the
  carried per-wallet totals (``leader_prior``) and those events are skipped (``leader_since``);
  every later arrival is replayed in arrival order, buys included.

Opening lots are the carried per-wallet lots mapped to the entity of the cut; the tx fee of a
multi-mint transaction is pre-seeded where it is not due (``charged``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from hunter_indicators.meme.wallets.carry import (
    Flow,
    MintCarry,
    canonical_order,
    flow_totals,
    sort_lots,
)
from hunter_indicators.meme.wallets.entities import Entities
from hunter_indicators.meme.wallets.episodes import Episode, window_books
from hunter_indicators.meme.wallets.follow import decision_order
from hunter_indicators.meme.wallets.lots import Lot, fifo
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.policy import CopyOutcome, simulate_copy
from hunter_indicators.meme.wallets.pricing import MintTape
from hunter_indicators.meme.wallets.stream_metrics import EntityTally
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap

__all__ = ["CopyTally", "Night", "Tallies", "earliest_create", "replay_mint"]


@dataclass(frozen=True, slots=True)
class Night:
    """Everything the replay of one mint needs that is the same for every mint of the night."""

    start: datetime
    cut: datetime
    next_start: datetime
    horizon: int
    entities: Entities
    funded_by: Mapping[str, str]
    gaps: tuple[Gap, ...]
    policy: FollowPolicy
    params: RankingParams
    bets: frozenset[tuple[str, str, int]]
    entity_seeds: Mapping[str, frozenset[tuple[str, str]]]
    """mint → (entity, signature) whose tx fee is due in another mint (window books)."""
    wallet_seeds: Mapping[str, frozenset[tuple[str, str]]]
    """mint → (wallet, signature) whose tx fee is due in another mint (the per-wallet seal)."""


@dataclass(slots=True)
class CopyTally:
    """``ranking._c_pnl``'s tally: complete copies summed, incomplete/contaminated counted."""

    total: int = 0
    copies: int = 0
    incomplete: int = 0
    contaminated: int = 0

    def add(self, out: CopyOutcome) -> None:
        if out.status in ("closed", "censored") and out.net_lamports is not None:
            self.total += out.net_lamports
            self.copies += 1
            self.contaminated += out.contaminated
        elif out.status == "incomplete":
            self.incomplete += 1
            self.contaminated += out.contaminated


@dataclass(slots=True)
class Tallies:
    books: dict[str, EntityTally] = field(default_factory=dict[str, EntityTally])
    copies: dict[str, CopyTally] = field(default_factory=dict[str, CopyTally])
    w_pnl: dict[str, int] = field(default_factory=dict[str, int])

    def copies_of(self, entity: str) -> CopyTally:
        return self.copies.get(entity, CopyTally())


def earliest_create(
    window_carry: MintCarry, creates: Iterable[CreateEvent], before: datetime
) -> CreateEvent | None:
    """The earliest received ``CreateEvent`` received before ``before`` (the carried one first)."""
    best = window_carry.create
    for c in creates:
        if c.received_at < before and (best is None or c.received_at < best.received_at):
            best = c
    return best


def _excluded(f: Fill, episodes: Iterable[Episode]) -> bool:
    return any(
        e.opened_slot <= f.slot <= (e.closed_slot if e.closed_slot is not None else f.slot)
        for e in episodes
    )


def _wallet(w: str) -> str:
    return w


def _frontier(events: Iterable[Fill]) -> tuple[Fill, ...]:
    pool = list(events)
    if not pool:
        return ()
    top = max(f.slot for f in pool)
    return tuple(sorted((f for f in pool if f.slot == top), key=canonical_order))


def _flows(old: tuple[Flow, ...], arrived: Iterable[Fill]) -> tuple[Flow, ...]:
    totals = {f.wallet: [f.bought_atoms, f.sold_atoms] for f in old}
    for f in arrived:
        row = totals.setdefault(f.wallet, [0, 0])
        row[f.side == "sell"] += f.token_atoms
    return tuple(Flow(w, b, s) for w, (b, s) in sorted(totals.items()))


def _advance(
    carry: MintCarry, fills: tuple[Fill, ...], creates: Iterable[CreateEvent], night: Night
) -> MintCarry:
    """The carry at ``next_start``: lots by mining time (the day is sealed under P1), the rest
    by arrival time (Astra must-fix 1: two clocks)."""
    nxt = night.next_start
    arrived = [f for f in fills if f.received_at < nxt]
    mined = [f for f in fills if night.start <= f.block_time < nxt]
    sealed = fifo(mined, owner_of=_wallet, opening=carry.lots,
                  charged=night.wallet_seeds.get(carry.mint, frozenset()))  # fmt: skip
    return MintCarry(
        carry.mint,
        _frontier((*carry.frontier, *arrived)),
        sort_lots(sealed.open_lots),
        _flows(carry.flows, arrived),
        earliest_create(carry, creates, nxt),
    )


def replay_mint(
    carry: MintCarry,
    fills: tuple[Fill, ...],
    creates: tuple[CreateEvent, ...],
    night: Night,
    tallies: Tallies,
) -> MintCarry:
    """Fold one mint of the window into ``tallies``; return the mint's next carry.

    ``fills`` = the mint's causal events received from the window start on, canonical order.
    """
    mint, ents, par = carry.mint, night.entities, night.params
    tape = MintTape([*carry.frontier, *fills])
    window = [f for f in fills if f.block_time >= night.start]
    opening = [
        Lot(ents.of(lot.owner), lot.mint, lot.atoms, lot.cost_lamports, lot.opened_slot,
            lot.opened_at)
        for lot in carry.lots
    ]  # fmt: skip
    create = earliest_create(carry, creates, night.cut)
    known = {} if create is None else {mint: create}
    seeds = night.entity_seeds.get(mint, frozenset())
    books = window_books(window, owner_of=ents.of, opening=opening, tapes={mint: tape},
                         start=night.start, days=par.window_days, gaps=night.gaps, charged=seeds)  # fmt: skip
    for m in fifo(window, owner_of=ents.of, opening=opening, charged=seeds).matches:
        if m.cost_lamports is not None:
            tallies.w_pnl[m.owner] = (
                tallies.w_pnl.get(m.owner, 0) + m.proceeds_lamports - m.cost_lamports
            )
    excluded: dict[str, list[Episode]] = {}
    for owner, book in books.items():
        tally = tallies.books.setdefault(owner, EntityTally(days=par.window_days))
        excluded[owner] = tally.fold(book, ents.wallets_of(owner), known, night.funded_by, par)
    flows: dict[str, Flow] | None = None  # built once per mint at its first copy, not per copy
    for f in sorted(window, key=decision_order):
        if f.identity not in night.bets:
            continue
        owner = ents.of(f.wallet)
        if _excluded(f, excluded.get(owner, ())):
            continue
        wallets = ents.wallets_of(owner)
        if flows is None:
            flows = {row.wallet: row for row in carry.flows}
        out = simulate_copy(f, leader_wallets=wallets, tape=tape, policy=night.policy,
                            horizon_slot=night.horizon, gaps=night.gaps,
                            leader_prior=flow_totals(flows, wallets), leader_since=night.start)  # fmt: skip
        tallies.copies.setdefault(owner, CopyTally()).add(out)
    return _advance(carry, fills, creates, night)
