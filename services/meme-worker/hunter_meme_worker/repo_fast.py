"""The radar-side reads and writes of the 15-second series (T4.16) — as
``hunter_worker``, never as owner (``repo.py``'s discipline): the curve
photos the fast lane may fold for an instant, and the rows it writes.

**Non-anticipation in SQL**: :func:`load_fast_points` returns only photos
with ``received_at <= as_of`` — the predicate the tape (``repo_tape.py``) and
the lines (``repo_lines.py``) already use — so a photo the chain delivered
after the instant is not an input of that instant, whatever its block time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_indicators.meme.fast import WINDOW_S, FastPoint
from hunter_meme_worker.features_fast import Fast15sRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["FastPoints", "insert_fast_rows", "load_fast_points"]

LOOKBACK_S = WINDOW_S + 60
"""Photos older than the window plus a minute cannot be the 60 s reference of
any photo received by ``as_of``; reading them would be reading for nothing."""

_POINTS = text(
    "SELECT mint, observed_at, received_at, source, mcap_sol, real_token_reserves "
    "FROM meme_curve_snapshots "
    "WHERE mint = ANY(:mints) AND observed_at > :start AND received_at <= :as_of "
    "ORDER BY mint, observed_at, received_at"
)

_ROW_COLUMNS = tuple(Fast15sRow.__dataclass_fields__)
_INSERT_ROW = text(
    f"INSERT INTO meme_features_15s ({', '.join(_ROW_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _ROW_COLUMNS)}) "
    "ON CONFLICT (as_of, mint, features_version) DO NOTHING"
)


class FastPoints:
    """The photos of many mints for one instant, and the source of each mint's newest."""

    def __init__(self) -> None:
        self.points: dict[str, list[FastPoint]] = {}
        self.newest_source: dict[str, str] = {}

    def add(self, mint: str, point: FastPoint, source: str) -> None:
        self.points.setdefault(mint, []).append(point)
        self.newest_source[mint] = source  # rows arrive ordered by observed_at, received_at


async def load_fast_points(
    session: AsyncSession, *, mints: Sequence[str], as_of: datetime
) -> FastPoints:
    """Every photo of ``mints`` that had reached us by ``as_of`` and is young
    enough to matter (the last ``LOOKBACK_S``), per mint."""
    out = FastPoints()
    if not mints:
        return out
    params = {
        "mints": list(mints),
        "as_of": as_of,
        "start": as_of - timedelta(seconds=LOOKBACK_S),
    }
    for r in (await session.execute(_POINTS, params)).mappings():
        out.add(
            str(r["mint"]),
            FastPoint(
                observed_at=r["observed_at"],
                received_at=r["received_at"],
                mcap_sol=r["mcap_sol"],
                real_token_reserves=r["real_token_reserves"],
            ),
            str(r["source"]),
        )
    return out


async def insert_fast_rows(session: AsyncSession, rows: Sequence[Fast15sRow]) -> int:
    """One statement per tick's worth of rows; returns how many were offered."""
    if not rows:
        return 0
    await session.execute(_INSERT_ROW, [asdict(row) for row in rows])
    return len(rows)
