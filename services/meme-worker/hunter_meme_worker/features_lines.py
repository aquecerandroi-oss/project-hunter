"""The T4.10 columns of the minute — the lines and the hype — as the fold
writes them (``meme_features_v3``, ``0026``). The arithmetic is the pure
package's (:mod:`hunter_indicators.meme.lines`, :mod:`~.hype`); this module
only turns the radar's rows into those inputs and the results into columns.

**Non-anticipation is decided in the inputs.** The line points come from
``meme_curve_snapshots`` with ``received_at <= end_time`` (``repo_lines.py``)
and ``compute_lines`` refuses any later point again; the board standing is
read from the board rows of the **same closed minute** whose ``received_at``
is not after it. ``test_features_lines.py`` proves both: a photo or a board
row that reached us after the close changes nothing in the row.

``hype_score`` reads the tape of the minute (``buys_1m``, ``unique_buyers``),
the mint's best position on ``movers``/``new`` and its ``has_social`` from the
board rows, and ``snipers`` from the holders reading the minute already uses —
so the score is a function of columns the same row carries, never of a source
the row does not name.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_indicators.meme.hype import HypeInputs, hype_score
from hunter_indicators.meme.lines import LinePoint, compute_lines

if TYPE_CHECKING:
    from hunter_meme_worker.features_tape import TapeMinute
    from hunter_meme_worker.repo_boards import BoardMinuteRow

__all__ = ["HYPE_BOARDS", "BoardStanding", "board_standing", "hype_columns", "line_columns"]

HYPE_BOARDS = frozenset({"movers", "new"})
"""The two boards whose position feeds the score (the brief's table)."""


@dataclass(frozen=True, slots=True)
class BoardStanding:
    """What the site's boards said about one mint in one closed minute."""

    best_position: int | None
    """Lowest 0-based position across :data:`HYPE_BOARDS`; ``None`` when the
    mint sat on neither (it may still be on ``graduating``/``graduated``)."""
    has_social: bool | None


def board_standing(
    rows: Iterable[BoardMinuteRow], *, mint: str, end_time: datetime
) -> BoardStanding | None:
    """The mint's standing from the rows of ``end_time`` received by then, or
    ``None`` when no board row of that minute names it."""
    best: int | None = None
    social: bool | None = None
    present = False
    for row in rows:
        if row.mint != mint or row.minute_end != end_time or row.received_at > end_time:
            continue
        present = True
        if row.board in HYPE_BOARDS:
            best = row.position if best is None else min(best, row.position)
        if row.has_social is not None:
            social = row.has_social if social is None else (social or row.has_social)
    return BoardStanding(best_position=best, has_social=social) if present else None


def line_columns(
    points: Sequence[LinePoint], *, end_time: datetime, mcap_now: Decimal | None
) -> dict[str, object]:
    """The nine line columns plus ``line_points``/``line_reason``."""
    lines = compute_lines(points, end_time=end_time, mcap_now=mcap_now)
    return {
        "mcap_slope_5m": lines.mcap_slope_5m,
        "mcap_slope_15m": lines.mcap_slope_15m,
        "high_15m_sol": lines.high_15m_sol,
        "low_15m_sol": lines.low_15m_sol,
        "breakout_15m": lines.breakout_15m,
        "support_line_sol": lines.support_line_sol,
        "support_line_slope": lines.support_line_slope,
        "higher_lows": lines.higher_lows,
        "distance_to_support_pct": lines.distance_to_support_pct,
        "line_points": lines.line_points,
        "line_reason": lines.line_reason,
    }


def hype_columns(
    *, tape: TapeMinute | None, board: BoardStanding | None, snipers: int | None
) -> dict[str, object]:
    """``hype_score``/``hype_reason`` from the minute's own inputs."""
    result = hype_score(
        HypeInputs(
            buys_1m=None if tape is None else tape.buys,
            unique_buyers_1m=None if tape is None else tape.unique_buyers,
            board_position=None if board is None else board.best_position,
            has_social=None if board is None else board.has_social,
            snipers=snipers,
            tape_present=tape is not None,
            board_present=board is not None,
        )
    )
    return {"hype_score": result.score, "hype_reason": result.reason}
