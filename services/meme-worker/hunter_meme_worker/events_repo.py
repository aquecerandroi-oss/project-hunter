"""The event ↔ mint matching query (T4.26): one savepoint per tick, bounded on
both sides, degrading to "not matched this tick" instead of killing the loop —
the T4.24b post-incident rule (``lab_repo_fast.pedigree_for``'s own shape).

**Bounded, twice:** the outer scan is ``meme_events``'s own partial index
(``ix_meme_events_unmatched``, tiny — a handful of rows a day, human- or
plantão-authored) restricted to :data:`MATCH_LOOKBACK_MINUTES`; for every such
event the inner join reads ``meme_tokens`` through its existing
``ix_meme_tokens_created_at`` range index, restricted to the 60-minute window
the brief names — never a scan of the ~40 k-rows/day table. The plan is
recorded in ``.claude/state/notes-T4.26.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "MATCH_LOOKBACK_MINUTES",
    "MATCH_WINDOW_MINUTES",
    "EventCounts",
    "MatchedEvent",
    "count_events",
    "link_proposals",
    "match_events_once",
]

_logger = get_logger(__name__)

MATCH_LOOKBACK_MINUTES: Final = 65
"""How far back an unmatched event is still worth trying — five minutes past
the brief's own 60-minute matching window, so an event born at the edge of one
tick is not dropped by the next."""

MATCH_WINDOW_MINUTES: Final = 60
"""The brief's own: a mint created in the 60 minutes *after* the event."""

STATEMENT_TIMEOUT_MS: Final = 5000


@dataclass(frozen=True, slots=True)
class MatchedEvent:
    event_id: str
    mint: str


_MATCH = text(
    "WITH candidates AS ("
    "  SELECT e.id AS event_id, t.mint, "
    "         row_number() OVER (PARTITION BY e.id ORDER BY t.created_at) AS rn "
    "  FROM meme_events e "
    "  JOIN meme_tokens t ON t.created_at IS NOT NULL "
    "    AND t.created_at BETWEEN e.observed_at "
    "      AND e.observed_at + make_interval(mins => :window_minutes) "
    "    AND ("
    "      (e.handle_hint IS NOT NULL AND t.twitter IS NOT NULL "
    "        AND t.twitter ILIKE '%' || e.handle_hint || '%') "
    "      OR (e.symbol_hint IS NOT NULL AND t.symbol IS NOT NULL AND t.symbol = e.symbol_hint)"
    "    ) "
    "  WHERE e.mint IS NULL AND e.observed_at >= :since "
    "    AND (e.handle_hint IS NOT NULL OR e.symbol_hint IS NOT NULL)"
    ") "
    "UPDATE meme_events SET mint = c.mint, matched_at = :now "
    "FROM candidates c WHERE meme_events.id = c.event_id AND c.rn = 1 "
    "RETURNING meme_events.id::text AS event_id, c.mint"
)
"""One event names at most one mint — the earliest created inside the window
(``rn = 1``): a shared handle that named several launches (M-P33's siblings)
picks the first, and the rest stay unmatched for the next tick to reconsider
if the first was wrong (never automatically — a human corrects a mismatch)."""

_LINK_PROPOSAL = text(
    "UPDATE meme_proposals SET event_id = :event_id WHERE mint = :mint AND event_id IS NULL "
    "RETURNING id"
)


async def match_events_once(session: AsyncSession, *, now: datetime) -> list[MatchedEvent] | None:
    """Every unmatched, recent event against the mints it could have named.
    ``None`` (not an empty list) means the savepoint rolled back — the tick
    goes on with events unmatched instead of dying."""
    since = now - timedelta(minutes=MATCH_LOOKBACK_MINUTES)
    params = {"since": since, "window_minutes": MATCH_WINDOW_MINUTES, "now": now}
    try:
        async with session.begin_nested():
            await session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            rows = (await session.execute(_MATCH, params)).mappings().all()
    except DBAPIError as exc:
        _logger.warning("meme_events_match_failed", error=type(exc.orig).__name__)
        return None
    return [MatchedEvent(event_id=str(r["event_id"]), mint=str(r["mint"])) for r in rows]


async def link_proposals(session: AsyncSession, matched: list[MatchedEvent]) -> int:
    """Every open or recent proposal for a newly matched mint gets the event's
    id — idempotent (``event_id IS NULL``), so a re-run links nothing twice."""
    linked = 0
    for m in matched:
        result = await session.execute(_LINK_PROPOSAL, {"event_id": m.event_id, "mint": m.mint})
        linked += len(result.scalars().all())
    return linked


_COUNTS = text(
    "SELECT "
    "  count(*) FILTER (WHERE mint IS NULL) AS open, "
    "  count(*) FILTER (WHERE matched_at >= :hour_ago) AS matched_1h "
    "FROM meme_events WHERE observed_at >= :day_ago"
)


@dataclass(frozen=True, slots=True)
class EventCounts:
    open: int
    matched_1h: int


async def count_events(session: AsyncSession, *, now: datetime) -> EventCounts:
    """``events_open``/``events_matched_1h`` (the adendo's heartbeat fields) —
    one cheap aggregate over the last 24 h, the same tiny table the match
    query already reads."""
    row = (
        await session.execute(
            _COUNTS, {"hour_ago": now - timedelta(hours=1), "day_ago": now - timedelta(days=1)}
        )
    ).one()
    return EventCounts(open=int(row.open), matched_1h=int(row.matched_1h))
