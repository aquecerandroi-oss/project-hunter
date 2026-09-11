"""``hunter_indicators.breadth`` — the amplitude of the universe as a series.

Two modules, two jobs: :mod:`~hunter_indicators.breadth.series` is the
arithmetic (:func:`compute_breadth`, the share of a declared universe whose close
fell over the last five completed minutes, T3.77 / H-P8) and
:mod:`~hunter_indicators.breadth.spec` is which universe each version of the
series is a statement about (T3.88: ``breadth_v1`` = ~200 monitored perpetuals,
``breadth_v2`` = the 16 with 90 days of 1m history, the shadow universe).

Kept apart from :mod:`hunter_indicators.regime.breadth`, which answers a
different question over a different horizon (markets *advancing* over four hours,
an input of the hourly regime score). Two names, two versions, never a shared
parameter — the day one of them changes, the other must not move with it.
"""

from hunter_indicators.breadth.series import (
    MIN_COVERAGE,
    RATIO_QUANTUM,
    REASON_EMPTY_UNIVERSE,
    REASON_INSUFFICIENT_COVERAGE,
    WINDOW_MINUTES,
    BreadthReading,
    compute_breadth,
    window_open_times,
)
from hunter_indicators.breadth.spec import (
    BREADTH_V1,
    BREADTH_V2,
    CURRENT_BREADTH_VERSION,
    SHADOW_UNIVERSE_DAYS,
    SPECS,
    UNIVERSE_ALL_MONITORED,
    BreadthSpec,
    current_spec,
    spec_for,
)

__all__ = [
    "BREADTH_V1",
    "BREADTH_V2",
    "CURRENT_BREADTH_VERSION",
    "MIN_COVERAGE",
    "RATIO_QUANTUM",
    "REASON_EMPTY_UNIVERSE",
    "REASON_INSUFFICIENT_COVERAGE",
    "SHADOW_UNIVERSE_DAYS",
    "SPECS",
    "UNIVERSE_ALL_MONITORED",
    "WINDOW_MINUTES",
    "BreadthReading",
    "BreadthSpec",
    "compute_breadth",
    "current_spec",
    "spec_for",
    "window_open_times",
]
