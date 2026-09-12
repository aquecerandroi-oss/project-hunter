"""The tape's budget (T4.2f): paced, adaptive, and honest about a block.

**What was measured.** The ``swap-api``'s ``x-ratelimit-limit: 1000`` is not its
limit: Cloudflare cuts the IP at about **20 requests per 60 s** (error 1015,
``retry-after: 60``) and every request of the next minute is refused — four live
probes on 12/09, ``hunter_exchanges.pumpfun.swap_api``. T4.2e's puller (900/60 s,
eight in flight) hit that rule at the start of every cycle, spent the rest of
the minute blocked, and wrote ``rate_limited`` on 1 069 rows in 15 minutes.

**What this does about it.** :class:`TapeBudget` hands each 10 s cycle its exact
share of the minute's budget (``16 × 10 / 60 = 2,67`` → 2, 3, 3, 2, 3, 3 — the
fraction is carried, never rounded away and never burst), so any 60 s window
holds at most the budget plus one. A **real** 429 (:class:`HttpRateLimited`,
never our own bucket) is measured — how many requests succeeded in the minute
before it — and the effective budget becomes 80 % of that, held for
``hold_s`` before the configured value is tried again; and nothing at all is
planned until the ``retry-after`` has passed, because a request during the
block is a refusal that may extend it. The heartbeat carries the effective
budget, the measured count and the block's end, so an operator sees the
ceiling the edge actually enforces rather than the one the header claims.

The arithmetic this leaves: 16 pulls a minute over ~130 tracked mints, each
usable for 180 s (``trades.py``), covers at most ~40 % of the set in any minute.
That is the ceiling of this endpoint from one IP, named here rather than
promised away.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction

from hunter_meme_worker.sources import RollingCounter

RATE_LIMITED = "rate_limited"
NO_TRADE_FEED = "no_trade_feed"
NOT_POLLED = "not_polled"
BUDGET_REFUSED = "budget_refused"
"""Our own bucket said no (never the server): the mint is ``not_polled``."""
MIN_BUDGET_60S = 4
SHRINK = 0.8
DEFAULT_HOLD_S = 900.0


@dataclass
class TapeCoverage:
    covered_since: datetime | None = None
    last_pull_at: datetime | None = None
    ok_times: deque[datetime] = field(default_factory=lambda: deque(maxlen=8))
    """Receive times of the newest successful pulls — the fold asks for the
    newest one at or before a minute's close (non-anticipation)."""
    high_water: str | None = None
    """The newest ``slotIndexId`` stored for the mint."""
    last_error: str | None = None
    pulls: int = 0
    rows: int = 0


@dataclass(frozen=True, slots=True)
class PullReport:
    pulled: int
    rows: int
    pages: int
    errors: int
    skipped: dict[str, int] = field(default_factory=dict[str, int])
    planned: int = 0
    deferred: int = 0
    """Due this cycle, cut by the cap — each remembered as ``not_polled``."""
    duration_s: float = 0.0
    refused_429: int = 0
    """Real 429s this cycle (the server's, never our bucket's)."""


@dataclass(frozen=True, slots=True)
class TapeStats:
    """How much of the tracked set the tape covers right now."""

    tracked: int
    covered: int
    never_pulled: int
    failing: int
    """Never covered and the last pull failed (the source's problem, named)."""


class TapeBudget:
    """Requests per 60 s, paced per cycle, shrunk by a real 429, blocked by its
    ``retry-after``."""

    def __init__(
        self,
        *,
        budget_60s: int,
        cycle_s: float,
        hold_s: float = DEFAULT_HOLD_S,
        floor: int = MIN_BUDGET_60S,
    ) -> None:
        self.configured = max(1, budget_60s)
        self.effective = self.configured
        self.cycle_s = max(0.1, cycle_s)
        self.hold = timedelta(seconds=hold_s)
        self.floor = max(1, floor)
        self.measured: int | None = None
        """Successful requests in the 60 s before the last real 429 — the
        ceiling as the edge counted it."""
        self.blocked_until: datetime | None = None
        self.restore_at: datetime | None = None
        self.ok_60s = RollingCounter(60)
        self.refusals_1h = RollingCounter(3600)
        self._carry = Fraction(0)
        """Exact, not a float: 2,67 + 0,33 must be 3, never 2,999…"""
        self.reserved = 0
        """Requests per 60 s another loop spends on the **same** edge budget
        (T4.2g: the batch route's calls, ``activity.py``) — taken off the
        top of what the tape may plan, so the two together never exceed
        ``effective``."""

    @property
    def per_cycle_nominal(self) -> int:
        """The cycle's share, floored — what a test asks for; :meth:`per_cycle`
        carries the fraction across cycles."""
        return max(1, int(self.effective * self.cycle_s / 60))

    @property
    def available(self) -> int:
        """What the tape itself may spend per 60 s: ``effective`` minus the reservation."""
        return max(1, self.effective - self.reserved)

    def reserve(self, requests_60s: int) -> None:
        self.reserved = max(0, requests_60s)

    def blocked_at(self, at: datetime) -> bool:
        return self.blocked_until is not None and at < self.blocked_until

    def per_cycle(self, now: datetime) -> int:
        """How many pulls this cycle may make: none while blocked, else the
        exact share with the fraction carried; the configured budget returns
        after ``hold_s`` without a 429."""
        if self.blocked_at(now):
            return 0
        if self.restore_at is not None and now >= self.restore_at:
            self.effective = self.configured
            self.restore_at = None
        exact = Fraction(self.available) * Fraction(self.cycle_s) / 60 + self._carry
        count = int(exact)
        self._carry = exact - count
        return count

    def record_ok(self, at: datetime) -> None:
        self.ok_60s.add(at)

    def record_refusal(self, at: datetime, *, retry_after_s: float) -> int:
        """A real 429: measure, shrink, block. Returns the new effective budget."""
        self.refusals_1h.add(at)
        self.measured = self.ok_60s.total(at)
        self.effective = max(self.floor, min(self.effective, int(self.measured * SHRINK)))
        self.blocked_until = at + timedelta(seconds=max(1.0, retry_after_s))
        self.restore_at = at + self.hold
        self._carry = Fraction(0)
        return self.effective


__all__ = [
    "BUDGET_REFUSED",
    "MIN_BUDGET_60S",
    "NOT_POLLED",
    "NO_TRADE_FEED",
    "RATE_LIMITED",
    "SHRINK",
    "PullReport",
    "TapeBudget",
    "TapeCoverage",
    "TapeStats",
]
