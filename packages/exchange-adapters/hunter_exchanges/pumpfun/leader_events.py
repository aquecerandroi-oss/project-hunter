"""Contract of the paper copy-trade pilot (H-037, decision 2026-10-09): what a followed wallet did.

This module is the **interface only**, written first so the source (NATS + on-chain fallback), the
leader selection and the meme-worker copy lane can be built in parallel against one shape. Pure:
no IO, no clock.

* :class:`LeaderEvent` — one confirmed change of a followed wallet's position in one mint, already
  cross-checked against the chain by signature (``confirmed=True``) or explicitly not
  (``confirmed=False``, the lane must not open or close a copy on it).
* :class:`LeaderGap` — the source lost coverage of a wallet for an interval (credential rotated,
  socket down, fallback lagging). The lane records it; a copy whose entry or exit falls inside a gap
  is censored, never priced by guess.
* :class:`LeaderSource` — what the copy lane consumes: an async stream of events and gaps for a
  frozen set of wallets.

Money is ``int`` atoms / lamports, time is UTC-aware, never ``float``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

Side = Literal["buy", "sell"]
Source = Literal["nats", "chain"]


def _require_utc(name: str, value: datetime) -> None:
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{name} must be UTC-aware, got {value!r}")


@dataclass(frozen=True, slots=True)
class LeaderEvent:
    """A followed wallet bought or sold ``mint`` in transaction ``signature``.

    ``token_delta_atoms`` is the wallet's token balance change (positive on a buy, negative on a
    sell); ``sol_delta_lamports`` its SOL change in the same transaction (negative on a buy), both
    as observed. ``position_after_atoms`` is the wallet's token balance after the transaction, so the
    lane can tell a partial sell from a full exit. ``observed_at`` is when **we** saw it (the copy's
    latency starts here); ``block_time`` is the chain's.
    """

    wallet: str
    mint: str
    side: Side
    token_delta_atoms: int
    sol_delta_lamports: int
    position_after_atoms: int
    signature: str
    slot: int
    block_time: datetime | None
    observed_at: datetime
    source: Source
    confirmed: bool

    def __post_init__(self) -> None:
        _require_utc("observed_at", self.observed_at)
        if self.block_time is not None:
            _require_utc("block_time", self.block_time)
        if self.side == "buy" and self.token_delta_atoms <= 0:
            raise ValueError("a buy must increase the token balance")
        if self.side == "sell" and self.token_delta_atoms >= 0:
            raise ValueError("a sell must decrease the token balance")
        if self.position_after_atoms < 0 or self.slot < 0:
            raise ValueError("position and slot cannot be negative")


@dataclass(frozen=True, slots=True)
class LeaderGap:
    """Coverage of ``wallet`` (or of every wallet when ``wallet`` is None) was lost in
    [``start``, ``end``); ``end`` is None while the gap is still open."""

    wallet: str | None
    start: datetime
    end: datetime | None
    reason: str

    def __post_init__(self) -> None:
        _require_utc("start", self.start)
        if self.end is not None:
            _require_utc("end", self.end)
            if self.end < self.start:
                raise ValueError("a gap cannot end before it starts")
        if not self.reason:
            raise ValueError("a gap needs a named reason")


class LeaderSource(Protocol):
    """What the copy lane consumes. Implementations: the NATS per-wallet channel with the mandatory
    on-chain fallback (decision 2026-10-06), and an in-memory fake for tests."""

    def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderEvent | LeaderGap]: ...
