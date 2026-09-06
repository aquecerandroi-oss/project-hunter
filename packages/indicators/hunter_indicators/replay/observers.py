"""The two exit rules that do not fit in a price level, as pure predicates.

``TrackingPlan`` can express "invalidation at level L", so ``INV-B``, ``INV-E``
and the target arms are just a different plan and the production walker runs
unchanged. ``INV-C`` (two consecutive closes) and ``EXIT-CHAN`` (a level that
moves with the channel) are not levels, so the replay engine evaluates them
here, at the close of each bar it has just folded, and hands the verdict to the
walker as a pending invalidation — the walker still decides *when* it is paid
(the next eligible open) and with what priority.

Both are folds over an integer state, not stateful objects: the engine keeps the
state next to the walker's ``Progress`` and a redelivered bar cannot advance a
streak, exactly as a redelivered bar cannot advance the walk.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import is_aligned

__all__ = ["ChannelObserver", "ConsecutiveCloseObserver"]


@dataclass(frozen=True, slots=True)
class ConsecutiveCloseObserver:
    """INV-C: fire when ``required`` consecutive aligned closes are below ``level``.

    Only closes aligned to the frozen invalidation timeframe count — a 1m close
    is not an observation of a 15m rule — and a close at or above the level
    resets the streak, because "consecutive" is the whole hypothesis being
    tested (a level touched twice with a recovery between is not a confirmed
    break).
    """

    level: Decimal
    timeframe: Timeframe
    required: int = 2

    def step(self, streak: int, *, close_time: datetime, close: Decimal) -> tuple[int, bool]:
        """The new streak and whether the invalidation is now observed."""
        if not is_aligned(close_time, self.timeframe):
            return streak, False
        if close >= self.level:
            return 0, False
        advanced = streak + 1
        return advanced, advanced >= self.required


@dataclass(frozen=True, slots=True)
class ChannelObserver:
    """EXIT-CHAN: fire when a close is strictly below the lowest of the previous
    ``lookback`` closes of the same timeframe.

    ``None`` means *unavailable*, never *false*: without the whole window (the
    history does not reach back far enough, or a minute is missing so the
    aggregation refuses the window) the rule has no answer, and the arm must be
    reported as uncovered rather than silently held open (SHADOW-LAB.md §7).
    """

    lookback: int

    def fired(self, close: Decimal, previous_closes: Sequence[Decimal]) -> bool | None:
        if len(previous_closes) < self.lookback:
            return None
        window = previous_closes[-self.lookback :]
        return close < min(window)
