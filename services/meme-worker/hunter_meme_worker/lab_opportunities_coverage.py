"""The coverage guard of EXP-M26 (design §1.6, "Guarda de cobertura") — pure.

The line of ``hunter_indicators.meme.lines`` (v1, untouched) reads two windows:
the current ``(T − 15 min, T]`` and the breakout's ``(T − 16 min, T − 1 min]``,
each with the photos **received** by ``T``. ``MIN_POINTS`` counts photos, not
time: five photos in the last four minutes pass it while eleven minutes went
unobserved, and a missing high at ``T − 16 min`` fakes a breakout. The guard
closes that without changing the formula: on the union ``(T − 16 min, T]`` and
with **the same usable points** the formula reads (``lines.usable_points``:
received by ``T``, positive market cap, one per instant), a decision is
covered when the first point is at most 150 s after the window's start, the last
at most 150 s before ``T``, and no two consecutive points are more than 150 s
apart (2.5× the chain's cadence, KB-0148).

A coin younger than 16 min has no photo before its birth: the effective start is
``created_at`` and a covered window is ``covered_from_birth`` — truncated at
birth, counted apart, never "complete". At the gate's floor (900 s) every
first opportunity of ``grafico_ctrl_v1/1`` lands here.

The version, the parameters and the measurements are returned with the status,
so a reader can reproduce the class without the photos (design §1.6, R1).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_indicators.meme.lines import WINDOW_MINUTES, LinePoint, usable_points

__all__ = [
    "COVERAGE_MAX_GAP_S",
    "COVERAGE_VERSION",
    "COVERAGE_WINDOW_MINUTES",
    "coverage_of",
    "unread_coverage",
]

COVERAGE_VERSION = "grafico_maduro_cobertura_v1"
COVERAGE_WINDOW_MINUTES = WINDOW_MINUTES + 1
"""The union of the two windows the line reads: ``(T − 16 min, T]``."""
COVERAGE_MAX_GAP_S = 150

_PARAMS: dict[str, Any] = {
    "window_s": COVERAGE_WINDOW_MINUTES * 60,
    "max_gap_s": COVERAGE_MAX_GAP_S,
    "points": "lines.usable_points: received_at <= T, mcap_sol > 0, one per instant",
}


def _seconds(delta: timedelta) -> str:
    return str(Decimal(str(delta.total_seconds())))


def unread_coverage(error: str) -> tuple[str, dict[str, Any]]:
    """The photos could not be read at the tick: ``unread``, never ``gap``."""
    return "unread", {"version": COVERAGE_VERSION, "params": _PARAMS, "error": error}


def coverage_of(
    points: Sequence[LinePoint], *, end_time: datetime, created_at: datetime | None
) -> tuple[str, dict[str, Any]]:
    """``(status, detail)`` of the union window ending at ``end_time``."""
    window = timedelta(minutes=COVERAGE_WINDOW_MINUTES)
    usable = usable_points(points, end_time=end_time, start_offset=window, end_offset=timedelta(0))
    window_start = end_time - window
    born_inside = created_at is not None and created_at > window_start
    start = created_at if born_inside and created_at is not None else window_start
    limit = timedelta(seconds=COVERAGE_MAX_GAP_S)
    detail: dict[str, Any] = {
        "version": COVERAGE_VERSION,
        "params": _PARAMS,
        "window_start": window_start.isoformat(),
        "effective_start": start.isoformat(),
        "truncated_at_birth": born_inside,
        "points": len(usable),
    }
    if not usable:
        return "gap", {**detail, "reason": "no_usable_points"}
    lead = usable[0].observed_at - start
    tail = end_time - usable[-1].observed_at
    gaps = [b.observed_at - a.observed_at for a, b in zip(usable, usable[1:], strict=False)]
    widest = max(gaps, default=timedelta(0))
    detail |= {
        "first_observed_at": usable[0].observed_at.isoformat(),
        "last_observed_at": usable[-1].observed_at.isoformat(),
        "lead_s": _seconds(lead),
        "tail_s": _seconds(tail),
        "max_gap_s": _seconds(widest),
    }
    if lead > limit or tail > limit or widest > limit:
        return "gap", detail
    return ("covered_from_birth" if born_inside else "covered"), detail
