"""Worker liveness and market-connectivity views built from Redis ``hb:*``
hashes and Postgres market/gap counts. The Redis field contract this module
reads is documented verbatim in ``schemas/system.py``'s module docstring;
keep the two in sync.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import TYPE_CHECKING, cast

import redis.exceptions as redis_exceptions

from hunter_api.repositories.markets import MarketRepository
from hunter_api.schemas.system import (
    MarketStatusExchangeOut,
    MarketStatusOut,
    WorkerHeartbeatOut,
    WorkerLivenessStatus,
)
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

ALIVE_AFTER_S = 15.0
"""ARCHITECTURE.md §11 / M1.md: a heartbeat this fresh or fresher is "alive"."""

LATE_AFTER_S = 30.0
"""Past ``ALIVE_AFTER_S`` but at or under this is "late"; older is "dead" —
though ``hb:*``'s own 30s TTL (``WorkerRuntime.HEARTBEAT_TTL_S``) means a row
this old has usually already expired out of Redis. "dead" mostly covers the
read racing that expiry, not a normal steady state.
"""

CLOCK_SKEW_TOLERANCE_S = 2.0
"""(F3) A ``ts`` more than this far ahead of ``now`` is a skewed producer
clock, not a live heartbeat -- reported ``dead`` regardless of how small the
naive ``now - ts`` looks. Mirrors ``services/markets.py``'s constant of the
same name and rationale; kept as a separate copy since the two modules are
independently owned and neither imports the other's internals.

(G6) Reduced from 5s to 2s, for the same reason ``services/markets_quality
.py`` reduced its copy: the API and every worker that writes a ``ts`` here
run on the same NTP-synced host, so genuine clock drift between them should
be near zero -- 2s is generous headroom for jitter, not for a producer that
has actually stopped. Also now applied to ``build_market_status``'s
``last_event_at`` handling, which previously only clamped the age and never
checked it against this tolerance at all."""

HEARTBEAT_SCAN_PATTERN = "hb:*"

HEARTBEAT_SCAN_COUNT = 500
"""(F7) redis-py's default ``SCAN COUNT`` is 10, so round trips would scale
with the *whole* keyspace (hot-state keys for every market, plus a
rate-limit key per client per minute) rather than the handful of ``hb:*``
keys this actually returns -- and this endpoint is polled by every open
browser tab."""


def classify_liveness(age_s: float) -> WorkerLivenessStatus:
    """(F3) A negative ``age_s`` beyond ``CLOCK_SKEW_TOLERANCE_S`` (``ts``
    more than the tolerance ahead of ``now``) means a skewed clock, not a
    live worker -- reported ``dead`` even though a naive ``age_s <=
    ALIVE_AFTER_S`` check would otherwise pass (a very negative number is
    always <= a positive threshold).
    """
    if age_s < -CLOCK_SKEW_TOLERANCE_S:
        return WorkerLivenessStatus.DEAD
    if age_s <= ALIVE_AFTER_S:
        return WorkerLivenessStatus.ALIVE
    if age_s <= LATE_AFTER_S:
        return WorkerLivenessStatus.LATE
    return WorkerLivenessStatus.DEAD


_PLAIN_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
"""(G2) What a legitimate, non-sensitive ``instance`` looks like: an exchange
code such as ``binance`` or ``bybit-testnet`` -- lowercase, no ``:``, no
whitespace. Anything else is treated as potentially ``hostname:pid`` (or
worse) and hashed, regardless of which role wrote it."""


def anonymize_instance(role: str, instance: str) -> str:
    """(G2) The exception is keyed on the *shape* of ``instance``, never on
    ``role`` -- the original fix ("pass it through when ``role ==
    'market'``") assumed a market instance is always an exchange code, but
    the worker entrypoint constructs ``WorkerRuntime(role="market")``
    *without* an explicit ``instance``, so ``WorkerRuntime`` still falls
    back to its generic ``f"{hostname}:{pid}"`` default and writes it under
    ``hb:market:{hostname}:{pid}`` -- a real key this endpoint would
    otherwise pass straight through and leak.

    Rule: an ``instance`` containing ``:`` (``WorkerRuntime``'s default
    shape), or that is not a plain lowercase slug at all, is hashed into a
    stable, non-reversible 12-hex digest -- whatever wrote it, and whatever
    ``role`` it was written under. A plain slug like ``binance`` (no ``:``,
    matching :data:`_PLAIN_SLUG_RE`) is meaningful, non-sensitive data and
    passes through verbatim. Two reads of the same non-slug instance still
    correlate (the digest is deterministic per ``role``+``instance``), but
    the hostname and PID never leave the box.
    """
    if ":" not in instance and _PLAIN_SLUG_RE.match(instance):
        return instance
    return hashlib.sha256(f"{role}:{instance}".encode()).hexdigest()[:12]


def _decode(raw: dict[bytes, bytes]) -> dict[str, str]:
    """(G7) ``errors="replace"``: a hash field that is not valid UTF-8 must
    decode to *something* rather than raise ``UnicodeDecodeError`` past this
    boundary -- the replaced string then simply fails whatever parser reads
    it next (``parse_heartbeat_datetime``/``parse_heartbeat_int`` return
    ``None`` for garbage), same as any other corrupted value.
    """
    return {
        key.decode(errors="replace"): value.decode(errors="replace") for key, value in raw.items()
    }


async def _hgetall(redis: redis_asyncio.Redis, key: bytes | str) -> dict[str, str]:
    """``HGETALL``, decoded — the one place this module crosses into redis-py's
    loosely-typed surface (its response type varies with ``decode_responses``,
    which pyright cannot see is fixed to ``False`` for this client).
    """
    raw = cast("dict[bytes, bytes]", await redis.hgetall(key))
    return _decode(raw)


def parse_heartbeat_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def parse_heartbeat_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_heartbeat_key(key: bytes) -> tuple[str, str]:
    """``hb:{role}:{instance}`` -> ``(role, instance)``. Split once, so an
    ``instance`` that itself contains ``:`` (``WorkerRuntime``'s default is
    ``hostname:pid``) stays intact.
    """
    remainder = key.decode()[len("hb:") :]
    role, _, instance = remainder.partition(":")
    return role, instance


def heartbeat_from_hash(
    role: str, instance: str, fields: dict[str, str], *, now: datetime
) -> WorkerHeartbeatOut | None:
    """``None`` when the hash has no ``ts`` — a key that raced past its TTL
    between ``SCAN`` and ``HGETALL``, or one line here would ever divide by a
    missing timestamp.
    """
    ts = parse_heartbeat_datetime(fields.get("ts"))
    if ts is None:
        return None
    age_s = (now - ts).total_seconds()
    status = classify_liveness(age_s)
    # (F3) the *status* above reflects clock skew (a far-future `ts` reads
    # `dead`); the reported `age_s` is still clamped at 0 so a mildly-skewed
    # but tolerated `ts` never surfaces a negative number to a client.
    reported_age_s = max(age_s, 0.0)
    return WorkerHeartbeatOut(
        role=role,
        instance=anonymize_instance(role, instance),
        ts=ts,
        last_success=parse_heartbeat_datetime(fields.get("last_success")),
        errors=parse_heartbeat_int(fields.get("errors")) or 0,
        version=fields.get("version") or None,
        age_s=reported_age_s,
        status=status,
        last_event_at=parse_heartbeat_datetime(fields.get("last_event_at")),
        ws_state=fields.get("ws_state") or None,
        subscriptions=parse_heartbeat_int(fields.get("subscriptions")),
        reconnects=parse_heartbeat_int(fields.get("reconnects")),
        markets_monitored=parse_heartbeat_int(fields.get("markets_monitored")),
        open_gaps=parse_heartbeat_int(fields.get("open_gaps")),
    )


async def scan_heartbeats(redis: redis_asyncio.Redis) -> list[WorkerHeartbeatOut]:
    """Every ``hb:*`` hash, via ``SCAN`` (never ``KEYS`` — ARCHITECTURE.md
    §11 runs this against the shared production Redis, where ``KEYS`` blocks
    every other client for the duration of the scan).

    (G4) Redis being unavailable -- the whole scan raising, or one key's
    ``HGETALL`` raising ``WRONGTYPE`` mid-scan -- is **not** the same fact as
    "no worker has ever reported in", and must not be reported as an
    identical ``200 []``: that reads to an operator as a healthy, empty
    cluster during an actual outage. This function re-raises
    ``redis.exceptions.RedisError`` after logging only its ``error_type``
    (never ``str(exc)`` -- a WRONGTYPE error from redis-py embeds the
    offending key) so the router can turn it into an explicit ``503``. An
    empty list here means exactly what it says: Redis was read successfully
    and no ``hb:*`` key exists.
    """
    out: list[WorkerHeartbeatOut] = []
    try:
        async for raw_key in redis.scan_iter(  # type: ignore[reportUnknownMemberType]
            match=HEARTBEAT_SCAN_PATTERN, count=HEARTBEAT_SCAN_COUNT
        ):
            key = cast(bytes, raw_key)
            role, instance = parse_heartbeat_key(key)
            fields = await _hgetall(redis, key)
            # (F3) captured per key, after its own HGETALL -- not once before
            # the loop -- so a heartbeat's age reflects when it was actually
            # read, not the read latency of every key scanned before it.
            now = utcnow()
            heartbeat = heartbeat_from_hash(role, instance, fields, now=now)
            if heartbeat is not None:
                out.append(heartbeat)
    except redis_exceptions.RedisError as exc:
        logger.warning("heartbeat_scan_redis_error", error_type=type(exc).__name__)
        raise
    out.sort(key=lambda item: (item.role, item.instance))
    return out


async def build_market_status(session: AsyncSession, redis: redis_asyncio.Redis) -> MarketStatusOut:
    """One row per (global, no-RLS) ``exchanges`` entry — not per ``hb:market:*``
    key found — so an exchange the worker has never touched still appears,
    reported ``ws_state: "unavailable"``, rather than silently missing.

    (G4) One exchange's own heartbeat hash misbehaving (a lone ``WRONGTYPE``)
    still degrades only that row -- the same per-item isolation
    ``services/markets.py`` applies. But if *every* exchange's read failed,
    that is not "no worker has reported for any exchange yet", it is Redis
    itself being unreachable -- reported wholesale by re-raising
    ``redis.exceptions.RedisError`` (after logging only its ``error_type``
    per exchange, never a key name) so the router can answer an explicit
    ``503`` instead of a ``200`` indistinguishable from a healthy, idle
    cluster.
    """
    repository = MarketRepository(session)
    exchange_codes = await repository.list_exchange_codes()
    monitored_counts = await repository.monitored_market_counts()
    gap_counts = await repository.open_gap_counts()

    raw_fields: list[tuple[str, dict[str, str]]] = []
    failed_reads = 0
    for code in exchange_codes:
        try:
            fields = await _hgetall(redis, keys.heartbeat("market", code))
        except redis_exceptions.RedisError as exc:
            logger.warning(
                "market_status_redis_error", error_type=type(exc).__name__, exchange=code
            )
            failed_reads += 1
            fields = {}
        raw_fields.append((code, fields))
    # (G5) captured after every Redis read above, not before the loop --
    # `now` must reflect when the reads actually completed.
    now = utcnow()
    if exchange_codes and failed_reads == len(exchange_codes):
        raise redis_exceptions.RedisError("every exchange heartbeat read failed")

    exchanges: list[MarketStatusExchangeOut] = []
    for code, fields in raw_fields:
        last_event_at = parse_heartbeat_datetime(fields.get("last_event_at"))
        ws_state = fields.get("ws_state") or "unavailable"
        age_ms: int | None = None
        if last_event_at is not None:
            age_s = (now - last_event_at).total_seconds()
            # (G6) apply the same clock-skew tolerance the component/
            # heartbeat freshness checks already apply: a `last_event_at`
            # further ahead of `now` than `CLOCK_SKEW_TOLERANCE_S` is not
            # evidence of a live feed, however fresh the naive `now - ts`
            # looks -- previously this branch only clamped the age at 0 and
            # left `ws_state` free to still read "connected" off an
            # impossible timestamp. An out-of-tolerance timestamp is treated
            # the same as no timestamp at all: `last_event_at`/`age_ms` come
            # back absent and `ws_state` is forced to "unavailable" rather
            # than trusting a signal that cannot be real.
            if age_s < -CLOCK_SKEW_TOLERANCE_S:
                last_event_at = None
                ws_state = "unavailable"
            else:
                age_ms = max(int(age_s * 1000), 0)
        exchanges.append(
            MarketStatusExchangeOut(
                exchange=code,
                ws_state=ws_state,
                last_event_at=last_event_at,
                last_event_age_ms=age_ms,
                markets_monitored=monitored_counts.get(code, 0),
                open_gaps=gap_counts.get(code, 0),
                reconnects=parse_heartbeat_int(fields.get("reconnects")),
            )
        )
    return MarketStatusOut(
        exchanges=exchanges,
        markets_monitored_total=sum(monitored_counts.values()),
        updated_at=now,
    )
