"""Is the live evaluation behind? The one question the background work asks.

The scanner runs two kinds of work in one process: the evaluation loop, whose
budget is the age of a tick (p99 <= 3 s, joint M2 decision), and the baseline
bootstrap, which is hours of replay that nothing is waiting for. T2.5b split
them by a **duty cycle** -- 50 ms of replay, then a pause leaving the bootstrap
40% of the wall clock -- and that is the right shape only while the scanner is
keeping up: a fixed share spends its share whatever the backlog.

This module is the backlog, expressed as one boolean, with hysteresis so it
cannot flap between two slices. It reads the same fact ``/ready`` and the
histogram read: how long the oldest dirty market has been waiting. Nothing here
decides *what* to do about it -- ``replay.BootstrapJob.run_slice`` does, at the
cooperative boundaries it already had.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker.metrics import scanner_bootstrap_suspended

if TYPE_CHECKING:
    from hunter_scanner_worker.state import ScannerState

logger = get_logger(__name__)

SUSPEND_S = 1.0
"""Backlog at which background work stands aside.

One feature throttle (``ScannerConfig.feature_throttle_s``): a market that has
been dirty longer than the interval between two of its own vectors has already
missed its cadence, and every second after that is spent by the tick, not by
the loop."""

RESUME_S = 0.5
"""Backlog at which it may come back -- half a throttle, so "caught up" means
caught up and not merely "under the line for one sample"."""

__all__ = ["RESUME_S", "SUSPEND_S", "LivePressure"]


@dataclass
class LivePressure:
    """Whether the evaluation loop is late enough to own the whole CPU."""

    state: ScannerState
    suspend_s: float = SUSPEND_S
    resume_s: float = RESUME_S
    suspended: bool = False

    def oldest_dirty_s(self, now: datetime | None = None) -> float:
        """Seconds the market that has been waiting longest has waited.

        The oldest, never the average: one market starving while 199 are fresh
        is precisely the p99 violation the budget is about.
        """
        moment = now or utcnow()
        ages = [
            (moment - market.dirty_since).total_seconds()
            for market in self.state.markets.values()
            if market.dirty_since is not None
        ]
        return max(ages) if ages else 0.0

    def __call__(self, now: datetime | None = None) -> bool:
        """``True`` while background work must stand aside."""
        age = self.oldest_dirty_s(now)
        if self.suspended:
            if age <= self.resume_s:
                self.suspended = False
                logger.info("scanner_bootstrap_resumed", oldest_dirty_s=round(age, 3))
        elif age > self.suspend_s:
            self.suspended = True
            logger.info("scanner_bootstrap_suspended", oldest_dirty_s=round(age, 3))
        scanner_bootstrap_suspended.set(1 if self.suspended else 0)
        return self.suspended
