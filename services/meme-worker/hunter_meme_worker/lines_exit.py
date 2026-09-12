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
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT

__all__ = ["SupportLine", "below_support", "next_streak", "support_at"]


@dataclass(frozen=True, slots=True)
class SupportLine:
    """One folded minute's support line, as ``meme_features_1m`` stores it."""

    end_time: datetime
    support_sol: Decimal
    slope_per_min: Decimal


def support_at(lines: Sequence[SupportLine], at: datetime) -> Decimal | None:
    """The newest line folded at or before ``at``, projected to ``at``; ``None``
    when no minute at or before ``at`` drew one."""
    usable = [line for line in lines if line.end_time <= at]
    if not usable:
        return None
    line = max(usable, key=lambda item: item.end_time)
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
