"""Where the follow source lost coverage (H-037): the lane's in-memory registry of ``LeaderGap`` spans and
of the **recompositions** a closed hole owes (R2 fix B1/B2).

A gap is an interval ``[start, end)`` of one wallet — or of every wallet when ``wallet`` is ``None`` — and
``end is None`` while it is still open. Not every gap means the same thing (the decision of 09/10, emenda 5):

* ``health`` — a child of the source lost a road (``nats_*``, ``chain_*``) while the other still covers the
  wallet. The source is degraded, **we are not blind**: recorded, and a copy that lives across it is
  flagged, but nothing is censored or rejected.
* ``coverage`` — effective loss: both roads lost (``no_coverage:*``), the lane's own downtime, the source
  that ended. A leader-driven exit of a copy alive across it is censored; entries are rejected.
* ``funnel`` — the database could not take a funnel fact (``funil_indisponivel``): entries are rejected
  (eligibility is not recoverable meanwhile) but an open copy is not blind.

A closed ``coverage`` or ``funnel`` hole owes a **recomposition** per leader: until the chain's history of
that window has been read, the leader has no new entry (:class:`Recompositions`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from hunter_meme_worker.copy_repo_gaps import gap_id

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from hunter_exchanges.pumpfun.leader_events import LeaderGap

__all__ = ["GAPS_MAX", "GapKind", "GapRegistry", "Recompositions", "Window", "classify"]

GAPS_MAX = 200
RETRY_FIRST_S = 5
RETRY_MAX_S = 120

GapKind = Literal["health", "coverage", "funnel"]
FUNNEL_REASON = "funil_indisponivel"


def classify(reason: str) -> GapKind:
    """Unknown reasons are effective loss: the safe reading of a hole nobody named."""
    if reason == FUNNEL_REASON:
        return "funnel"
    if reason.startswith(("nats_", "chain_")):
        return "health"
    return "coverage"


@dataclass(slots=True)
class _Span:
    start: datetime
    end: datetime | None
    kind: GapKind
    reason: str

    def has(self, at: datetime) -> bool:
        return self.start <= at and (self.end is None or at < self.end)


class GapRegistry:
    def __init__(self) -> None:
        self._spans: dict[str | None, list[_Span]] = {}

    def add(self, gap: LeaderGap) -> GapKind:
        kind = classify(gap.reason)
        spans = self._spans.setdefault(gap.wallet, [])
        spans[:] = [s for s in spans if not (s.start == gap.start and s.reason == gap.reason)]
        spans.append(_Span(gap.start, gap.end, kind, gap.reason))
        del spans[:-GAPS_MAX]
        return kind

    def _hit(self, wallet: str, kinds: Iterable[GapKind], instants: tuple[datetime | None, ...]):  # type: ignore[no-untyped-def]
        for key in (wallet, None):
            for span in self._spans.get(key, ()):
                if span.kind in kinds:
                    for at in instants:
                        if at is not None and span.has(at):
                            return span
        return None

    def blocks_entry(self, wallet: str, *instants: datetime | None) -> bool:
        """An instant inside an effective-loss or funnel hole: the entry is not admissible."""
        return self._hit(wallet, ("coverage", "funnel"), instants) is not None

    def blinds(self, wallet: str, *instants: datetime | None) -> bool:
        """An instant inside an effective-loss hole: a leader-driven exit seen there is not trustworthy."""
        return self._hit(wallet, ("coverage",), instants) is not None

    def health_reason(self, wallet: str, *instants: datetime | None) -> str | None:
        span = self._hit(wallet, ("health",), instants)
        return None if span is None else span.reason

    def funnel_starts(self) -> list[datetime]:
        """Every open funnel hole (a fact older than the current one may be lost later)."""
        return [s.start for s in self._spans.get(None, ()) if s.kind == "funnel" and s.end is None]

    def funnel_open(self) -> bool:
        return any(s.kind == "funnel" and s.end is None for s in self._spans.get(None, ()))

    @staticmethod
    def overlaps_life(gap: LeaderGap, opened_by: datetime) -> bool:
        """The gap touches a copy opened at ``opened_by`` that is still alive now."""
        return gap.end is None or gap.end > opened_by


@dataclass(slots=True)
class Window:
    """One leader's slice of a closed hole, owed a read of the chain's history."""

    wallet: str
    start: datetime
    end: datetime
    reason: str
    gap_id: str = ""
    """The hole this slice belongs to (``copy_repo_gaps.gap_id``): the durable key of "recomposed"."""
    tries: int = 0
    next_try: datetime | None = None
    done: bool = False


class Recompositions:
    def __init__(self, wallets: Iterable[str], spec_id: str = "") -> None:
        self._wallets = sorted(wallets)
        self._spec_id = spec_id
        self._windows: list[Window] = []

    def request(self, gap: LeaderGap, done: frozenset[str] = frozenset()) -> None:
        """Owe each leader its slice of a closed hole (``done``: the leaders whose slice is already
        recorded as recomposed - what a restart reads back from the database)."""
        assert gap.end is not None
        targets = self._wallets if gap.wallet is None else [gap.wallet]
        key = gap_id(self._spec_id, gap.wallet, gap.reason, gap.start)
        for wallet in targets:
            if wallet in done or any(
                w.wallet == wallet
                and w.start == gap.start
                and w.end == gap.end
                and w.reason == gap.reason
                for w in self._windows
            ):
                continue
            self._windows.append(Window(wallet, gap.start, gap.end, gap.reason, key))

    def due(self, now: datetime) -> list[Window]:
        return [
            w for w in self._windows if not w.done and (w.next_try is None or w.next_try <= now)
        ]

    def failed(self, window: Window, now: datetime) -> None:
        window.tries += 1
        wait = min(RETRY_MAX_S, RETRY_FIRST_S * 2 ** (window.tries - 1))
        window.next_try = now + timedelta(seconds=wait)

    def finish(self, window: Window) -> None:
        window.done = True
        self._windows = [w for w in self._windows if not w.done]

    def blocked(self, wallet: str) -> bool:
        return any(w.wallet == wallet and not w.done for w in self._windows)

    def pending(self) -> int:
        return len(self._windows)
