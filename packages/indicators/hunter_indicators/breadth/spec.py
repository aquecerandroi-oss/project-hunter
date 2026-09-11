"""Which universe each ``breadth_5m`` version is a statement about.

T3.88. ``series.py`` is the arithmetic and it did not change: the window rule, the
completeness rule, the strict ``<`` and the coverage floor are the same function
they were in T3.77. What changed is the **universe** the fraction is a fraction
of, and a different universe is a different series -- so it is a different version
string, and this module is where the two are bound together instead of being
implied by whatever the producer happened to query.

===============  =========================================  ==================
version          universe                                    status
===============  =========================================  ==================
``breadth_v1``   every monitored active perpetual (~200)     frozen, immutable
``breadth_v2``   the same, restricted to markets with >= 90  current
                 days of final 1m candles (16 on the VPS,
                 2026-09-10)
===============  =========================================  ==================

**Why v2 exists.** A reading is the share of *the universe* that fell, so a day
on which only sixteen of two hundred perpetuals have 1-minute candles produces
8 % coverage, which the floor refuses -- 87 of the last 91 days, measured on the
VPS 2026-09-10. ``breadth_v1`` therefore has no past and EXP-0027 was
prospective-only. The sixteen markets with 90 days of history are exactly the
shadow universe (T3.82) and exactly the population every replay cohort is drawn
from, so a series measured over *them* is both computable over 90 days and the
universe the decisions being cut by it actually live in.

**Why ``min_history_days`` is frozen here and not read from the environment.**
``SHADOW_UNIVERSE_MIN_HISTORY_DAYS`` is an operational knob of the shadow
dispatch gate -- an operator may set it to ``0`` to measure the cost of
evaluating everything. If this series read that knob, turning it would silently
change what ``breadth_v2`` *means* while rows already written under the old
meaning stayed in the table, which is the one thing an immutable series exists to
forbid. The membership **rule** is shared (:mod:`hunter_core.universe`); the
number is a property of the version.

**v1 is not deleted and not edited.** ``breadth_v1`` rows keep their meaning, the
spec that describes them stays here, and the producer can still be pointed at it
(``--series breadth_v1``) to reproduce one. Nothing reads it by default any more:
:data:`CURRENT_BREADTH_VERSION` is ``breadth_v2``, and every consumer that used to
default to "the version" now names one -- the gate takes it from the stored
policy, the producer and the backfill from a spec they were handed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hunter_indicators.breadth.series import MIN_COVERAGE, WINDOW_MINUTES

BREADTH_V1 = "breadth_v1"
BREADTH_V2 = "breadth_v2"

CURRENT_BREADTH_VERSION = BREADTH_V2
"""What a producer or a backfill computes when nobody names a version, and what
the operator's ``--policy breadth=<min>-<max>`` stores unless it names one."""

UNIVERSE_ALL_MONITORED = 0
"""``min_history_days`` of a universe with no history requirement at all -- the
same ``0`` :func:`hunter_core.universe.has_min_history` reads as "no window"."""

SHADOW_UNIVERSE_DAYS = 90
"""The window T3.82 froze, and the one ``candles_1m`` retention keeps
(DATABASE.md §1.3). A different number is a different version, never an edit."""

__all__ = [
    "BREADTH_V1",
    "BREADTH_V2",
    "CURRENT_BREADTH_VERSION",
    "SHADOW_UNIVERSE_DAYS",
    "SPECS",
    "UNIVERSE_ALL_MONITORED",
    "BreadthSpec",
    "current_spec",
    "spec_for",
]


@dataclass(frozen=True, slots=True)
class BreadthSpec:
    """Everything a version of the series is: a name and the universe it folds.

    The arithmetic knobs travel here too (``window_minutes``, ``min_coverage``)
    so that a producer, a backfill and an audit row all read one object rather
    than three constants they could pick different values of.
    """

    version: str
    min_history_days: int
    """``0`` means "every monitored active perpetual" (``breadth_v1``)."""

    window_minutes: int = WINDOW_MINUTES
    min_coverage: Decimal = MIN_COVERAGE

    @property
    def restricted(self) -> bool:
        """Whether membership asks for history at all."""
        return self.min_history_days > UNIVERSE_ALL_MONITORED

    @property
    def universe_rule(self) -> str:
        """The rule as one auditable word, stored in ``market_breadth.inputs``."""
        return (
            f"monitored_perpetual_min_history_{self.min_history_days}d"
            if self.restricted
            else "monitored_perpetual"
        )


SPECS: dict[str, BreadthSpec] = {
    BREADTH_V1: BreadthSpec(version=BREADTH_V1, min_history_days=UNIVERSE_ALL_MONITORED),
    BREADTH_V2: BreadthSpec(version=BREADTH_V2, min_history_days=SHADOW_UNIVERSE_DAYS),
}
"""Every version this build can compute or read. A name absent from here is
refused rather than served the nearest series: a version attributed to an
experiment nobody ran is worse than an error."""


def spec_for(version: str) -> BreadthSpec:
    """The spec of ``version``, or :class:`KeyError` naming what does exist."""
    try:
        return SPECS[version]
    except KeyError:
        known = ", ".join(sorted(SPECS))
        raise KeyError(f"unknown breadth version {version!r}; this build knows {known}") from None


def current_spec() -> BreadthSpec:
    """The spec of :data:`CURRENT_BREADTH_VERSION`."""
    return SPECS[CURRENT_BREADTH_VERSION]
