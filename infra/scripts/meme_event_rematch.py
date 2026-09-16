"""``meme_event.py rematch`` — the backfill entry point (T4.26b): today's 8
plantão events, registered under the old 65-minute lookback/forward-only
window (0041), get matched after deploy without waiting for their
``observed_at`` to fall inside a fresh 72 h window by luck.

Same rule as the per-minute job (``hunter_meme_worker.events_repo``, which
this module does not import — a script must not import a service package for
shared logic, ``infra/scripts/meme_ops_db.py``'s own precedent; the pure
matcher both share lives in :mod:`hunter_indicators.meme.event_match`).
Dry-run by default, auditable in ``system_events`` on ``--apply`` — the same
discipline as ``add``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from meme_ops_db import record_event
from sqlalchemy import text

from hunter_indicators.meme.event_match import event_hints, event_match_kind, is_match

COMPONENT = "meme_event"
DEFAULT_GRACE_MIN = 30
"""The worker's own default (``MEME_EVENT_MATCH_GRACE_MIN``) — not a flag
here; a one-off backfill does not need its grace tuned per run."""

__all__ = ["Connection", "rematch"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


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
    "RETURNING event_id"
)
_ADVANCE_CURSOR = text("UPDATE meme_events SET last_scanned_created_at = :now WHERE id = ANY(:ids)")


def _since_of(event: Any) -> datetime:
    cursor = event["last_scanned_created_at"]
    if cursor is not None:
        return cursor
    return event["observed_at"] - timedelta(minutes=DEFAULT_GRACE_MIN)


async def rematch(conn: Connection, *, hours: int, now: datetime, apply: bool) -> tuple[int, str]:
    """Everything the per-minute job would match on its next tick, run once by
    hand — the same rule, the same idempotent insert (``ON CONFLICT DO
    NOTHING``), the same cursor advance so the next regular tick does not
    redo this work."""
    since = now - timedelta(hours=hours)
    targets = (await conn.execute(_SCAN_TARGETS, {"since": since})).mappings().all()
    if not targets:
        return 0, f"rematch: 0 events with observed_at >= {since.isoformat()}"
    floor = min(_since_of(t) for t in targets)
    candidates = (
        (await conn.execute(_CANDIDATE_TOKENS, {"floor": floor, "now": now})).mappings().all()
    )
    matches: list[dict[str, Any]] = []
    for target in targets:
        hints = event_hints(
            symbol_hint=target["symbol_hint"],
            handle_hint=target["handle_hint"],
            notes=target["notes"] or {},
        )
        kind = event_match_kind(target["notes"] or {})
        event_since = _since_of(target)
        for candidate in candidates:
            if candidate["created_at"] <= event_since:
                continue
            if is_match(
                hints,
                symbol=candidate["symbol"],
                name=candidate["name"],
                twitter=candidate["twitter"],
            ):
                matches.append(
                    {
                        "event_id": target["event_id"],
                        "mint": candidate["mint"],
                        "match_kind": kind,
                    }
                )
    plan = (
        f"rematch: {len(targets)} events, {len(candidates)} candidate coins since "
        f"{since.isoformat()}, {len(matches)} rule matches"
    )
    if not apply:
        return 0, plan + "\ndry-run: nothing written (rematch --apply)"
    inserted = 0
    for match in matches:
        result = await conn.execute(_INSERT_MATCH, match)
        if result.mappings().first() is not None:
            inserted += 1
    await conn.execute(_ADVANCE_CURSOR, {"now": now, "ids": [t["event_id"] for t in targets]})
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="rematched",
        message=f"{inserted} new meme_event_matches over {len(targets)} events, hours={hours}",
    )
    return 0, plan + f"\napplied: {inserted} new meme_event_matches rows; system_events written"
