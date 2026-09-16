"""The event ↔ mint matching queries (T4.26b): bounded on both sides, one
savepoint per tick, degrading to "not matched this tick" instead of killing
the loop — the T4.24b post-incident rule (``lab_repo_fast.pedigree_for``'s
own shape).

**Bounded, three ways.** The outer scan is ``meme_events``'s own
``ix_meme_events_observed_at`` restricted to
:func:`~hunter_meme_worker.events_config.match_window_h` hours (72 by
default — KB-0100: a plantão event's ``observed_at`` is routinely hours in
the past by the time it is registered, so the lookback has to reach back
past the event's own age, not just past a tick). The inner read of
``meme_tokens`` is **one query**, floored at the earliest of every active
event's own cursor (``ix_meme_tokens_created_at``, unchanged since 0021) —
never a scan of the ~40 k-rows/day table, and in steady state (cursors
already warm) it is only the coins born since the last tick, system-wide.
The event × candidate cross product then runs in Python
(:mod:`hunter_indicators.meme.event_match`, pure): both sides are small (a
handful of events a day, a slice of a minute of coins), so this costs
nothing next to the two queries. The plan is recorded in
``.claude/state/notes-T4.26b.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_indicators.meme.event_match import event_hints, event_match_kind, is_match
from hunter_meme_worker.events_config import match_grace_min, match_window_h

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "EventCounts",
    "MatchedEvent",
    "count_events",
    "link_proposals",
    "match_events_once",
]

_logger = get_logger(__name__)

STATEMENT_TIMEOUT_MS: Final = 5000


@dataclass(frozen=True, slots=True)
class MatchedEvent:
    event_id: str
    mint: str
    match_kind: str


@dataclass(frozen=True, slots=True)
class _ScanTarget:
    event_id: str
    symbol_hint: str | None
    handle_hint: str | None
    notes: dict[str, Any]
    since: datetime
    """The floor this event's own coins are read from this tick — its cursor
    if it has one, else ``observed_at`` minus the backward grace."""


_SCAN_TARGETS = text(
    "SELECT id::text AS event_id, symbol_hint, handle_hint, notes, observed_at, "
    "  last_scanned_created_at "
    "FROM meme_events WHERE observed_at >= :since"
)

_CANDIDATE_TOKENS = text(
    "SELECT mint, symbol, name, twitter, created_at "
    "FROM meme_tokens WHERE created_at > :floor AND created_at <= :now"
)

_INSERT_MATCH = text(
    "INSERT INTO meme_event_matches (event_id, mint, match_kind) "
    "VALUES (:event_id, :mint, :match_kind) "
    "ON CONFLICT (event_id, mint) DO NOTHING "
    "RETURNING event_id::text AS event_id, mint, match_kind"
)

_ADVANCE_CURSOR = text("UPDATE meme_events SET last_scanned_created_at = :now WHERE id = ANY(:ids)")

_LINK_PROPOSAL = text(
    "UPDATE meme_proposals SET event_id = :event_id WHERE mint = :mint AND event_id IS NULL "
    "RETURNING id"
)


async def _scan_targets(session: AsyncSession, *, since: datetime) -> list[_ScanTarget]:
    grace = timedelta(minutes=match_grace_min())
    rows = (await session.execute(_SCAN_TARGETS, {"since": since})).mappings().all()
    out: list[_ScanTarget] = []
    for r in rows:
        cursor = r["last_scanned_created_at"]
        since_row = cursor if cursor is not None else r["observed_at"] - grace
        out.append(
            _ScanTarget(
                event_id=r["event_id"],
                symbol_hint=r["symbol_hint"],
                handle_hint=r["handle_hint"],
                notes=r["notes"] or {},
                since=since_row,
            )
        )
    return out


async def match_events_once(session: AsyncSession, *, now: datetime) -> list[MatchedEvent] | None:
    """Every event inside the matching window against the coins it could
    name. ``None`` (not an empty list) means the savepoint rolled back — the
    tick goes on with nothing recorded instead of dying."""
    since_observed = now - timedelta(hours=match_window_h())
    try:
        async with session.begin_nested():
            await session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            targets = await _scan_targets(session, since=since_observed)
            if not targets:
                return []
            floor = min(t.since for t in targets)
            candidates = (
                (await session.execute(_CANDIDATE_TOKENS, {"floor": floor, "now": now}))
                .mappings()
                .all()
            )
            matched: list[MatchedEvent] = []
            for target in targets:
                hints = event_hints(
                    symbol_hint=target.symbol_hint,
                    handle_hint=target.handle_hint,
                    notes=target.notes,
                )
                kind = event_match_kind(target.notes)
                for candidate in candidates:
                    if candidate["created_at"] <= target.since:
                        continue
                    if not is_match(
                        hints,
                        symbol=candidate["symbol"],
                        name=candidate["name"],
                        twitter=candidate["twitter"],
                    ):
                        continue
                    inserted = (
                        (
                            await session.execute(
                                _INSERT_MATCH,
                                {
                                    "event_id": target.event_id,
                                    "mint": candidate["mint"],
                                    "match_kind": kind,
                                },
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if inserted is not None:
                        matched.append(
                            MatchedEvent(
                                event_id=inserted["event_id"],
                                mint=inserted["mint"],
                                match_kind=inserted["match_kind"],
                            )
                        )
            await session.execute(
                _ADVANCE_CURSOR, {"now": now, "ids": [t.event_id for t in targets]}
            )
    except DBAPIError as exc:
        _logger.warning("meme_events_match_failed", error=type(exc.orig).__name__)
        return None
    return matched


async def link_proposals(session: AsyncSession, matched: list[MatchedEvent]) -> int:
    """Every open or recent proposal for a newly matched mint gets the
    event's id — idempotent (``event_id IS NULL``), so a re-run links nothing
    twice. Linked whether the match is ``buy`` or ``avoid``: an ``avoid``
    match is exactly the case a human most needs the reason attached to."""
    linked = 0
    for m in matched:
        result = await session.execute(_LINK_PROPOSAL, {"event_id": m.event_id, "mint": m.mint})
        linked += len(result.scalars().all())
    return linked


_COUNTS = text(
    "SELECT "
    "  count(*) FILTER (WHERE NOT EXISTS ("
    "    SELECT 1 FROM meme_event_matches m WHERE m.event_id = e.id)) AS open, "
    "  count(*) FILTER (WHERE EXISTS ("
    "    SELECT 1 FROM meme_event_matches m WHERE m.event_id = e.id "
    "      AND m.matched_at >= :hour_ago)) AS matched_1h "
    "FROM meme_events e WHERE observed_at >= :day_ago"
)


@dataclass(frozen=True, slots=True)
class EventCounts:
    open: int
    matched_1h: int


async def count_events(session: AsyncSession, *, now: datetime) -> EventCounts:
    """``events_open``/``events_matched_1h`` (the adendo's heartbeat fields) —
    one cheap aggregate over the last 24 h, the same tiny table the match
    query already reads. "Open" now means "named no coin yet at all", read
    from :class:`~hunter_core.db.models.MemeEventMatch`, not the legacy
    ``mint`` column this job no longer writes."""
    row = (
        await session.execute(
            _COUNTS, {"hour_ago": now - timedelta(hours=1), "day_ago": now - timedelta(days=1)}
        )
    ).one()
    return EventCounts(open=int(row.open), matched_1h=int(row.matched_1h))
