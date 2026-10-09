"""Contract of the paper copy-trade pilot (H-037, decision 2026-10-09): what a followed wallet did.

Amended by task 0b (docs/design/copiar-carteiras-papel.md section 2.3). This module is the **interface
only**, shared by the source (NATS + on-chain fallback), the leader selection and the meme-worker copy
lane. Pure: no IO, no clock.

* :class:`LeaderEvent` — a change of a followed wallet's position in one mint, **as soon as the first
  trustworthy signal exists**. A NATS event is provisional (``confirmed=False``); the lane may open and
  close a copy on it **when the evidence of section 2.1 holds** (token up with SOL down by at least the
  floor, not ``multi_mint``). A missing leg is ``None``, never a guessed zero.
* :class:`LeaderConfirmation` — the asynchronous chain check of one earlier event, with the five states
  of the design. It never rewrites the event: a leg that arrives after the decision only updates a
  diagnostic, and a repeated confirmation of the same signature is idempotent for the consumer.
* :class:`LeaderGap` — the source lost coverage of a wallet for an interval (credential rotated, socket
  down, fallback lagging). The lane records it; a copy whose entry or exit falls inside a gap is
  censored, never priced by guess.
* :class:`LeaderSource` — what the copy lane consumes: an async stream of the three, for a frozen set of
  wallets.

Money is ``int`` atoms / lamports, time is UTC-aware, never ``float``. Stamps (all UTC, millisecond
meaning, microsecond storage): ``server_ts`` (NATS server), ``first_seen_at`` (our clock when the first
leg woke ``recv``, before parsing), ``fields_complete_at`` (when the observation was resolved: the
legs it needed arrived, **or the 300 ms pairing wait ran out with the SOL leg still ``None``** — so it
is not by itself evidence that the SOL leg is known), ``block_time`` (the chain's, only from the chain), ``confirmed_at`` (local reception of the
confirmation result, timeouts included — not a block time).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, get_args

Side = Literal["buy", "sell"]
Source = Literal["nats", "chain"]
Kind = Literal["unknown", "swap", "transfer"]
"""``unknown``: the source could not tell a swap from a transfer (the default of a NATS event);
``swap``: a swap event attributed to the wallet was read on chain; ``transfer``: the source knows tokens
left (or arrived) without the SOL side of a swap. For the exit only the observed position matters."""
Venue = Literal["curve", "pool"]
ConfirmationStatus = Literal["confirmed", "divergent", "failed_tx", "not_found", "rpc_error"]


def _require_utc(name: str, value: datetime) -> None:
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{name} must be UTC-aware, got {value!r}")


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int, got {value!r}")


@dataclass(frozen=True, slots=True)
class LeaderEvent:
    """A followed wallet's position in ``mint`` changed in transaction ``signature``.

    ``token_delta_atoms`` is the token balance change (positive on a buy, negative on a sell);
    ``sol_delta_lamports`` the SOL change of the same transaction (negative on a buy; network fee and
    rent included — what the wallet spent, not the swap price), or ``None`` while the SOL leg is unknown
    or cannot be attributed (``multi_mint``). ``position_after_atoms`` is the token balance after the
    transaction, so the lane can tell a partial sell from a full exit.

    ``multi_mint=False`` means "no other mint known in this transaction at this instant", not proof of
    absence; ``multi_mint=True`` forces ``sol_delta_lamports=None`` (one SOL debit is not N debits).
    """

    wallet: str
    mint: str
    side: Side
    token_delta_atoms: int
    sol_delta_lamports: int | None
    position_after_atoms: int
    signature: str
    slot: int
    block_time: datetime | None
    first_seen_at: datetime
    fields_complete_at: datetime
    source: Source
    confirmed: bool
    server_ts: datetime | None = None
    multi_mint: bool = False
    kind: Kind = "unknown"

    def __post_init__(self) -> None:
        _require_utc("first_seen_at", self.first_seen_at)
        _require_utc("fields_complete_at", self.fields_complete_at)
        if self.fields_complete_at < self.first_seen_at:
            raise ValueError("fields_complete_at cannot precede first_seen_at")
        for name, value in (("block_time", self.block_time), ("server_ts", self.server_ts)):
            if value is not None:
                _require_utc(name, value)
        for name, closed in (("side", get_args(Side)), ("source", get_args(Source))):
            if getattr(self, name) not in closed:
                raise ValueError(f"unknown {name} {getattr(self, name)!r}")
        for name in ("token_delta_atoms", "position_after_atoms", "slot"):
            _require_int(name, getattr(self, name))
        if self.sol_delta_lamports is not None:
            _require_int("sol_delta_lamports", self.sol_delta_lamports)
        if self.multi_mint and self.sol_delta_lamports is not None:
            raise ValueError("a multi_mint event cannot carry one sol_delta_lamports")
        if self.kind not in get_args(Kind):
            raise ValueError(f"unknown kind {self.kind!r}")
        if self.side == "buy" and self.token_delta_atoms <= 0:
            raise ValueError("a buy must increase the token balance")
        if self.side == "sell" and self.token_delta_atoms >= 0:
            raise ValueError("a sell must decrease the token balance")
        if self.position_after_atoms < 0 or self.slot < 0:
            raise ValueError("position and slot cannot be negative")

    @property
    def observed_at(self) -> datetime:
        """Deprecated alias of ``first_seen_at`` (the pre-0b name); new code reads ``first_seen_at``."""
        return self.first_seen_at


@dataclass(frozen=True, slots=True)
class PostReserves:
    """The market's reserves right after the leader's trade (the "ideal" price of section 3.3), as the
    swap event reports them. Curve: virtual reserves; pool: the pool's quote/base after the trade, with
    ``virtual_quote_reserves`` for boosted pools (KB-0184 item 3)."""

    venue: Venue
    sol_reserves: int
    token_reserves: int
    virtual_quote_reserves: int | None
    real_sol_reserves: int | None

    def __post_init__(self) -> None:
        if self.venue not in get_args(Venue):
            raise ValueError(f"unknown venue {self.venue!r}")
        for name, value in (
            ("sol_reserves", self.sol_reserves),
            ("token_reserves", self.token_reserves),
            ("real_sol_reserves", self.real_sol_reserves),
        ):
            if value is None and name == "real_sol_reserves":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"reserves must be non-negative ints, got {name}={value!r}")
        virtual = self.virtual_quote_reserves  # PumpSwap's is an i128: negative is legal
        if virtual is not None:
            _require_int("virtual_quote_reserves", virtual)


@dataclass(frozen=True, slots=True)
class LeaderConfirmation:
    """The chain's verdict on one earlier :class:`LeaderEvent` ``(wallet, signature, mint)``.

    ``confirmed``: wallet, mint, side, amount and slot match; ``divergent``: some field does not
    (``reason`` names it; ``chain_*`` carry the chain's own numbers); ``failed_tx``: the transaction
    failed on chain; ``not_found``: still unseen after the retries — **not** a claim that the
    transaction was false; ``rpc_error``: the node did not answer (``reason`` records why).
    """

    wallet: str
    mint: str
    signature: str
    slot: int
    status: ConfirmationStatus
    reason: str | None
    confirmed_at: datetime
    block_time: datetime | None
    post_reserves: PostReserves | None = None
    chain_token_delta_atoms: int | None = None
    chain_position_after_atoms: int | None = None

    def __post_init__(self) -> None:
        if self.status not in get_args(ConfirmationStatus):
            raise ValueError(f"unknown status {self.status!r}")
        _require_utc("confirmed_at", self.confirmed_at)
        if self.block_time is not None:
            _require_utc("block_time", self.block_time)
        _require_int("slot", self.slot)
        if self.slot < 0:
            raise ValueError("slot cannot be negative")
        if self.status == "confirmed" and self.reason is not None:
            raise ValueError("a confirmed confirmation carries no reason")
        if self.status != "confirmed" and not self.reason:
            raise ValueError(f"a {self.status} confirmation needs a named reason")
        if self.post_reserves is not None and self.status not in ("confirmed", "divergent"):
            raise ValueError("post_reserves only come with a transaction that was read")
        for name, value in (
            ("chain_token_delta_atoms", self.chain_token_delta_atoms),
            ("chain_position_after_atoms", self.chain_position_after_atoms),
        ):
            if value is not None:
                _require_int(name, value)
        if self.chain_position_after_atoms is not None and self.chain_position_after_atoms < 0:
            raise ValueError("chain_position_after_atoms cannot be negative")


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


LeaderItem = LeaderEvent | LeaderGap | LeaderConfirmation


class LeaderSource(Protocol):
    """What the copy lane consumes. Implementations: the NATS per-wallet channel with the mandatory
    on-chain fallback (decision 2026-10-06), and an in-memory fake for tests."""

    def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderItem]: ...
