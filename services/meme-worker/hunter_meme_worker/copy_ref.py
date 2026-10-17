"""What the copy lane knows of the leader's transaction behind a decision (H-037): the stamp format
(:func:`ms_iso`), :class:`LeaderRef` and the two ways to build one — from an event, or as the stand-in for
the event that was never seen (a pair bought inside a hole). Split from ``copy_events.py`` for the
350-line budget; that module re-exports every name here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.leader_events import LeaderEvent

__all__ = ["LeaderRef", "leader_ref", "ms_iso", "window_ref"]


def ms_iso(value: datetime) -> str:
    """ISO-8601 with millisecond precision — the lane's stamp format."""
    return value.isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class LeaderRef:
    """What we know of the leader's transaction behind a decision (stored on the row)."""

    wallet: str
    stratum: str
    signature: str
    slot: int
    block_time: datetime | None
    observed_at: datetime
    """The event's ``first_seen_at``: our clock when the first leg woke ``recv``."""
    fields_complete_at: datetime
    source: str
    confirmed: bool
    token_delta_atoms: int
    sol_delta_lamports: int | None
    position_after_atoms: int
    kind: str = "unknown"
    multi_mint: bool = False
    server_ts: datetime | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "stratum": self.stratum,
            "signature": self.signature,
            "slot": self.slot,
            "block_time": None if self.block_time is None else ms_iso(self.block_time),
            "observed_at": ms_iso(self.observed_at),
            "first_seen_at": ms_iso(self.observed_at),
            "fields_complete_at": ms_iso(self.fields_complete_at),
            "server_ts": None if self.server_ts is None else ms_iso(self.server_ts),
            "kind": self.kind,
            "multi_mint": self.multi_mint,
            "source": self.source,
            "confirmed_at_decision": self.confirmed,
            "token_delta_atoms": self.token_delta_atoms,
            "sol_delta_lamports": self.sol_delta_lamports,
            "position_after_atoms": self.position_after_atoms,
        }


def leader_ref(event: LeaderEvent, stratum: str) -> LeaderRef:
    return LeaderRef(
        wallet=event.wallet,
        stratum=stratum,
        signature=event.signature,
        slot=event.slot,
        block_time=event.block_time,
        observed_at=event.first_seen_at,
        fields_complete_at=event.fields_complete_at,
        source=event.source,
        confirmed=event.confirmed,
        token_delta_atoms=event.token_delta_atoms,
        sol_delta_lamports=event.sol_delta_lamports,
        position_after_atoms=event.position_after_atoms,
        kind=event.kind,
        multi_mint=event.multi_mint,
        server_ts=event.server_ts,
    )


def window_ref(wallet: str, stratum: str, start: datetime, end: datetime, seq: int) -> LeaderRef:
    """A stand-in for the event that was never seen: the funnel fact of a pair a leader bought **inside a
    hole**, learned from the chain's history afterwards. ``seq`` keeps rows of one window apart in the
    funnel's unique index (rule set, mint, instant)."""
    at = end + timedelta(microseconds=seq)
    return LeaderRef(
        wallet=wallet,
        stratum=stratum,
        signature=f"gap:{start.isoformat()}",
        slot=0,
        block_time=None,
        observed_at=at,
        fields_complete_at=at,
        source="chain",
        confirmed=True,
        token_delta_atoms=0,
        sol_delta_lamports=None,
        position_after_atoms=0,
        kind="unknown",
    )
