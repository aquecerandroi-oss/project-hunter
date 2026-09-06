"""Was this market in the eligible universe *at that bar's close*?

``markets.is_monitored`` is overwritten in place by every universe refresh, so
reading it now says nothing about an hour ago: a market that was ineligible at
12:15 and entered the universe at 12:16 would, for a bar delivered at 12:17,
look like it had always been there — and a false bar evaluated on that reading
could re-arm a slot it had no right to re-arm (Astra, S2 design review,
must-fix 4, re-raised in the diff review).

There is no per-bar membership history in the schema, and S0 is frozen. What
*does* exist is the event the market-worker publishes **only when the monitored
set changes** (``universe.refresh_universe``): so if no ``market.universe.changed``
was published for this exchange after ``source_bar_close``, the set has not
changed since, and the current flag *is* the flag of that instant. That is a
proof, not an estimate.

Two declared limits:

- publication is best-effort (``market_worker.publication.publish`` swallows a
  failed ``XADD`` and records a ``system_event``), so a lost publication makes
  this answer optimistic. It is logged on the producer side, and the coarse
  ``eligibility_max_lag_s`` gate still applies;
- the stream is trimmed at ``MAXLEN`` 1000. An empty window is read as "no
  change observed", which is the same optimistic direction.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import ensure_utc
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)
PROBE_ENTRIES = 50
"""How far back to look for this exchange's newest universe change."""

__all__ = ["PROBE_ENTRIES", "universe_changed_after"]


async def universe_changed_after(
    redis: redis_asyncio.Redis, *, exchange: str, instant: datetime
) -> bool:
    """Whether the monitored set of ``exchange`` changed after ``instant``.

    ``True`` means the current ``is_monitored`` cannot stand as evidence for a
    bar that closed at ``instant``. A Redis failure answers ``True`` as well:
    when membership cannot be established, the evaluation must be unavailable,
    not optimistic.
    """
    cut = ensure_utc(instant)
    try:
        entries: Any = await redis.xrevrange(Streams.MARKET_UNIVERSE_CHANGED, count=PROBE_ENTRIES)
    except Exception:
        logger.warning("shadow_universe_probe_failed", exchange=exchange)
        return True
    for _entry_id, fields in entries:
        raw = fields.get(b"data") or fields.get("data")
        if raw is None:
            continue
        try:
            envelope = EventEnvelope.from_bytes(raw)
        except Exception:
            continue
        if envelope.key != exchange:
            continue
        return ensure_utc(envelope.ts) > cut
    return False
