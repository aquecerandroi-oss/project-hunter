"""``hunter_indicators.breadth`` — the amplitude of the universe as a series.

One module, one number: :func:`compute_breadth`, the share of the monitored
perpetuals whose close fell over the last five completed minutes (T3.77, H-P8).

Kept apart from :mod:`hunter_indicators.regime.breadth`, which answers a
different question over a different horizon (markets *advancing* over four hours,
an input of the hourly regime score). Two names, two versions, never a shared
parameter — the day one of them changes, the other must not move with it.
"""

from hunter_indicators.breadth.series import (
    BREADTH_VERSION,
    MIN_COVERAGE,
    RATIO_QUANTUM,
    REASON_EMPTY_UNIVERSE,
    REASON_INSUFFICIENT_COVERAGE,
    WINDOW_MINUTES,
    BreadthReading,
    compute_breadth,
    window_open_times,
)

__all__ = [
    "BREADTH_VERSION",
    "MIN_COVERAGE",
    "RATIO_QUANTUM",
    "REASON_EMPTY_UNIVERSE",
    "REASON_INSUFFICIENT_COVERAGE",
    "WINDOW_MINUTES",
    "BreadthReading",
    "compute_breadth",
    "window_open_times",
]
