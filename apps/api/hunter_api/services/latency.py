"""Build :class:`~hunter_api.schemas.latency.LatencyOut` from Redis heartbeats.

See ``schemas/latency.py`` for which key/field each hop reads. Every read is a
plain ``HGETALL``/``SCAN`` — no Prometheus scrape, no new table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from hunter_api.schemas.latency import LatencyHopOut, LatencyOut, LatencySloStatus
from hunter_core.domain.types import utcnow
from hunter_core.latency import classify_slo
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

STRATEGY_SHADOW_KEY = "hb:strategy:shadow"
"""``hunter_strategy_worker.config.HEARTBEAT_KEY`` (T3.74c) -- not imported:
``apps/api`` does not depend on ``services/*`` packages, so the literal is
kept in sync by convention, same as this module's other two keys."""

EXECUTION_PAPER_KEY = "hb:execution:paper"
"""``hunter_execution_worker.config.HEARTBEAT_KEY``."""

MARKET_HEARTBEAT_SCAN_PATTERN = "hb:market:*"
"""Matches every market-worker heartbeat: the solo key, a sharded
``:{i}of{N}`` suffix, and the spot collector's own. The first one carrying an
``ingest_lag_p95_s`` field (present, even if empty, only on a build that has
``hunter_market_worker.latency`` wired) is used -- **not** a full
``hunter_api.services.market_shards``-style union across shards. A registered
simplification (``notes-T3.79.md``): with more than one perpetual shard this
hop reports only whichever shard's key ``SCAN`` happens to return first,
exactly the same category of known gap ``schemas/system.py`` already names
for ``hb:execution:paper``'s missing outbox-lag field."""

SCAN_COUNT = 100

_INGEST = "ingest"
_FLUSH = "flush"
_DECISION = "decision"
_ADMISSION = "admission"
_FILL = "fill"
_END_TO_END = "end_to_end"

# (warn_s, critical_s) per hop -- PIPELINE.md §6b's budget table. A hop with a
# single stated ceiling (everything but "decision") uses half of it as the
# warn boundary; "decision" already states both numbers (median < 5s, p95 <
# 20s) and both are used verbatim. Documented here, not derived, because the
# halving convention is this task's own choice, not a value in the brief.
_HOP_TARGETS: dict[str, tuple[float, float]] = {
    _INGEST: (0.5, 1.0),
    _FLUSH: (0.5, 1.0),
    _DECISION: (5.0, 20.0),
    _ADMISSION: (1.0, 2.0),
    _FILL: (1.0, 2.0),
}
_END_TO_END_TARGET = (5.0, 10.0)


def _decode(raw: object) -> dict[str, str]:
    fields = cast("dict[bytes, bytes]", raw)
    return {
        key.decode(errors="replace"): value.decode(errors="replace")
        for key, value in fields.items()
    }


def _float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


async def _read_hash(redis: redis_asyncio.Redis, key: str) -> dict[str, str]:
    return _decode(await cast("object", redis).hgetall(key))  # type: ignore[attr-defined]


async def _market_hop_fields(redis: redis_asyncio.Redis) -> dict[str, str]:
    """The first ``hb:market:*`` hash carrying T3.79's fields (module docstring)."""
    client = cast("object", redis)
    async for raw_key in client.scan_iter(  # type: ignore[attr-defined]
        match=MARKET_HEARTBEAT_SCAN_PATTERN, count=SCAN_COUNT
    ):
        raw_key = cast("bytes | str", raw_key)
        key = raw_key.decode(errors="replace") if isinstance(raw_key, bytes) else raw_key
        fields = await _read_hash(redis, key)
        if "ingest_lag_p95_s" in fields:
            return fields
    return {}


def _hop(name: str, p50: float | None, p95: float | None) -> LatencyHopOut:
    warn_s, critical_s = _HOP_TARGETS[name] if name != _END_TO_END else _END_TO_END_TARGET
    status = LatencySloStatus(classify_slo(p95, warn_s=warn_s, critical_s=critical_s))
    return LatencyHopOut(
        hop=name, p50_s=p50, p95_s=p95, target_p50_s=warn_s, target_p95_s=critical_s, status=status
    )


def _sum_or_none(values: list[float | None]) -> float | None:
    """The sum of ``values``, or ``None`` the moment any one is missing --
    never a partial sum (module docstring: a dropped term would read as "the
    whole pipeline is fast", not "one leg is unmeasured")."""
    if any(value is None for value in values):
        return None
    return sum(cast("list[float]", values))


async def build_latency(redis: redis_asyncio.Redis) -> LatencyOut:
    market_fields = await _market_hop_fields(redis)
    shadow_fields = await _read_hash(redis, STRATEGY_SHADOW_KEY)
    execution_fields = await _read_hash(redis, EXECUTION_PAPER_KEY)

    hops = [
        _hop(
            _INGEST,
            _float(market_fields.get("ingest_lag_p50_s")),
            _float(market_fields.get("ingest_lag_p95_s")),
        ),
        _hop(
            _FLUSH,
            _float(market_fields.get("flush_lag_p50_s")),
            _float(market_fields.get("flush_lag_p95_s")),
        ),
        _hop(
            _DECISION,
            _float(shadow_fields.get("decision_lag_p50_s")),
            _float(shadow_fields.get("decision_lag_p95_s")),
        ),
        _hop(
            _ADMISSION,
            _float(execution_fields.get("admission_lag_p50_s")),
            _float(execution_fields.get("admission_lag_p95_s")),
        ),
        _hop(
            _FILL,
            _float(execution_fields.get("fill_lag_p50_s")),
            _float(execution_fields.get("fill_lag_p95_s")),
        ),
    ]
    end_to_end = _hop(
        _END_TO_END,
        _sum_or_none([hop.p50_s for hop in hops]),
        _sum_or_none([hop.p95_s for hop in hops]),
    )
    return LatencyOut(hops=hops, end_to_end=end_to_end, generated_at=utcnow())


__all__ = ["build_latency"]
