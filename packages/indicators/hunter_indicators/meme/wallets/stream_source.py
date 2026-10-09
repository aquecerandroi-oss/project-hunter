"""The input contract of the bounded engine (wave 1c-bis): what a night is streamed.

Split out of :mod:`.stream` (CPU plan step 3) so the per-mint replay of :mod:`.stream_parallel`
workers and the coordinator's passes share one definition of a mint's window and its checks
(:mod:`.carry` states the contract).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from hunter_indicators.meme.wallets.carry import (
    Carry,
    ContractViolation,
    MintCarry,
    canonical_order,
)
from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.snapshot import Snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap, dedupe

__all__ = [
    "MintWindow",
    "StreamInputs",
    "StreamResult",
    "each_mint",
    "prepared",
    "shared_signatures",
]


@dataclass(frozen=True, slots=True)
class MintWindow:
    carry: MintCarry
    fills: tuple[Fill, ...] = ()
    """The mint's events received at or after the window start, in canonical order (later ones
    than the cut are ignored)."""
    creates: tuple[CreateEvent, ...] = ()
    """The mint's ``CreateEvent`` s received at or after the window start."""


def _no_funders() -> Mapping[str, tuple[str, datetime]]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class StreamInputs:
    carry: Carry
    mints: Callable[[], Iterable[MintWindow]]
    """A re-iterable source (read three times): every mint with a carry or a new event, once.
    Completeness is the source's guarantee (an omitted mint cannot be seen from here)."""
    shared_signatures: frozenset[str]
    """Every signature with events in more than one mint of the window (:func:`shared_signatures`);
    the tx fee goes to the owner's first event of the transaction across mints. REQUIRED, no
    default: "none shared" must be said, not assumed. Completeness is the storage's guarantee —
    one mint at a time cannot see an omission, and an omitted one charges the fee twice."""
    links: tuple[Link, ...] = ()
    funders: Mapping[str, tuple[str, datetime]] = field(default_factory=_no_funders)
    gaps: tuple[Gap, ...] = ()


@dataclass(frozen=True, slots=True)
class StreamResult:
    snapshot: Snapshot
    carry: Carry
    """The global carry at the next window start (``boundary + 1 day``)."""
    mint_carries: tuple[MintCarry, ...]
    """The non-empty per-mint carries at the next window start."""


def shared_signatures(fills: Iterable[Fill]) -> frozenset[str]:
    first: dict[str, str] = {}
    shared: set[str] = set()
    for f in fills:
        if first.setdefault(f.signature, f.mint) != f.mint:
            shared.add(f.signature)
    return frozenset(shared)


def prepared(
    window: MintWindow, sealed_until: datetime, start: datetime, cut: datetime
) -> tuple[Fill, ...]:
    """The mint's causal events from the window start on, folded like ``dedupe``, contract-checked."""
    mint = window.carry.mint
    if any(f.mint != mint for f in window.fills) or any(c.mint != mint for c in window.creates):
        raise ValueError(f"an event of another mint in the window of {mint}")
    early = next((f for f in window.fills if f.received_at < start), None)
    if early is not None:  # already in the carry: it would be counted twice (Astra, diff review)
        raise ContractViolation(
            "received_before_window", f"{early.signature}/{early.event_ordinal}"
        )
    fills = tuple(
        sorted(dedupe(f for f in window.fills if f.received_at < cut), key=canonical_order)
    )
    times: dict[int, datetime] = {}
    for f in (*window.carry.frontier, *fills):
        if f.received_at < f.block_time:
            raise ContractViolation("received_before_mined", f"{f.signature}/{f.event_ordinal}")
        if f.block_time < start and f.received_at >= sealed_until:
            raise ContractViolation("late_beyond_seal", f"{f.signature}/{f.event_ordinal}")
        if times.setdefault(f.slot, f.block_time) != f.block_time:
            raise ContractViolation("slot_time_inconsistent", f"{mint} slot {f.slot}")
    ordered = sorted(times.items())
    if any(b[1] < a[1] for a, b in zip(ordered, ordered[1:], strict=False)):
        raise ContractViolation("slot_time_inconsistent", f"{mint}: time decreases with the slot")
    return fills


def each_mint(inputs: StreamInputs) -> Iterable[MintWindow]:
    """One pass over the source, refusing a mint seen twice (it would be replayed twice)."""
    seen: set[str] = set()
    for window in inputs.mints():
        if window.carry.mint in seen:
            raise ContractViolation("repeated_mint", window.carry.mint)
        seen.add(window.carry.mint)
        yield window
