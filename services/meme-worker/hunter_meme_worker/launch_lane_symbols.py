"""The launch lane's own, cheap answer to "is this a ticker clone" (T4.67a):
a bounded, in-memory memory of every symbol the lane has seen created in the
last 60 seconds — never a database read (``pedigree.py``'s own
``symbol_dup_24h`` is the 24-hour, DB-backed version of the same idea; the
launch lane cannot afford its round trip inside a 200 ms budget).

Pure, no clock of its own: every call is handed ``at``. Bounded by time alone
(``window_s``); a process that sees no creates for a while empties on its own,
never growing past the last minute of traffic.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

__all__ = ["RecentSymbols", "normalize_symbol"]

WINDOW_S = 60


def normalize_symbol(symbol: str) -> str:
    """Case and surrounding whitespace are not identity (``pump`` vs
    ``PUMP `` are the same ticker) — the same normalisation a human comparing
    two tickers by eye would apply, and nothing more (no unicode folding, no
    stripping of punctuation: a clone that changes punctuation to dodge this
    check is a question for the 24-hour DB-backed criterion, not this one)."""
    return symbol.strip().casefold()


@dataclass(slots=True)
class RecentSymbols:
    """A deque of ``(created_at, normalized_symbol)``, oldest first — pruned by
    time on every read and every write, so it never holds more than a window's
    worth of creates."""

    window_s: int = WINDOW_S
    _seen: deque[tuple[datetime, str]] = field(
        default_factory=lambda: deque[tuple[datetime, str]]()
    )

    def _prune(self, at: datetime) -> None:
        horizon = at - timedelta(seconds=self.window_s)
        while self._seen and self._seen[0][0] < horizon:
            self._seen.popleft()

    def is_recent_clone(self, symbol: str, at: datetime) -> bool:
        """``True`` when a mint with the same (normalized) symbol was observed
        created within :attr:`window_s` seconds before ``at`` — never counting
        ``at`` itself, so a mint is never its own clone."""
        self._prune(at)
        normalized = normalize_symbol(symbol)
        return any(seen == normalized for _, seen in self._seen)

    def observe(self, symbol: str, at: datetime) -> None:
        """Record this create so the *next* one can compare against it. Called
        unconditionally — a clone that itself gets refused is still evidence
        for the next arrival within the window."""
        self._seen.append((at, normalize_symbol(symbol)))
        self._prune(at)

    def __len__(self) -> int:
        return len(self._seen)
