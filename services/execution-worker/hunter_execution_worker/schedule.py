"""When the next pass of a loop happens — and why the MTM's is not "in 60 s".

:func:`hunter_execution_worker.cycles.every` sleeps **after** the work, so a
cadence of 60 s is really ``60 s + however long the pass took``. For five of the
six loops that drift is harmless. For the mark-to-market it is not: the daily
reference is the newest point of the 1m curve **at or before** the São Paulo
turn, and it is refused if it was taken more than
:data:`hunter_core.risk.daily.DAY_OPENING_MAX_LAG_S` (60 s) before it. A curve
whose real period is 61,5 s therefore leaves the turn unanchored whenever the
first point after midnight lands inside the first 1,5 s of the day — a couple of
days a month, and much more often after a restart near midnight. An unavailable
reference blocks entries for the whole day (RISK_ENGINE.md §5), so this is a
wallet that silently stops trading because of an ``asyncio.sleep``.

Two things fix it, and both are here because either alone is thin:

- the pass is **aligned to the minute grid**, so the period is 60 s and not
  "60 s plus the database";
- one **extra point is written just before the turn**
  (:data:`TURN_MARGIN_S`), so the anchor's lag is a handful of seconds instead
  of a hair under the whole budget.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hunter_risk import sao_paulo_day_start_utc

__all__ = ["TURN_MARGIN_S", "next_grid_tick", "next_mtm_tick", "next_sao_paulo_turn"]

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

TURN_MARGIN_S = 5.0
"""How far before the São Paulo turn the extra point is taken.

Five seconds, not zero: the point's timestamp is the instant the cycle *ran*, so
a point aimed exactly at the turn lands a few milliseconds **after** it and
``day_opening_observation`` (``ts <= day_start``) will not see it at all. Five
seconds is comfortably inside the 60 s budget and comfortably outside the
scheduling jitter of a loop that also talks to Postgres."""


def next_grid_tick(now: datetime, period_s: float) -> datetime:
    """The next instant on the fixed ``period_s`` grid, strictly after ``now``.

    The grid is anchored on the Unix epoch, which for 60 s is "every whole
    minute" — the same grid the 1m curve is named after.
    """
    elapsed = (now - _EPOCH).total_seconds()
    return _EPOCH + timedelta(seconds=(math.floor(elapsed / period_s) + 1) * period_s)


def next_sao_paulo_turn(now: datetime) -> datetime:
    """The next midnight in ``America/Sao_Paulo``, in UTC, strictly after ``now``."""
    return sao_paulo_day_start_utc(now + timedelta(days=1))


def next_mtm_tick(now: datetime, *, period_s: float) -> datetime:
    """The grid — unless the São Paulo turn comes first, and then its margin.

    Never later than the grid, so the curve keeps its cadence, and never after
    the turn's margin, so the day always has a point to anchor on.
    """
    grid = next_grid_tick(now, period_s)
    anchor = next_sao_paulo_turn(now) - timedelta(seconds=TURN_MARGIN_S)
    return min(grid, anchor) if anchor > now else grid
