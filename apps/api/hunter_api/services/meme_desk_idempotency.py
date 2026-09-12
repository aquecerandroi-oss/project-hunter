"""``Idempotency-Key`` for the desk's five POSTs (T4.7) — the same contract
``order-requests`` gives (``services/admission.py``): a replay of the same
key with the same intent returns what the first call produced; the same key
with a *different* intent is a 409, never a silent second write.

**Why Redis and not a column.** ``trade_proposals`` carries its own
``idempotency_key`` column; the contract's ``meme_proposals``/
``meme_operator_commands`` do not, and their migration (``0022_meme_lab``) is
T4.6's — so the key → outcome memory lives in the process-wide Redis
``hunter_api.deps.get_redis`` already hands every route, namespaced per
organization, for 24 h. What is remembered is only *which entity* the key
produced (plus a fingerprint of the intent), never the response body: a
replay re-reads the entity from Postgres, so a write that rolled back after
the key was remembered (the tenant transaction commits after the handler
returns) is simply not found and the call runs again instead of replaying a
success that never landed.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from fastapi import status

from hunter_api.errors import HunterError
from hunter_core.strategies.canonical import params_hash

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

__all__ = [
    "IDEMPOTENCY_TTL_S",
    "DeskReplayConflictError",
    "IdempotencyStore",
    "RedisIdempotencyStore",
    "ReplayRecord",
    "fingerprint",
    "find_replay",
    "key_hash",
    "remember",
    "replay_key",
]

IDEMPOTENCY_TTL_S = 24 * 3600


class IdempotencyStore(Protocol):
    """Two operations, typed narrowly so the unit suite can hand in a
    dict-backed fake without a Redis (``RedisIdempotencyStore`` is the real one)."""

    async def load(self, key: str) -> str | None: ...

    async def save(self, key: str, value: str, *, ttl_s: int) -> None: ...


class RedisIdempotencyStore:
    """The production store over ``redis.asyncio.Redis`` (bytes in, bytes out)."""

    def __init__(self, redis: redis_asyncio.Redis) -> None:
        self._redis = redis

    async def load(self, key: str) -> str | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    async def save(self, key: str, value: str, *, ttl_s: int) -> None:
        # ``nx``: the first writer of a key wins; a concurrent second call with
        # the same key cannot overwrite what the first already produced.
        await self._redis.set(key, value.encode(), ex=ttl_s, nx=True)


class DeskReplayConflictError(HunterError):
    """409 — the idempotency key already names a **different** intent."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="idempotency-key-conflict",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    fingerprint: str
    entity_type: str
    entity_id: str


def key_hash(idempotency_key: str) -> str:
    """What is stored and audited in place of the key itself — the same
    ``params_hash({"idempotency_key": ...})`` ``record_filing_audit`` uses."""
    return params_hash({"idempotency_key": idempotency_key})


def replay_key(org_id: uuid.UUID, idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()
    return f"idem:meme-desk:{org_id}:{digest}"


def fingerprint(action: str, target: str, body: Mapping[str, object]) -> str:
    """One hash of *what was asked*: the action, its target and the body
    (money already canonicalised by ``params_hash``'s decimal rule)."""
    return params_hash({"action": action, "target": target, "body": dict(body)})


async def find_replay(
    store: IdempotencyStore, org_id: uuid.UUID, idempotency_key: str, expected: str
) -> ReplayRecord | None:
    """The record this key produced earlier, or ``None``. A record whose
    fingerprint disagrees with ``expected`` is the 409 — checked here, once,
    so no use case can forget it."""
    payload = await store.load(replay_key(org_id, idempotency_key))
    if payload is None:
        return None
    try:
        decoded: object = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(decoded, dict):
        return None
    data = cast("dict[str, object]", decoded)
    record = ReplayRecord(
        fingerprint=str(data.get("fingerprint", "")),
        entity_type=str(data.get("entity_type", "")),
        entity_id=str(data.get("entity_id", "")),
    )
    if record.fingerprint != expected:
        raise DeskReplayConflictError(
            "idempotency key already names a different desk action "
            f"(reason: desk_replay_conflict; {record.entity_type} {record.entity_id})"
        )
    return record


async def remember(
    store: IdempotencyStore, org_id: uuid.UUID, idempotency_key: str, record: ReplayRecord
) -> None:
    value = json.dumps(
        {
            "fingerprint": record.fingerprint,
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
        }
    )
    await store.save(replay_key(org_id, idempotency_key), value, ttl_s=IDEMPOTENCY_TTL_S)
