"""The "line broken" exit's input, computed statelessly from durable rows
(T4.10, EXP-M2): the support line of ``meme_features_1m`` projected to a
snapshot's instant, and the streak of consecutive snapshots closed below it.

Nothing here reads a clock or a table. The loop (``lab_bets.py``) hands in the
lines folded **at or before** the snapshot being judged and the streak it had
after the previous snapshot; a restart rebuilds the streak from the snapshot
at ``mark_at``, so the count survives without a column of its own.

Projection: the fold writes ``support_line_sol`` as the line's value at
``end_time`` and ``support_line_slope`` in SOL per minute, so the line at an
instant ``t >= end_time`` is ``support + slope × (t − end_time) / 60 s``. The
newest folded minute not after ``t`` is the one used — never a minute folded
after the snapshot, which would be the look-ahead in different clothes.

T4.98 (EXP-M26 L1, KB-0161) — "folded" is ``computed_at <= t``, not only
``end_time <= t``: the minute that closed at T and was folded at T + 3 s did
not exist for the photo of T + 2 s (39 of 243 ``line_broken`` exits of 19–26/09
fired on such a minute). The **newest** known minute decides: if it drew no
line (``flat``, ``too_few_points``…), an older line is never projected over it;
and a line whose minute closed more than ``SUPPORT_MAX_AGE_S`` (120 s) before
``t`` is stale. The fold runs every minute with a delay of p99 5,4 s, max
6,3 s (7 days, 2,29 M rows), so a tracked mint's newest minute is at most
~66 s old; 120 s absorbs a fold up to ~54 s late. A minute never folded
leaves the support unknown for the last ~6 s before the next fold — neutral,
never a stale line.

**Unknown is neutral.** A stale or missing support is ``None``: the snapshot's
streak becomes unknown (``next_streak``), ``hit_line_break`` does not fire and
``evaluate_exit`` reports ``support_line_unknown``. It never blocks target,
trailing, time, max-loss, creator-dump or an operator's sale — those rules do
not read the line. A break needs two consecutive *known* closes below again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT

__all__ = ["SUPPORT_MAX_AGE_S", "SupportLine", "below_support", "next_streak", "support_at"]

SUPPORT_MAX_AGE_S = 120


@dataclass(frozen=True, slots=True)
class SupportLine:
    """One folded minute's support line, as ``meme_features_1m`` stores it."""

    end_time: datetime
    computed_at: datetime
    support_sol: Decimal | None
    slope_per_min: Decimal | None


def support_at(
    lines: Sequence[SupportLine],
    at: datetime,
    *,
    causal: bool = True,
    max_age_s: int = SUPPORT_MAX_AGE_S,
) -> Decimal | None:
    """The newest minute **known** at ``at`` (closed and folded by then),
    projected to ``at`` — ``None`` when that minute drew no line or closed more
    than ``max_age_s`` before ``at``, or when no minute was known yet. The rule
    set's ``line_support_causal: false`` drops the ``computed_at`` test only."""
    known = [
        line for line in lines if line.end_time <= at and (not causal or line.computed_at <= at)
    ]
    if not known:
        return None
    line = max(known, key=lambda item: item.end_time)
    if line.support_sol is None or line.slope_per_min is None:
        return None
    if at - line.end_time > timedelta(seconds=max_age_s):
        return None
    with localcontext(CONTEXT):
        minutes = Decimal(str((at - line.end_time).total_seconds())) / Decimal(60)
        return line.support_sol + line.slope_per_min * minutes


def below_support(mcap_sol: Decimal | None, support_sol: Decimal | None) -> bool | None:
    """Closed below the line, or ``None`` when either number does not exist."""
    if mcap_sol is None or support_sol is None or support_sol <= 0:
        return None
    return mcap_sol < support_sol


def next_streak(previous: int | None, below: bool | None) -> int | None:
    """The streak after one more snapshot: unknown stays unknown, a close above
    the line resets to zero, a close below adds one."""
    if below is None:
        return None
    if not below:
        return 0
    return (previous or 0) + 1
