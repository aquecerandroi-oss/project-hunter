"""Which universe, and which reference, each ``dispersion_24h`` version means.

T3.90, the shape T3.88 gave ``hunter_indicators.breadth.spec``: ``series.py`` is
the arithmetic and this module is *what the arithmetic is a statement about*. A
version of this series is three things at once — the numeric protocol (24 h,
two endpoints, median, strict ``<``), the **universe** the median is a median
of, and the **reference market** the dispersion is measured against — and all
three are bound together here so that none of them can be implied by whatever
the producer happened to query.

=====================  =============================================  ==========
version                universe / reference                            status
=====================  =============================================  ==========
``dispersion_24h_v1``  markets with >= 90 d of final 1m candles (the   current
                       shadow universe, 16 on the VPS 2026-09-10),
                       reference ``BTCUSDT``
=====================  =============================================  ==========

**Why v1 starts where ``breadth_v2`` ended.** T3.77 shipped ``breadth_v1`` over
~200 monitored perpetuals and T3.88 had to write a second version because a
fraction of a universe that has no candles is ``insufficient_coverage`` on 87 of
91 days. This series does not repeat that: its first version already folds the
universe every replay cohort is drawn from (:mod:`hunter_core.universe`,
``min(candles.open_time) <= as_of - 90 d``), which is both computable over the
retained ninety days and the population the decisions being cut by it live in.

**Why ``min_history_days`` is frozen here and not read from the environment.**
``SHADOW_UNIVERSE_MIN_HISTORY_DAYS`` is an operational knob of the shadow
dispatch gate; if this series read it, turning it would silently change what
``dispersion_24h_v1`` *means* while rows written under the old meaning stayed in
the table. The membership **rule** is shared; the number is a property of the
version — T3.88's sentence, and the reason ``SHADOW_UNIVERSE_DAYS`` below is a
constant of this module and not an import from ``breadth.spec``: the two series
agree on 90 today and must be free to disagree tomorrow.

**Why the reference is a field and not a constant.** ``BTCUSDT`` is what H-P18
is about, but "which market is the reference" is part of what a stored row
*means*: a reading folded against ETH is a different series, not the same one
with a different input. It travels with the version, is written into
``market_dispersion.inputs`` on every row, and a build that changed it would
have to change the version string to write anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hunter_indicators.dispersion.series import HORIZON_MINUTES, MIN_COVERAGE

DISPERSION_V1 = "dispersion_24h_v1"

CURRENT_DISPERSION_VERSION = DISPERSION_V1
"""What a producer or a backfill computes when nobody names a version, and what
the operator's ``--policy dispersion=<min>-<max>`` stores unless it names one."""

UNIVERSE_ALL_MONITORED = 0
"""``min_history_days`` of a universe with no history requirement at all — the
same ``0`` :func:`hunter_core.universe.has_min_history` reads as "no window".
No version of this series uses it; it is the vocabulary a future one would."""

SHADOW_UNIVERSE_DAYS = 90
"""The window T3.82 froze and ``candles_1m`` retention keeps (DATABASE.md §1.3).
Written again here rather than imported from ``breadth.spec``: a different
number is a different version, and the two series must be able to move apart."""

REFERENCE_SYMBOL = "BTCUSDT"
"""The market every other one is compared against. Spelled here and not imported
from ``hunter_scanner_worker.regime``: an indicator package must not depend on a
worker, and the reference is a property of the *series*, not of the process."""

__all__ = [
    "CURRENT_DISPERSION_VERSION",
    "DISPERSION_V1",
    "REFERENCE_SYMBOL",
    "SHADOW_UNIVERSE_DAYS",
    "SPECS",
    "UNIVERSE_ALL_MONITORED",
    "DispersionSpec",
    "current_spec",
    "spec_for",
]


@dataclass(frozen=True, slots=True)
class DispersionSpec:
    """Everything a version of the series is: a name, a universe, a reference.

    The arithmetic knobs travel here too (``horizon_minutes``, ``min_coverage``)
    so that a producer, a backfill and an audit row all read one object rather
    than three constants they could pick different values of.
    """

    version: str
    min_history_days: int
    reference_symbol: str = REFERENCE_SYMBOL
    horizon_minutes: int = HORIZON_MINUTES
    min_coverage: Decimal = MIN_COVERAGE

    @property
    def restricted(self) -> bool:
        """Whether membership asks for history at all."""
        return self.min_history_days > UNIVERSE_ALL_MONITORED

    @property
    def universe_rule(self) -> str:
        """The rule as one auditable word, stored in ``market_dispersion.inputs``."""
        return (
            f"monitored_perpetual_min_history_{self.min_history_days}d"
            if self.restricted
            else "monitored_perpetual"
        )


SPECS: dict[str, DispersionSpec] = {
    DISPERSION_V1: DispersionSpec(version=DISPERSION_V1, min_history_days=SHADOW_UNIVERSE_DAYS)
}
"""Every version this build can compute or read. A name absent from here is
refused rather than served the nearest series: a version attributed to an
experiment nobody ran is worse than an error."""


def spec_for(version: str) -> DispersionSpec:
    """The spec of ``version``, or :class:`KeyError` naming what does exist."""
    try:
        return SPECS[version]
    except KeyError:
        known = ", ".join(sorted(SPECS))
        raise KeyError(
            f"unknown dispersion version {version!r}; this build knows {known}"
        ) from None


def current_spec() -> DispersionSpec:
    """The spec of :data:`CURRENT_DISPERSION_VERSION`."""
    return SPECS[CURRENT_DISPERSION_VERSION]
