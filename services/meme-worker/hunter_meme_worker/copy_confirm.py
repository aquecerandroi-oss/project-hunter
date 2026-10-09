"""What the copy lane remembers about the events it acted on (H-037): which facts it has seen, and which
copies are waiting for their event to be confirmed. In memory, synchronous, no IO — the hot path's.

A **fact** is identified by (signature, wallet, mint, side), not by the signature alone: one transaction
can carry facts about two mints, and the second must not be swallowed as a duplicate of the first.

The lane acts on the first trustworthy signal; this registry is how the late truth reaches the copy:
the same fact arriving confirmed gives a confirmation delay, the same fact arriving confirmed with
**different numbers** is ``divergent``, and a fact still unconfirmed at the timeout is ``not_found``.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.leader_events import LeaderEvent

__all__ = ["Confirmations", "Pending", "Seen", "SeenKey", "seen_key"]

SEEN_MAX = 100_000

SeenKey = tuple[str, str, str, str]
Kind = Literal["entry", "exit"]


def seen_key(event: LeaderEvent) -> SeenKey:
    return (event.signature, event.wallet, event.mint, event.side)


@dataclass(slots=True)
class Seen:
    confirmed: bool
    position_after: int
    token_delta: int
    slot: int


@dataclass(slots=True)
class Pending:
    key: str
    signature: str
    kind: Kind
    deadline: datetime
    first_observed_at: datetime


class Confirmations:
    def __init__(self, timeout_s: int) -> None:
        self._timeout = timedelta(seconds=timeout_s)
        self._seen: OrderedDict[SeenKey, Seen] = OrderedDict()
        self._pending: dict[SeenKey, Pending] = {}

    def get(self, event: LeaderEvent) -> Seen | None:
        return self._seen.get(seen_key(event))

    def remember(self, event: LeaderEvent) -> None:
        self._seen[seen_key(event)] = Seen(
            event.confirmed, event.position_after_atoms, event.token_delta_atoms, event.slot
        )
        while len(self._seen) > SEEN_MAX:
            self._seen.popitem(last=False)

    def expect(self, event: LeaderEvent, key: str, kind: Kind, now: datetime) -> None:
        """A copy was decided on an unconfirmed event: wait for its confirmation, until the timeout."""
        if not event.confirmed:
            self._pending[seen_key(event)] = Pending(
                key, event.signature, kind, now + self._timeout, event.first_seen_at
            )

    def restore(self, pending: Pending, event_key: SeenKey, seen: Seen) -> None:
        """A provisional copy that survived a restart still waits for its confirmation."""
        self._seen[event_key] = seen
        self._pending[event_key] = pending

    def of_fact(self, signature: str, wallet: str, mint: str) -> tuple[Pending, Seen] | None:
        """The copy waiting on a fact named without its side (a ``LeaderConfirmation`` does not carry
        one) — popped, so a repeated confirmation of the same signature is idempotent."""
        for side in ("buy", "sell"):
            skey = (signature, wallet, mint, side)
            pending = self._pending.pop(skey, None)
            seen = self._seen.get(skey)
            if pending is not None and seen is not None:
                seen.confirmed = True
                return pending, seen
        return None

    def confirmed(self, event: LeaderEvent, seen: Seen) -> tuple[Pending, bool] | None:
        """A confirmed copy of a fact already seen unconfirmed: ``(pending, same_numbers)`` when a
        copy was waiting for it, else ``None`` (a plain duplicate)."""
        if not event.confirmed or seen.confirmed:
            return None
        seen.confirmed = True
        pending = self._pending.pop(seen_key(event), None)
        if pending is None:
            return None
        same = (event.position_after_atoms, event.token_delta_atoms, event.slot) == (
            seen.position_after,
            seen.token_delta,
            seen.slot,
        )
        return pending, same

    def expired(self, now: datetime) -> list[Pending]:
        out: list[Pending] = []
        for skey, pending in list(self._pending.items()):
            if pending.deadline <= now:
                del self._pending[skey]
                out.append(pending)
        return out
