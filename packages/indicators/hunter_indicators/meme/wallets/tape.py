"""The wallet tape as the engine sees it: one decoded event per :class:`Fill`.

Units are integers at the boundary (lamports, token atoms); Decimal only appears
where a price is computed (:mod:`.pricing`). Every time is timezone-aware UTC.

Two clocks travel with every event (design §2.1): ``block_time`` (when the chain
says it happened, whole seconds) and ``received_at`` (when our collector had it).
An event is usable at an instant ``t`` only when **both** are ``< t`` —
:func:`causal_view` is the one place that rule is written.

Money semantics of a :class:`Fill`: ``sol_lamports`` is the SOL leg **gross of
the fees the event declares** and ``fee_lamports`` is those fees, so a buy costs
``sol + fee`` and a sell nets ``sol − fee``. An adapter that maps a PumpSwap
``SellEvent`` must therefore put ``quote_amount_out`` (gross) here, never
``net_proceeds`` (already net) — otherwise the fee is taken twice (§3.1).
:mod:`.bridge` maps the adapter's ``SwapRecord`` (same semantics) into a ``Fill``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

__all__ = [
    "LAMPORTS_PER_SOL",
    "TOKEN_ATOMS_PER_TOKEN",
    "CreateEvent",
    "Fill",
    "Gap",
    "Reserves",
    "Side",
    "Venue",
    "causal_view",
    "dedupe",
    "event_order",
    "touches_gap",
]

LAMPORTS_PER_SOL: Final = 1_000_000_000
TOKEN_ATOMS_PER_TOKEN: Final = 1_000_000
"""pump.fun mints carry 6 decimals (1e15 atoms per 1e9 supply, T4.0/T4.1)."""

Venue = Literal["curve", "pool"]
Side = Literal["buy", "sell"]


def _utc(value: datetime, what: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{what} must be UTC-aware")


@dataclass(frozen=True, slots=True)
class Reserves:
    """The post-trade state the event reports.

    Curve: ``sol_lamports``/``token_atoms`` are the *virtual* reserves and
    ``real_sol_lamports`` is the vault (the ceiling of any sale, ``curve.py``
    T4.27) — mandatory on the curve. Pool: ``sol_lamports`` is the REAL quote
    (WSOL vault, the ceiling of any sale) and ``virtual_quote_lamports`` the
    pool's signed virtual quote: the pool is priced on their sum
    (:attr:`effective_quote_lamports`, KB-0184 item 3), which must be positive.
    """

    venue: Venue
    sol_lamports: int
    token_atoms: int
    real_sol_lamports: int | None
    complete: bool = False
    """The curve program's own completion flag (migration); never derived here."""
    virtual_quote_lamports: int = 0
    """PumpSwap ``virtual_quote_reserves`` (i128, may be negative); ``0`` on the curve."""

    def __post_init__(self) -> None:
        if self.sol_lamports <= 0 or self.token_atoms <= 0:
            raise ValueError("reserves must be positive")
        if self.venue == "curve" and self.real_sol_lamports is None:
            raise ValueError("a curve state needs its real SOL (the sale ceiling)")
        if self.venue == "curve" and self.virtual_quote_lamports != 0:
            raise ValueError("a curve state has no separate virtual quote")
        if self.effective_quote_lamports <= 0:
            raise ValueError("the pool's effective quote (real + virtual) must be positive")

    @property
    def effective_quote_lamports(self) -> int:
        """The quote side of the constant product: real + virtual (the curve's is virtual already)."""
        return self.sol_lamports + self.virtual_quote_lamports


@dataclass(frozen=True, slots=True)
class Fill:
    """One decoded trade event. Identity = ``(signature, program, event_ordinal)``."""

    signature: str
    program: str
    event_ordinal: int
    slot: int
    block_time: datetime
    received_at: datetime
    wallet: str
    mint: str
    venue: Venue
    side: Side
    sol_lamports: int
    token_atoms: int
    fee_lamports: int
    fee_bps: int
    """Total fee of the event in basis points — the rate our simulated trade pays."""
    reserves: Reserves
    lp_fee_lamports: int = 0
    """The part of ``fee_lamports`` that stays in a pool (PumpSwap LP fee): the vault moves by
    ``sol + lp`` on a buy and ``sol − lp`` on a sale. ``0`` on the curve."""

    def __post_init__(self) -> None:
        _utc(self.block_time, "block_time")
        _utc(self.received_at, "received_at")
        if self.sol_lamports < 0 or self.token_atoms <= 0 or self.fee_lamports < 0:
            raise ValueError("a fill moves a positive token amount and non-negative SOL")
        if not 0 <= self.fee_bps < 10_000:
            raise ValueError("fee_bps out of range")
        if not 0 <= self.lp_fee_lamports <= self.fee_lamports or (
            self.reserves.venue == "curve" and self.lp_fee_lamports
        ):
            raise ValueError("the lp fee is part of the declared fees, and only in a pool")

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self.signature, self.program, self.event_ordinal)


@dataclass(frozen=True, slots=True)
class CreateEvent:
    """A mint's ``CreateEvent``: who created it, and when we knew."""

    mint: str
    creator: str
    slot: int
    block_time: datetime
    received_at: datetime


@dataclass(frozen=True, slots=True)
class Gap:
    """A coverage hole of the collector, in slots, inclusive on both ends."""

    start_slot: int
    end_slot: int

    def __post_init__(self) -> None:
        if self.end_slot < self.start_slot:
            raise ValueError("a gap ends at or after it starts")


def event_order(fill: Fill) -> tuple[int, str, int]:
    """Deterministic order: slot, then signature, then ordinal.

    The intra-slot order of transactions is **not** known from the logs feed;
    this key only makes runs reproducible. Pricing never relies on it — a
    landing slot is priced at the worst of all its states (:mod:`.pricing`).
    """
    return (fill.slot, fill.signature, fill.event_ordinal)


def dedupe(fills: Iterable[Fill]) -> tuple[Fill, ...]:
    """One event per identity — the same tx seen by both subscriptions counts once.

    The copy kept is the earliest received (the one we could have acted on).
    """
    kept: dict[tuple[str, str, int], Fill] = {}
    for f in fills:
        seen = kept.get(f.identity)
        if seen is None or f.received_at < seen.received_at:
            kept[f.identity] = f
    return tuple(sorted(kept.values(), key=event_order))


def causal_view(fills: Iterable[Fill], cut: datetime) -> tuple[Fill, ...]:
    """Only what was both mined and received strictly before ``cut``, in order."""
    _utc(cut, "cut")
    return tuple(
        sorted((f for f in fills if f.block_time < cut and f.received_at < cut), key=event_order)
    )


def touches_gap(first_slot: int, last_slot: int, gaps: Iterable[Gap]) -> bool:
    """``True`` when ``[first_slot, last_slot]`` intersects any gap (contamination)."""
    return any(g.start_slot <= last_slot and first_slot <= g.end_slot for g in gaps)
