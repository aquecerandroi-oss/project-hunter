"""What one night hands to the next (wave 1c-bis): the state at a window start ``S``.

Why a carry, and not "the new day + accumulators": the snapshot of day D applies D's entity map
to the whole window, starts from the per-**wallet** lots at ``S`` and restarts the trigger ledger
in every window, so a day's contribution depends on the window it sits in (twin A buys 100 and
twin B sells 100 on day ``S``: inside the window that starts at ``S`` the entity is flat; in the
next one the wallet lots give 100 open). The exact bounded form is therefore a nightly replay of
the window **one mint at a time** (:mod:`.stream`) on top of this carry, which only holds what the
window cannot see and does not depend on where the window starts (Astra, wallets-1c-bis).

Two clocks (Astra must-fix 1), never mixed:

- **economic, by ``block_time``** — per-wallet FIFO lots and the weak-link evidence cover every
  event mined before ``S``; they are *sealed* later, once no such event can still arrive;
- **reception, by ``received_at``** — the frontier (the events of the highest slot received
  before ``S``: :meth:`.pricing.MintTape.valid_states_at`), each wallet's bought/sold totals in the
  mint (``policy._leader_exit`` reads the leader's whole history there), the highest slot
  received and the earliest received ``CreateEvent``.

The contract this equivalence holds under has two kinds of conditions.

**Checked locally by :mod:`.stream`, refused by name** (:class:`ContractViolation`):

- **P1 seal** — an event mined before ``S`` is received before :attr:`Carry.sealed_until`;
- **P2** — ``received_at ≥ block_time``; **P3** — one ``block_time`` per slot, never decreasing
  with the slot in a mint;
- a window holds only events received at or after ``S``; each mint appears once per pass; the
  carry belongs to this window start; the settle horizon does not reach before ``S``;
- parallel replay: a worker's window has the mint name and the event count the survey saw
  (``fetch_mismatch`` — a sanity check, not a proof of the guarantee below).

**Guaranteed by the source (storage), NOT checkable one mint at a time** — a breach is silent:

- each identity is delivered once across nights (design §9.6.4); within a night duplicates are
  folded exactly like :func:`.tape.dedupe`;
- an identity belongs to ONE mint: the same ``(signature, program, ordinal)`` in two mints is a
  conflicting event, and the per-mint bets (step 3) would keep it in one of them only, where the
  batch kept both (code review, step 3: reproduced with fabricated input, not with a real tape);
- the source is complete: every mint with a new event **or a carry** (an omitted carried mint
  loses its lots, frontier and totals);
- ``shared_signatures`` lists every signature with events in more than one mint;
- the carry handed in is the one the previous night produced (it is trusted, not re-verified);
- parallel replay: the source is immutable for the run — the three passes and every worker's
  ``fetch(name)`` see the same window, carry and creates of each mint (Astra, step 3 design).

Events come in :func:`canonical_order` and opening lots in :func:`lot_order` (a deterministic
convention for ties, not the economic order between wallets, which the feed does not know).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal

from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill

__all__ = [
    "Carry",
    "ContractViolation",
    "Evidence",
    "Flow",
    "MintCarry",
    "Violation",
    "canonical_order",
    "flow_totals",
    "initial_carry",
    "lot_order",
    "merge_evidence",
    "sort_lots",
]

Evidence = tuple[tuple[datetime, str], ...]
"""A wallet pair's same-slot co-buys: the ≤ 3 smallest ``(known_at, mint)``, per-mint minimum."""
Violation = Literal[
    "late_beyond_seal",
    "received_before_mined",
    "slot_time_inconsistent",
    "carry_mismatch",
    "lot_after_origin",
    "settle_beyond_window",
    "received_before_window",
    "repeated_mint",
    "fetch_mismatch",
]
_WEAK_MINTS = 3


class ContractViolation(ValueError):
    """The input breaks the contract the equivalence holds under: never publish around it."""

    def __init__(self, reason: Violation, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason: Violation = reason
        self.detail = detail

    def __reduce__(self) -> tuple[type[ContractViolation], tuple[Violation, str]]:
        """Rebuilt by name when it crosses a process boundary (parallel replay, step 3)."""
        return (ContractViolation, (self.reason, self.detail))


def canonical_order(f: Fill) -> tuple[datetime, int, str, int, str]:
    """Input order of events: arrival, then the identity. :func:`.tape.event_order` ties (same
    slot, signature and ordinal, other program) are broken by it, in both engines."""
    return (f.received_at, f.slot, f.signature, f.event_ordinal, f.program)


def lot_order(lot: Lot) -> tuple[int, datetime, str]:
    """Opening-lot order: FIFO position, then the wallet (a stable sort keeps book order)."""
    return (lot.opened_slot, lot.opened_at, lot.owner)


def sort_lots(lots: Iterable[Lot]) -> tuple[Lot, ...]:
    return tuple(sorted(lots, key=lot_order))


@dataclass(frozen=True, slots=True)
class Flow:
    """A wallet's atoms bought and sold in one mint, over the events received before ``S``."""

    wallet: str
    bought_atoms: int
    sold_atoms: int


@dataclass(frozen=True, slots=True)
class MintCarry:
    """The per-mint part of the carry (streamed with the mint's window, never all at once)."""

    mint: str
    frontier: tuple[Fill, ...] = ()
    """Every event of the highest slot received before ``S`` (canonical order)."""
    lots: tuple[Lot, ...] = ()
    """Per-wallet FIFO lots open over the events mined before ``S`` (``owner`` = wallet)."""
    flows: tuple[Flow, ...] = ()
    """Sorted by wallet; one row per wallet that ever traded the mint — closed ones included."""
    create: CreateEvent | None = None
    """The earliest received ``CreateEvent`` received before ``S``."""

    @property
    def empty(self) -> bool:
        return not (self.frontier or self.lots or self.flows or self.create)

    def flow_of(self, wallets: Iterable[str]) -> tuple[int, int]:
        return flow_totals({f.wallet: f for f in self.flows}, wallets)


def flow_totals(rows: Mapping[str, Flow], wallets: Iterable[str]) -> tuple[int, int]:
    """(bought, sold) atoms of ``wallets`` from a wallet → flow index. A replay builds the index
    once per mint, not once per copy (CPU plan step 2)."""
    hits = [rows[w] for w in wallets if w in rows]
    return sum(f.bought_atoms for f in hits), sum(f.sold_atoms for f in hits)


def _no_pairs() -> Mapping[tuple[str, str], Evidence]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Carry:
    """The global part of the carry at the window start ``boundary``."""

    boundary: datetime
    sealed_until: datetime
    """Events received before this instant are in the economic seal (lots, weak evidence)."""
    window_days: int = 7
    max_slot: int = -1
    """Highest slot among the events received before ``boundary`` (the horizon's floor)."""
    weak_links: tuple[Link, ...] = ()
    """Pairs whose sealed evidence already reached 3 mints (final: evidence only grows)."""
    pending: Mapping[tuple[str, str], Evidence] = field(default_factory=_no_pairs)
    """Pairs with 1–2 sealed co-bought mints. No rule lets them be pruned (Astra)."""

    def check(self, start: datetime, window_days: int) -> None:
        if self.boundary != start or self.window_days != window_days:
            raise ContractViolation(
                "carry_mismatch",
                f"carry at {self.boundary.isoformat()}/{self.window_days}d, "
                f"window at {start.isoformat()}/{window_days}d",
            )


def merge_evidence(old: Evidence, new: Mapping[str, datetime]) -> Evidence:
    """Per-mint minimum of both, then the 3 smallest ``(known_at, mint)`` — exact for the 3rd."""
    best = {mint: known for known, mint in old}
    for mint, known in new.items():
        if mint not in best or known < best[mint]:
            best[mint] = known
    return tuple(sorted((k, m) for m, k in best.items())[:_WEAK_MINTS])


def initial_carry(
    origin: datetime, preserved: Iterable[Lot] = (), *, window_days: int = 7
) -> tuple[Carry, tuple[MintCarry, ...]]:
    """The carry of a campaign whose collector starts at ``origin`` (the first window start).

    Nothing is known before ``origin`` except the ``preserved`` per-wallet lots (cost may be
    unknown); an event mined before it can never be sealed (``sealed_until = origin``).
    """
    by_mint: dict[str, list[Lot]] = {}
    for lot in preserved:
        if lot.opened_at >= origin:
            raise ContractViolation("lot_after_origin", f"{lot.owner}/{lot.mint}")
        by_mint.setdefault(lot.mint, []).append(lot)
    mints = tuple(MintCarry(m, lots=sort_lots(lots)) for m, lots in sorted(by_mint.items()))
    return Carry(origin, origin, window_days), mints
