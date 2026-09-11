"""``breadth_5m`` — how much of the monitored universe is falling, as a number.

T3.77 / H-P8. On 2026-09-09 at 22:08Z, **194 of the 200 monitored perpetuals
fell in the same minute** (mean -3,71 %) while the BTC moved -0,20 %; that minute
is where 15 of the 39 bets of the family's worst hour died
(``.claude/state/notes-D-P9.md`` §4, KB-0083). The hypothesis is that the
fraction of the universe falling *before* a decision separates expectancy. This
module is the number, and nothing else: whether a version may decide inside a
band of it is :mod:`hunter_strategy_worker.breadth_gate`, and whether that band
helps is EXP-0027, which has not been run.

**Not** :mod:`hunter_indicators.regime.breadth`. That one (PIPELINE §4 / §4b) is
the share of markets *advancing* over four hours with volume, an input of the
hourly regime score. This one is the share *falling* over five minutes,
minute-anchored, and the two must never be added, averaged or read for each
other — which is why they are two modules with two names and two versions rather
than one function with a parameter.

**What one market contributes.** Its close at ``end_time`` against its close at
``end_time - window``: strictly below is *falling*, equal is not. A close at
instant ``t`` is the close of the 1-minute candle whose ``open_time`` is
``t - 1 min``, so the reading needs ``window + 1`` candles with ``open_time`` in
``[end_time - window - 1min, end_time)``. **No candle with
``open_time + 1 min > end_time`` may enter** — that is the whole of the
anti-look-ahead rule here, and it is why the caller resolves the open times from
:func:`window_open_times` instead of asking for "the last six candles".

**All ``window + 1`` closes, or the market is not counted.** Only two of them
enter the comparison, and requiring the four in between is the same doctrine
``regime_repo`` states for an hour ("complete or it does not exist"): a market
whose feed dropped for three of the five minutes has a close from before the gap
and one from after it, and calling that a five-minute move is a claim about
minutes nobody observed.

**Coverage refuses; it never leans bearish.** Below :data:`MIN_COVERAGE` of the
declared universe the answer is ``None`` with a reason, never a fraction of
whoever happened to answer — reporting 0,97 because six markets replied and five
of them fell would say "the universe is collapsing" when the truth is "we could
not look" (the rule :mod:`hunter_indicators.regime.breadth` already states for
its own coverage).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

# The version *strings* and the universe each one folds live in
# ``hunter_indicators.breadth.spec`` (T3.88), not here: this module is the frozen
# numeric protocol (this window rule, this completeness rule, this strict ``<``),
# and the universe is the other half of what a version names. Changing either is
# a new version string, never an edit — the same rule ``beta_version`` and
# ``classifier_version`` state.

WINDOW_MINUTES = 5
"""The only window this build computes. A policy asking for another one finds no
series and is refused; it does not get this one relabelled."""

MIN_COVERAGE = Decimal("0.80")
"""Four fifths of the declared universe. Below it the reading is unavailable."""

RATIO_QUANTUM = Decimal("0.0001")
"""Four decimals, the same quantum ``hunter_indicators.regime.model`` uses for a
ratio. 194/200 is 0,9700 exactly; 194/199 would be 0,9749."""

REASON_INSUFFICIENT_COVERAGE = "insufficient_coverage"
REASON_EMPTY_UNIVERSE = "empty_universe"

__all__ = [
    "MIN_COVERAGE",
    "RATIO_QUANTUM",
    "REASON_EMPTY_UNIVERSE",
    "REASON_INSUFFICIENT_COVERAGE",
    "WINDOW_MINUTES",
    "BreadthReading",
    "compute_breadth",
    "window_open_times",
]


def window_open_times(
    end_time: datetime, window_minutes: int = WINDOW_MINUTES
) -> tuple[datetime, ...]:
    """The ``open_time`` of every candle the reading needs, oldest first.

    ``window_minutes + 1`` of them, ending at ``end_time - 1 min``: the newest
    candle admitted is the one that *closed* exactly at ``end_time``. The candle
    opening at ``end_time`` closes after it and is not in this tuple — which is
    the anti-look-ahead guarantee expressed as a set of instants rather than as a
    filter somebody has to remember to write.
    """
    if window_minutes < 1:
        raise ValueError(f"window_minutes must be at least 1, got {window_minutes}")
    minute = timedelta(minutes=1)
    oldest = end_time - minute * (window_minutes + 1)
    return tuple(oldest + minute * step for step in range(window_minutes + 1))


@dataclass(frozen=True, slots=True)
class BreadthReading:
    """One ``breadth_5m`` value, with everything needed to audit it."""

    end_time: datetime
    window_minutes: int
    universe_size: int
    """The markets the universe *declared*, not the ones that answered."""
    covered: int
    """Markets with every close the window needs."""
    falling: int
    value: Decimal | None
    """``falling / covered``, or ``None`` when the reading is unusable. Never a
    fraction of a universe nobody could see."""
    coverage: Decimal
    """``covered / universe_size``."""
    usable: bool
    reason: str | None
    """Non-null exactly when ``usable`` is false — the same
    ``valid = (reason IS NULL)`` shape ``market_betas`` makes a constraint."""


def compute_breadth[MarketKey](
    closes: Mapping[MarketKey, Mapping[datetime, Decimal]],
    *,
    end_time: datetime,
    universe_size: int,
    window_minutes: int = WINDOW_MINUTES,
    min_coverage: Decimal = MIN_COVERAGE,
) -> BreadthReading:
    """The share of the universe whose close fell over ``window_minutes``.

    ``MarketKey`` is whatever the caller names a market by — a ``UUID`` in the
    job, a string in the tests. The arithmetic never looks at it.

    ``closes`` is ``market -> {open_time: close}`` over at least the instants
    :func:`window_open_times` names; anything else in it is ignored rather than
    trusted, so a caller that over-fetched cannot widen the window by accident.
    """
    needed = window_open_times(end_time, window_minutes)
    first, last = needed[0], needed[-1]
    covered = 0
    falling = 0
    for series in closes.values():
        if any(instant not in series for instant in needed):
            continue
        covered += 1
        if series[last] < series[first]:
            falling += 1
    with localcontext(CONTEXT):
        coverage = (
            Decimal(0)
            if universe_size <= 0
            else (Decimal(covered) / Decimal(universe_size)).quantize(RATIO_QUANTUM)
        )
        usable = universe_size > 0 and covered > 0 and coverage >= min_coverage
        value = (Decimal(falling) / Decimal(covered)).quantize(RATIO_QUANTUM) if usable else None
    reason: str | None = None
    if not usable:
        reason = REASON_EMPTY_UNIVERSE if universe_size <= 0 else REASON_INSUFFICIENT_COVERAGE
    return BreadthReading(
        end_time=end_time,
        window_minutes=window_minutes,
        universe_size=universe_size,
        covered=covered,
        falling=falling,
        value=value,
        coverage=coverage,
        usable=usable,
        reason=reason,
    )
