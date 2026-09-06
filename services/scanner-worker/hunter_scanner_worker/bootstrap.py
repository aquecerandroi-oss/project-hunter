"""What a bootstrap *is*: a window of minutes, a settings block and the holes.

Split from :mod:`hunter_scanner_worker.replay`, which is what *does* it. The seam
is deliberate: everything here is a pure statement about time and about the
candles that are missing from it, decidable without a database, a clock or an
event loop — which is why the window arithmetic and the gap detection are the two
things this task can test without touching Postgres.

**No REST, ever.** Missing history is published as ``market.backfill.requested``
and the market is declared "under construction" with the holes it found; the
scanner does not fetch candles (``docs/plans/M2.md``, section REST). Every hole is
reported, not only the long ones: one missing minute costs
``relative_volume_1h`` a whole day of observations, so a five-minute floor would
leave the most damaging gaps unrepaired (Astra, T2.5b design review, must-fix 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc
from hunter_indicators.baselines.bootstrap import BUFFER_MINUTES

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from hunter_indicators.baselines import BaselineRevision
    from hunter_scanner_worker.registry import MarketRef

MINUTE = timedelta(minutes=1)
REASON_INCOMPLETE = "history_incomplete"
REASON_NO_CANDLES = "no_persisted_candles"

__all__ = [
    "MINUTE",
    "REASON_INCOMPLETE",
    "REASON_NO_CANDLES",
    "BootstrapOutcome",
    "BootstrapSettings",
    "BootstrapWindow",
    "merge_runs",
    "missing_runs",
    "window_for",
]


@dataclass(frozen=True, slots=True)
class BootstrapSettings:
    """Everything tunable about a bootstrap. All cadence, no thresholds."""

    window_days: int = 7
    buffer_minutes: int = BUFFER_MINUTES
    slice_s: float = 0.05
    """How long the replay may hold the event loop before yielding. Checked per
    vector, not per chunk: a chunk of 250 cuts is seven seconds of silence."""

    duty: float = 0.4
    """Share of wall time the replay may take. The rest is given back to the
    evaluation loop, which is the one with a latency budget to defend."""

    tail_lag_minutes: int = 3
    """A hole this close to *now* is the collector still writing, not a gap."""

    merge_gap_minutes: int = 60
    max_gap_requests: int = 5
    max_age_h: int = 24
    """How old a market's newest bootstrap may be before it is redone."""

    retry_s: float = 6 * 3600.0
    max_retry_s: float = 7 * 24 * 3600.0

    @property
    def expected_size(self) -> int:
        """Observations a full bucket holds: one per minute, one UTC hour, N days."""
        return self.window_days * 60

    def __post_init__(self) -> None:
        # A duty of zero is a division by zero and a bootstrap that never runs;
        # refusing at construction beats discovering it in the loop.
        if not 0.0 < self.duty <= 1.0:
            raise ValueError(f"bootstrap duty must be in (0, 1], got {self.duty}")
        if self.slice_s <= 0.0:
            raise ValueError(f"bootstrap slice_s must be positive, got {self.slice_s}")

    @property
    def pause_s(self) -> float:
        if self.duty >= 1.0:
            return 0.0
        return self.slice_s * (1.0 / self.duty - 1.0)


@dataclass(frozen=True, slots=True)
class BootstrapWindow:
    """``[start, end)`` — half-open, ending at the hour that just closed."""

    start: datetime
    end: datetime

    def cuts(self) -> Iterator[datetime]:
        """One cut per minute boundary in the window.

        The boundary and not "some instant inside the minute": at ``M:00:00``
        ``bisect_right`` over ``close_time`` admits exactly the candles up to
        ``M-1``, which is what the live path holds when it snapshots minute
        ``M``. The bucket is then ``M.hour``, same as live.
        """
        moment = self.start
        while moment < self.end:
            yield moment
            moment += MINUTE


def window_for(now: datetime, *, days: int) -> BootstrapWindow:
    """The ``days``-long window ending at the last closed hour before ``now``."""
    end = ensure_utc(now).replace(minute=0, second=0, microsecond=0)
    return BootstrapWindow(start=end - timedelta(days=days), end=end)


def missing_runs(
    stamps: Sequence[datetime], *, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """Half-open runs of minutes with no candle in ``[start, end)``."""
    present = {ensure_utc(stamp) for stamp in stamps}
    runs: list[tuple[datetime, datetime]] = []
    moment = ensure_utc(start)
    limit = ensure_utc(end)
    run_start: datetime | None = None
    while moment < limit:
        if moment in present:
            if run_start is not None:
                runs.append((run_start, moment))
                run_start = None
        elif run_start is None:
            run_start = moment
        moment += MINUTE
    if run_start is not None:
        runs.append((run_start, limit))
    return runs


def merge_runs(
    runs: Sequence[tuple[datetime, datetime]], *, settings: BootstrapSettings
) -> list[tuple[datetime, datetime]]:
    """Collapse holes that are close together, then bound how many are asked for.

    A hundred one-minute holes are one damaged stretch, not a hundred repairs;
    re-fetching the minutes in between is harmless (the market-worker upserts by
    natural key) and one request is what the recovery loop can actually drain.
    Past ``max_gap_requests`` the hull of everything left is asked for instead —
    a bounded request is repairable, an unbounded queue is not.
    """
    if not runs:
        return []
    merged: list[tuple[datetime, datetime]] = [runs[0]]
    slack = timedelta(minutes=settings.merge_gap_minutes)
    for run in runs[1:]:
        previous = merged[-1]
        if run[0] - previous[1] <= slack:
            merged[-1] = (previous[0], max(previous[1], run[1]))
        else:
            merged.append(run)
    if len(merged) > settings.max_gap_requests:
        return [(merged[0][0], merged[-1][1])]
    return merged


@dataclass(frozen=True, slots=True)
class BootstrapOutcome:
    """What one market's bootstrap produced, and what it could not."""

    ref: MarketRef
    window: BootstrapWindow
    cuts: int = 0
    revisions: tuple[BaselineRevision, ...] = ()
    complete: bool = False
    reason: str | None = None
    gaps: tuple[tuple[datetime, datetime], ...] = ()
    rejections: dict[str, dict[str, int]] = field(default_factory=dict[str, dict[str, int]])
    requested: int = 0
    withheld: int = 0
    """Revisions this run computed and did **not** publish, because doing so
    would have replaced a usable baseline with a less mature one."""

    @property
    def buckets(self) -> int:
        return len(self.revisions)
