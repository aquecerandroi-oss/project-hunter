"""The live decision consumer's own backlog, read straight from Redis (T3.74b).

Split from :mod:`.budget` for the same reason :mod:`hunter_strategy_worker.roster`
was split from ``catalogue``: one cohesive read (parse ``XINFO GROUPS``, find one
entry, pull its ``lag``) with its own failure modes, kept out of the gate that
consumes it so ``budget.py`` stays under the 350-line budget.

``lag`` (Redis 7+) is entries the stream has added minus entries the group has
read — the backlog the group has not even picked up yet. It is independent of
``outbox_lag_s`` (:mod:`hunter_strategy_worker.heartbeat`), which measures what
happens *after* a decision is already made; T3.74 found the live lane's worst
measured decision lag (125 s+) with ``outbox_lag_s`` reading ``0.0`` throughout
(notes-T3.74.md §3), so this is a second, independent signal, not a rename.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_strategy_worker.config import CONSUMER_GROUP

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

LIVE_CONSUMER_STREAM = Streams.MARKET_CANDLES_CLOSED
LIVE_CONSUMER_GROUP = CONSUMER_GROUP

__all__ = ["LIVE_CONSUMER_GROUP", "LIVE_CONSUMER_STREAM", "group_lag"]


def _find_lag(groups: list[dict[Any, Any]], name: str) -> int | None:
    """The ``lag`` of the entry named ``name``, comparing ``name`` against
    whichever type Redis sent it as (``str`` or ``bytes``) instead of decoding
    an *other* group's name — a group this gate never asked about may carry
    anything, and decoding it just to reject it is a needless way to raise."""
    wanted = (name, name.encode("utf-8"))
    for entry in groups:
        fields = {(k.decode() if isinstance(k, bytes) else str(k)): v for k, v in entry.items()}
        if fields.get("name") not in wanted:
            continue
        raw_lag = fields.get("lag")
        if raw_lag is None:
            return None
        try:
            return int(raw_lag)
        except (TypeError, ValueError):
            return None
    return None


async def group_lag(
    redis: redis_asyncio.Redis,
    *,
    stream: str = LIVE_CONSUMER_STREAM,
    group: str = LIVE_CONSUMER_GROUP,
) -> int | None:
    """``lag`` for ``group`` on ``stream``, or ``None`` when it cannot be read.

    ``None`` covers four cases the caller must treat alike (fail closed, never
    as zero): the ``XINFO GROUPS`` call itself failing, ``group`` not existing on
    ``stream`` at all, a group entry with no ``lag`` field or an explicit
    ``lag: null`` (both mean Redis cannot compute it, e.g. a group whose first
    entry was trimmed by ``MAXLEN`` before it read anything — a group Redis
    cannot name is not proof the group is fine, it is proof nothing was
    established), and — Astra, T3.74b review — a parsing failure on some
    *other* group's entry (an un-decodable name), which must not raise past
    this function and crash the gate over a group nobody asked about.
    """
    try:
        groups: list[dict[Any, Any]] = await cast("Any", redis).xinfo_groups(stream)
        lag = _find_lag(groups, group)
    except Exception:
        logger.warning("replay_consumer_lag_unreadable", stream=stream)
        return None
    if lag is None:
        logger.warning("replay_consumer_lag_unreadable", stream=stream)
    return lag
