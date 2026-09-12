"""The one read the lines need (T4.10): the curve photos of the last sixteen
minutes of every tracked mint, **as they had reached us** by the minute's close
— ``received_at <= end_time``, the same predicate the tape read uses
(``repo_tape.py``). As ``hunter_worker``, never as owner.

Sixteen minutes, not fifteen: the breakout's reference is the previous window
``(end_time − 16 min, end_time − 1 min]`` (``hunter_indicators.meme.lines``).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_indicators.meme.lines import WINDOW_MINUTES, LinePoint

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["load_line_points"]

_LINE_POINTS = text(
    "SELECT mint, observed_at, received_at, mcap_sol FROM meme_curve_snapshots "
    "WHERE mint = ANY(:mints) AND observed_at > :start AND observed_at <= :end_time "
    "  AND received_at <= :end_time ORDER BY mint, observed_at, received_at"
)


async def load_line_points(
    session: AsyncSession, *, mints: Sequence[str], end_time: datetime
) -> dict[str, list[LinePoint]]:
    """The photos the lines may look at for ``end_time``, per mint."""
    if not mints:
        return {}
    params = {
        "mints": list(mints),
        "end_time": end_time,
        "start": end_time - timedelta(minutes=WINDOW_MINUTES + 1),
    }
    out: dict[str, list[LinePoint]] = {mint: [] for mint in mints}
    for r in (await session.execute(_LINE_POINTS, params)).mappings():
        out[str(r["mint"])].append(
            LinePoint(
                observed_at=r["observed_at"], received_at=r["received_at"], mcap_sol=r["mcap_sol"]
            )
        )
    return out
