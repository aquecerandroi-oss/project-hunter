"""Bounded memory of the executor's obligations (H-037, R2 fix B6): how many times each job was tried, and
what was already **priced** for it. Both are keyed by the job's own ``oid`` — one obligation, one budget —
and both are bounded, so a long outage cannot grow them without limit.

A job that fails after it was priced is redelivered with the *same* price: a failure of the database
must not swap the photograph (and so the economic result) of a sale or a fill.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hunter_meme_worker.lab_models import BetEntry, BetExit

__all__ = ["CAP", "Held", "PricedEntry", "PricedExit", "Retries"]

CAP = 10_000


class Retries:
    def __init__(self, cap: int = CAP) -> None:
        self._cap = cap
        self._tries: OrderedDict[str, int] = OrderedDict()

    def bump(self, oid: str) -> int:
        n = self._tries.pop(oid, 0) + 1
        self._tries[oid] = n
        while len(self._tries) > self._cap:
            self._tries.popitem(last=False)
        return n

    def clear(self, oid: str) -> None:
        self._tries.pop(oid, None)

    def __len__(self) -> int:
        return len(self._tries)


class Held[T]:
    """What was decided/priced for an obligation, until it lands or is given up."""

    def __init__(self, cap: int = CAP) -> None:
        self._cap = cap
        self._items: OrderedDict[str, T] = OrderedDict()

    def get(self, oid: str) -> T | None:
        return self._items.get(oid)

    def put(self, oid: str, value: T) -> None:
        self._items[oid] = value
        while len(self._items) > self._cap:
            self._items.popitem(last=False)

    def drop(self, oid: str) -> None:
        self._items.pop(oid, None)

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True, slots=True)
class PricedExit:
    closed: BetExit
    mark_source: str | None
    censor: str | None


@dataclass(frozen=True, slots=True)
class PricedEntry:
    """The outcome of pricing an open: a fill, a mint found on the pool, or a named refusal."""

    kind: str  # "fill" | "venue" | "censor"
    entry: BetEntry | None = None
    mayhem: bool | None = None
    slot: int = 0
    reason: str | None = None
