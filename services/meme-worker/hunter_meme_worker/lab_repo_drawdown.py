"""The recent drawdown of the real SOL on the **15-second lane** (T4.61a,
EXP-M13 / KB-0118) — the fill the event lane already had and this lane never
did, so a rule set that turns ``max_recent_drawdown_pct`` on could only ever
refuse ``recent_drawdown_unknown`` here.

**Where the reserve comes from.** ``meme_features_15s`` carries no reserve
column: every 15-second row names its newest photo (``snapshot_observed_at``,
``snapshot_source``) and the real SOL lives on ``meme_curve_snapshots``,
which is exactly the input EXP-M13 froze (``real_sol_reserves``, **never**
``mcap_sol`` — a Mayhem coin's market cap is rewritten by the agent's virtual
SOL, KB-0115). So this module reads **one bounded query per tick** over the
judged mints — the last ``FILL_LOOKBACK_S`` of photos, on
``ix_meme_curve_snapshots_mint_observed`` — and folds each row's own instant
with :func:`hunter_indicators.meme.drawdown.recent_drawdown`, the same
arithmetic the event lane uses (one definition, two lanes).

**Non-anticipation, twice.** The query is bounded by the tick's ceiling
(``received_at <= max(as_of)``); the fold is bounded by the **row's** own
``as_of`` (a backlog row of 40 s ago must not see the photo of 10 s ago), which
``recent_drawdown`` enforces itself over a sequence.

**Why a 120 s lookback and a 60 s gate window.** The gate refuses only when
the peak is at most ``recent_drawdown_window_s`` (60 s) old — the frozen
definition — and passes a fall whose peak is older (KB-0118's best cell,
+0,566 R, dd > 50 % with a 60–180 s old peak). Folding over the gate's own
60 s would make that age invisible (a peak inside a 60 s window is never
older than 60 s); folding over the 15-second series' own horizon (120 s,
``snapshots_120s``) lets the row carry the age and the gate decide. The
lookback is **not** a param: a set moves ``recent_drawdown_window_s``, and
the row's horizon stays the series'.

**Fail closed, by name.** No photo known by the instant is ``no_observation``;
one photo is ``too_few_points`` (it cannot say whether anything fell); a newest
photo older than ``DEFAULT_MAX_GAP_S`` is ``stale``. A read that fails (timeout)
leaves every row's three fields ``None`` — ``recent_drawdown_unknown`` for a set
with the guard, nothing for a set without — and is logged, never raised: the
tick goes on, as the pedigree and E2-b reads already do.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_indicators.meme.drawdown import (
    DEFAULT_MAX_GAP_S,
    NO_OBSERVATION,
    TOO_FEW_POINTS,
    RecentDrawdown,
    ReservePoint,
    recent_drawdown,
)
from hunter_meme_worker.proposals_row import GateRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "FILL_LOOKBACK_S",
    "drawdown_of",
    "fill_recent_drawdown",
    "reserve_points_for",
    "with_recent_drawdown",
]

FILL_LOOKBACK_S: Final = 120
"""The 15-second series' own horizon (``snapshots_120s``): the peak is looked
for in the last 120 s so the gate can read the peak's age against its 60 s."""

_RESERVES = text(
    "SELECT mint, observed_at, received_at, real_sol_reserves "
    "FROM meme_curve_snapshots "
    "WHERE mint = ANY(:mints) AND observed_at > :floor AND observed_at <= :ceiling "
    "  AND received_at <= :ceiling "
    "ORDER BY mint, observed_at, received_at"
)
"""``repo_fast._POINTS``'s shape (the fold the 15-second row itself came
from), bounded on both ends by the tick's rows. The partition-local children of
``ix_meme_curve_snapshots_mint_observed`` serve it; the ceiling prunes the
later monthly partitions — proved by ``EXPLAIN`` in ``test_lab_drawdown.py``."""

_logger = get_logger(__name__)


def drawdown_of(
    points: Sequence[ReservePoint],
    *,
    as_of: datetime,
    lookback_s: int = FILL_LOOKBACK_S,
    max_gap_s: int = DEFAULT_MAX_GAP_S,
) -> RecentDrawdown:
    """One row's three fields from the photos of its mint: the fold of
    :func:`recent_drawdown` over the last ``lookback_s`` known by ``as_of``,
    or a named unknown. Pure; total."""
    start = as_of - timedelta(seconds=lookback_s)
    known = [
        p
        for p in points
        if p.received_at <= as_of and p.observed_at <= as_of and p.observed_at > start
    ]
    if not known:
        return RecentDrawdown(None, None, NO_OBSERVATION)
    if len(known) < 2:
        return RecentDrawdown(None, None, TOO_FEW_POINTS)
    return recent_drawdown(known, as_of=as_of, window_s=lookback_s, max_gap_s=max_gap_s)


def fill_recent_drawdown(
    rows: Iterable[GateRow], points: Mapping[str, Sequence[ReservePoint]]
) -> list[GateRow]:
    """Every row with its own ``recent_drawdown_*`` — a mint absent from
    ``points`` is ``no_observation``, never a clean row."""
    out: list[GateRow] = []
    for row in rows:
        fold = drawdown_of(points.get(row.mint, ()), as_of=row.end_time)
        out.append(
            replace(
                row,
                recent_drawdown_pct=fold.drawdown_pct,
                recent_drawdown_peak_age_s=fold.peak_age_s,
                recent_drawdown_reason=fold.reason,
            )
        )
    return out


async def reserve_points_for(
    session: AsyncSession, rows: Sequence[GateRow]
) -> dict[str, list[ReservePoint]] | None:
    """The real-SOL photos of the judged mints over ``[min(as_of) − lookback,
    max(as_of)]``, received by ``max(as_of)``; ``None`` when the read failed
    (logged), so the caller can tell "nothing stored" from "not read"."""
    if not rows:
        return {}
    mints = sorted({row.mint for row in rows})
    as_ofs = [row.end_time for row in rows]
    params = {
        "mints": mints,
        "floor": min(as_ofs) - timedelta(seconds=FILL_LOOKBACK_S),
        "ceiling": max(as_ofs),
    }
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = 8000"))
            found = (await session.execute(_RESERVES, params)).mappings().all()
    except DBAPIError as exc:
        _logger.warning(
            "meme_drawdown_read_failed", mints=len(mints), error=type(exc.orig).__name__
        )
        return None
    out: dict[str, list[ReservePoint]] = {}
    for r in found:
        out.setdefault(str(r["mint"]), []).append(
            ReservePoint(
                observed_at=r["observed_at"],
                received_at=r["received_at"],
                real_sol=r["real_sol_reserves"],
            )
        )
    return out


async def with_recent_drawdown(session: AsyncSession, rows: list[GateRow]) -> list[GateRow]:
    """The rows of one tick with EXP-M13's three fields filled; on a failed
    read the rows come back untouched (all three ``None``)."""
    points = await reserve_points_for(session, rows)
    if points is None:
        return rows
    return fill_recent_drawdown(rows, points)
