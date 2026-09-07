"""The collector's topology, unioned: N shard heartbeats, one honest row.

T2.5g. Until now one process wrote ``hb:market:{exchange}`` and this API read
it. Splitting the collector into ``MARKET_SHARD=i/N`` processes (the only way
the measured 200-market load fits in one core each) means N hashes,
``hb:market:{exchange}:{i}of{N}``, and exactly one place that can turn them
back into "this exchange is healthy" without lying:

- **the expected N is self-declared.** This API does not read the collector's
  environment, so each shard publishes ``shard_index``/``shard_total`` in its
  own hash. Expected = the largest ``shard_total`` any *live* shard declares,
  and only shards agreeing with it are counted — during a topology change
  ``0of2`` does not fill a slot of a 4-shard cluster;
- **partial is never healthy.** ``shards_reporting < shards_expected`` reports
  ``ws_state = "stale"``, whatever the surviving shards say. A dead shard is
  50 markets nobody is collecting;
- **nothing reporting means the topology is unknown**, not "1 shard, 0 alive":
  ``shards_expected`` comes back ``None`` and ``ws_state`` ``"unavailable"``;
- **the worst shard wins** for ``ws_state``, and the *oldest* ``last_event_at``
  is the exchange's — the aggregate must never look fresher than its slowest
  slice;
- **counts of markets and gaps are still Postgres's** (``build_market_status``),
  never a sum of self-reported shard fields: summing loses exactly the shard
  that is missing, which is the case this module exists to surface.

Freshness is checked here rather than left to the key's own 30s TTL: a
``SCAN``/``HGETALL`` racing an expiry, or a producer whose clock is ahead, must
not count as a live shard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import ensure_utc
from hunter_core.redis import keys

if TYPE_CHECKING:
    from collections.abc import Iterable

    import redis.asyncio as redis_asyncio

SHARD_ALIVE_S = 30.0
"""How old a shard's ``ts`` may be and still count. The hash's own TTL
(``HB_TTL_S``), so the verdict does not depend on winning a race with expiry."""

CLOCK_SKEW_TOLERANCE_S = 2.0
"""Mirrors ``services/system_status.py``'s constant: a ``ts`` further ahead of
``now`` than this is a skewed clock, not a live shard."""

SCAN_COUNT = 100

STALE = "stale"
"""The aggregate ``ws_state`` when a declared shard is not reporting. Not one
of the collector's own states — it is a statement about the *cluster*, and the
UI shows it as not-green (``live-status.tsx`` maps anything that is not
``connected``/``reconnecting`` to the red dot)."""

UNAVAILABLE = "unavailable"

_WS_RANK = {"connected": 0, "idle": 1, "connecting": 2, "reconnecting": 3, "disconnected": 4}
_WORST_RANK = 5
_SHARD_SUFFIX = re.compile(r":(\d+)of(\d+)$")


@dataclass(frozen=True, slots=True)
class CollectorView:
    """One exchange's collector, however many processes it is made of."""

    ws_state: str
    last_event_at: datetime | None = None
    reconnects: int | None = None
    shards_expected: int | None = None
    shards_reporting: int = 0


@dataclass(frozen=True, slots=True)
class _Shard:
    index: int
    total: int
    ws_state: str
    last_event_at: datetime | None
    reconnects: int | None


def _instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _fresh(fields: dict[str, str], now: datetime) -> bool:
    ts = _instant(fields.get("ts"))
    if ts is None:
        return False
    age_s = (now - ts).total_seconds()
    return -CLOCK_SKEW_TOLERANCE_S <= age_s <= SHARD_ALIVE_S


def _shard_from(key: str, fields: dict[str, str], now: datetime) -> _Shard | None:
    """A shard only counts when the key's ``{i}of{N}`` suffix, the hash's own
    ``shard_index``/``shard_total`` and its freshness all agree — otherwise it
    is some other key that happens to live under ``hb:market:{exchange}:``."""
    match = _SHARD_SUFFIX.search(key)
    if match is None or not _fresh(fields, now):
        return None
    index, total = int(match.group(1)), int(match.group(2))
    if _int(fields.get("shard_index")) != index or _int(fields.get("shard_total")) != total:
        return None
    if total < 1 or not 0 <= index < total:
        return None
    return _Shard(
        index=index,
        total=total,
        ws_state=fields.get("ws_state") or UNAVAILABLE,
        last_event_at=_event_stamp(fields.get("last_event_at"), now),
        reconnects=_int(fields.get("reconnects")),
    )


def _event_stamp(raw: str | None, now: datetime) -> datetime | None:
    """A ``last_event_at`` further ahead of ``now`` than the skew tolerance is
    not evidence of a live feed (Astra, T2.5g diff review): it must be treated
    as *absent* here rather than survive into the aggregate's ``min``, where a
    healthy sibling's timestamp would hide it."""
    stamp = _instant(raw)
    if stamp is None or (now - stamp).total_seconds() < -CLOCK_SKEW_TOLERANCE_S:
        return None
    return stamp


def _reduce(shards: list[_Shard], expected: int) -> CollectorView:
    reporting = len(shards)
    ws_state = max((s.ws_state for s in shards), key=lambda state: _WS_RANK.get(state, _WORST_RANK))
    stamps = [s.last_event_at for s in shards if s.last_event_at is not None]
    # Every reporting shard must have one, or the exchange has none: a shard
    # that has never seen an event would otherwise inherit a sibling's fresh
    # timestamp and the row would read "live" for markets nobody has data for
    # (Astra, T2.5g diff review).
    if len(stamps) != reporting:
        stamps = []
    reconnects = [s.reconnects for s in shards if s.reconnects is not None]
    return CollectorView(
        # A missing shard outranks every state its siblings report: 50 markets
        # with nobody on them is not "connected".
        ws_state=STALE if reporting < expected else ws_state,
        last_event_at=min(stamps) if stamps else None,
        reconnects=sum(reconnects) if reconnects else None,
        shards_expected=expected,
        shards_reporting=reporting,
    )


async def read_collector(
    redis: redis_asyncio.Redis, exchange: str, *, now: datetime
) -> CollectorView:
    """Union every shard heartbeat of ``exchange`` (falling back to the solo
    key). Raises ``redis.exceptions.RedisError`` — the caller decides whether
    one exchange degrades or the whole endpoint answers 503."""
    client: Any = redis
    seen: dict[str, dict[str, str]] = {}
    async for raw_key in client.scan_iter(
        match=keys.market_heartbeat_shard_pattern(exchange), count=SCAN_COUNT
    ):
        # SCAN may return the same key twice — dict, not list.
        key = cast(bytes, raw_key).decode(errors="replace")
        if key not in seen:
            seen[key] = _decode(await client.hgetall(key))
    shards = [s for key, fields in seen.items() if (s := _shard_from(key, fields, now)) is not None]
    if shards:
        expected = max(shard.total for shard in shards)
        # A shard declaring a different N belongs to another topology (a
        # rolling change, or a leftover) and fills no slot of this one.
        current = {shard.index: shard for shard in shards if shard.total == expected}
        return _reduce(list(current.values()), expected)

    solo = _decode(await client.hgetall(keys.heartbeat("market", exchange)))
    if solo and _fresh(solo, now):
        return CollectorView(
            ws_state=solo.get("ws_state") or UNAVAILABLE,
            last_event_at=_event_stamp(solo.get("last_event_at"), now),
            reconnects=_int(solo.get("reconnects")),
            shards_expected=_int(solo.get("shard_total")) or 1,
            shards_reporting=1,
        )
    # Nothing reporting. Not "1 of 1 missing" — with no live heartbeat this API
    # does not know how many shards should exist, and inventing one would be a
    # fake number. And a hash that exists but is stale (or whose clock is ahead
    # of ours) reports nothing of its own either: passing its ``ws_state``
    # through would print "connected" next to "0 shards reporting" (Astra,
    # T2.5g diff review).
    return CollectorView(ws_state=UNAVAILABLE, shards_expected=None, shards_reporting=0)


def _decode(raw: object) -> dict[str, str]:
    fields = cast("dict[bytes, bytes]", raw)
    return {
        key.decode(errors="replace"): value.decode(errors="replace")
        for key, value in fields.items()
    }


async def summarize_collectors(
    redis: redis_asyncio.Redis, exchanges: Iterable[str], *, now: datetime
) -> tuple[int | None, int | None]:
    """``(shards_expected, shards_reporting)`` summed over ``exchanges`` — the
    numbers behind the web's "N shards, M mercados" label. ``(None, None)``
    when no collector declared a topology at all, so the label is omitted
    rather than printed as a zero."""
    expected = reporting = 0
    declared = False
    for exchange in sorted(set(exchanges)):
        view = await read_collector(redis, exchange, now=now)
        if view.shards_expected is None:
            continue
        declared = True
        expected += view.shards_expected
        reporting += view.shards_reporting
    return (expected, reporting) if declared else (None, None)


__all__ = ["CollectorView", "read_collector", "summarize_collectors"]
