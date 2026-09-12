"""``hunter_indicators.dispersion`` — BTC × alts as a series.

Two modules, two jobs: :mod:`~hunter_indicators.dispersion.series` is the
arithmetic (:func:`compute_dispersion`, the median 24 h return of the alts minus
the reference's, T3.90 / H-P18) and
:mod:`~hunter_indicators.dispersion.spec` is which universe and which reference
each version of the series is a statement about (``dispersion_24h_v1`` = the 16
markets with 90 days of 1m history, reference ``BTCUSDT``).

Kept apart from :mod:`hunter_indicators.breadth`, which answers a different
question with a different shape (how many markets fell over five minutes, each
against its own earlier close, no reference and no returns compared). Two names,
two versions, two tables, never a shared parameter — the day one of them changes,
the other must not move with it.
"""

from hunter_indicators.dispersion.series import (
    HORIZON_MINUTES,
    MIN_COVERAGE,
    RATIO_QUANTUM,
    REASON_EMPTY_UNIVERSE,
    REASON_INSUFFICIENT_COVERAGE,
    REASON_NO_ALTS,
    REASON_REFERENCE_MISSING,
    RETURN_QUANTUM,
    DispersionReading,
    compute_dispersion,
    endpoint_open_times,
    median,
)
from hunter_indicators.dispersion.spec import (
    CURRENT_DISPERSION_VERSION,
    DISPERSION_V1,
    REFERENCE_SYMBOL,
    SHADOW_UNIVERSE_DAYS,
    SPECS,
    UNIVERSE_ALL_MONITORED,
    DispersionSpec,
    current_spec,
    spec_for,
)

__all__ = [
    "CURRENT_DISPERSION_VERSION",
    "DISPERSION_V1",
    "HORIZON_MINUTES",
    "MIN_COVERAGE",
    "RATIO_QUANTUM",
    "REASON_EMPTY_UNIVERSE",
    "REASON_INSUFFICIENT_COVERAGE",
    "REASON_NO_ALTS",
    "REASON_REFERENCE_MISSING",
    "REFERENCE_SYMBOL",
    "RETURN_QUANTUM",
    "SHADOW_UNIVERSE_DAYS",
    "SPECS",
    "UNIVERSE_ALL_MONITORED",
    "DispersionReading",
    "DispersionSpec",
    "compute_dispersion",
    "current_spec",
    "endpoint_open_times",
    "median",
    "spec_for",
]
