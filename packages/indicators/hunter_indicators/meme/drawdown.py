"""The recent drawdown of a curve's **real SOL** — the "do not buy after the
fall" guard of EXP-M13 (KB-0118), as a pure fold that costs O(1) amortized
per event (T4.52b-2).

``dd = 1 − current / peak`` where ``peak = max(real_sol_reserves)`` over
``[as_of − window_s, as_of]`` and ``current`` is the newest observation at or
before ``as_of``. The reserve is the chain's ``real_sol_reserves``, **never**
``mcap_sol``: a Mayhem coin's market cap is rewritten by the agent's virtual
SOL and drops below the empty-curve floor (KB-0115 §1.3), while the real SOL
is what actually left the curve.

Two unknowns, each named, both read by the gate as ``recent_drawdown_unknown``
(EXP-M13's fail-closed clause — a filter that reads a missing photo as "no
fall" is coverage noise, not a criterion):

- ``no_observation`` — nothing reached us by ``as_of``;
- ``stale`` — the newest observation is older than ``max_gap_s``.

**Non-anticipation is decided here.** Every point carries ``received_at``; a
point received after ``as_of`` is not an input of that instant, however early
its ``observed_at``. Over a plain sequence the fold filters and is O(n); over a
:class:`PeakDeque` — the monotonic deque an event state keeps up to date — it
is O(1) amortized, valid exactly when every point in the deque had reached us
by ``as_of`` (``PeakDeque.received_by``), which is the event gate's case: it
judges at the instant of the newest event.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final, NamedTuple

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "DEFAULT_MAX_GAP_S",
    "DEFAULT_WINDOW_S",
    "DRAWDOWN_DEFINITION",
    "DRAWDOWN_REASONS",
    "NO_OBSERVATION",
    "STALE",
    "PeakDeque",
    "RecentDrawdown",
    "ReservePoint",
    "recent_drawdown",
]

DEFAULT_WINDOW_S: Final = 60
DEFAULT_MAX_GAP_S: Final = 30
"""EXP-M13's frozen ``N = 60 s`` and the 30 s fail-closed staleness bound."""

NO_OBSERVATION: Final = "no_observation"
STALE: Final = "stale"
DRAWDOWN_REASONS: Final = frozenset({NO_OBSERVATION, STALE})

_FRACTION = Decimal("0.000001")
_SECONDS = Decimal("0.001")

DRAWDOWN_DEFINITION: Final = FeatureDefinition(
    key="recent_drawdown_pct",
    version=1,
    category=FeatureCategory.PRICE,
    inputs=(
        "meme_curve_snapshots.real_sol_reserves",
        "meme_curve_snapshots.observed_at",
        "meme_curve_snapshots.received_at",
        "solana_rpc_ws.trade_event.real_sol_reserves",
    ),
    description=(
        "1 − real_sol_now / max(real_sol_reserves over the last window_s); unknown "
        "(stale) when the newest observation is older than max_gap_s (KB-0118)."
    ),
    params={"window_s": DEFAULT_WINDOW_S, "max_gap_s": DEFAULT_MAX_GAP_S},
)
"""Registered as every feature is; a different window is a new version."""


@dataclass(frozen=True, slots=True)
class ReservePoint:
    """One observation of the curve's real SOL with its two clocks."""

    observed_at: datetime
    received_at: datetime
    real_sol: Decimal


class RecentDrawdown(NamedTuple):
    """``(dd_pct, peak_age_s, reason)`` — the fraction lost from the window's
    peak, how old that peak is, and why the first two are ``None``."""

    drawdown_pct: Decimal | None
    peak_age_s: Decimal | None
    reason: str | None


class PeakDeque:
    """A monotonic deque of reserve points: values strictly decrease from head
    to tail, so the head is the peak of whatever is still inside the window.

    ``push`` is O(1) amortized for points arriving in ``observed_at`` order
    (every point is appended once and popped at most once); an out-of-order
    point takes the O(n) path so the invariant never depends on the feed.
    ``expire`` is the owner's retention (drop the head while older than its
    horizon); a query scans past the few retained entries older than its
    window without popping them, so several windows can read one deque. The
    deque also remembers the newest observation (by ``observed_at``) and the
    latest ``received_at`` it has seen, which is what makes the fold honest.
    """

    __slots__ = ("_entries", "_newest", "_received_by")

    def __init__(self) -> None:
        self._entries: deque[ReservePoint] = deque()
        self._newest: ReservePoint | None = None
        self._received_by: datetime | None = None

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def newest(self) -> ReservePoint | None:
        return self._newest

    @property
    def received_by(self) -> datetime | None:
        """The latest ``received_at`` pushed: the fold is exact for ``as_of`` ≥ this."""
        return self._received_by

    @property
    def peak(self) -> ReservePoint | None:
        return self._entries[0] if self._entries else None

    def peak_since(self, start: datetime) -> ReservePoint | None:
        """The peak among the entries observed at or after ``start`` — the
        first such entry from the head (values decrease head to tail). Does
        not pop: the owner decides the retention with :meth:`expire`, so two
        windows can be asked of the same deque."""
        for entry in self._entries:
            if entry.observed_at >= start:
                return entry
        return None

    def push(self, point: ReservePoint) -> None:
        if self._newest is None or point.observed_at >= self._newest.observed_at:
            self._newest = point
            while self._entries and self._entries[-1].real_sol <= point.real_sol:
                self._entries.pop()
            self._entries.append(point)
        else:
            self._insert_out_of_order(point)
        if self._received_by is None or point.received_at > self._received_by:
            self._received_by = point.received_at

    def _insert_out_of_order(self, point: ReservePoint) -> None:
        """A point older than the newest: it matters only if no later point
        already dominates it, and it dominates every earlier point ≤ it."""
        kept = [e for e in self._entries if e.observed_at <= point.observed_at]
        later = [e for e in self._entries if e.observed_at > point.observed_at]
        if later and later[0].real_sol >= point.real_sol:
            return
        kept = [e for e in kept if e.real_sol > point.real_sol]
        self._entries = deque([*kept, point, *later])

    def expire(self, before: datetime) -> None:
        """Drop the head while it was observed before ``before``."""
        while self._entries and self._entries[0].observed_at < before:
            self._entries.popleft()

    def clear(self) -> None:
        self._entries.clear()
        self._newest = None
        self._received_by = None


def _fold(peak: ReservePoint, newest: ReservePoint, as_of: datetime) -> RecentDrawdown:
    age = Decimal((as_of - peak.observed_at).total_seconds()).quantize(_SECONDS, ROUND_HALF_EVEN)
    if peak.real_sol <= 0:
        return RecentDrawdown(Decimal(0).quantize(_FRACTION), age, None)
    dd = (Decimal(1) - newest.real_sol / peak.real_sol).quantize(_FRACTION, ROUND_HALF_EVEN)
    return RecentDrawdown(max(dd, Decimal(0).quantize(_FRACTION)), age, None)


def _from_sequence(
    points: Sequence[ReservePoint], *, as_of: datetime, start: datetime
) -> tuple[ReservePoint | None, ReservePoint | None]:
    """``(newest, peak)`` over the points that had reached us by ``as_of``."""
    known = [p for p in points if p.received_at <= as_of and p.observed_at <= as_of]
    if not known:
        return None, None
    newest = max(known, key=lambda p: (p.observed_at, p.received_at))
    inside = [p for p in known if p.observed_at >= start]
    if not inside:
        return newest, None
    peak = max(inside, key=lambda p: (p.real_sol, p.observed_at))  # ties: the latest, as the deque
    return newest, peak


def recent_drawdown(
    points: PeakDeque | Sequence[ReservePoint],
    *,
    as_of: datetime,
    window_s: int = DEFAULT_WINDOW_S,
    max_gap_s: int = DEFAULT_MAX_GAP_S,
) -> RecentDrawdown:
    """The fraction the real SOL lost from its peak of the last ``window_s``,
    the peak's age, or a named unknown. Total: every input yields an answer.

    Over a :class:`PeakDeque` the fold is O(1) amortized and requires that
    every point had reached us by ``as_of`` (``received_by <= as_of``); a
    deque queried at an earlier instant raises ``ValueError`` rather than
    silently counting a point from the future — the caller with a full
    history folds the sequence instead.
    """
    start = as_of - timedelta(seconds=window_s)
    if isinstance(points, PeakDeque):
        if points.received_by is not None and points.received_by > as_of:
            raise ValueError("PeakDeque holds a point received after as_of; fold the sequence")
        newest, peak = points.newest, points.peak_since(start)
    else:
        newest, peak = _from_sequence(points, as_of=as_of, start=start)
    if newest is None:
        return RecentDrawdown(None, None, NO_OBSERVATION)
    if as_of - newest.observed_at > timedelta(seconds=max_gap_s):
        return RecentDrawdown(None, None, STALE)
    # A fresh newest outside the window (max_gap_s > window_s): nothing fell
    # inside the window, so the newest is its own peak and the drawdown is 0.
    return _fold(peak or newest, newest, as_of)
