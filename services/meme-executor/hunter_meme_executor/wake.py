"""T4.52a: waking the entries loop the instant a proposal lands.

R55 measured Proposal->Received at 4.8s median / 7.5s p95 — 76% of the
end-to-end decision latency — because ``entries_once`` only ever ran on its
own timer (``config.loop_s``, ``main.py``). ``ProposalWakeListener`` subscribes
to :func:`hunter_core.redis.keys.meme_proposals_wake` (published by the
radar right after its own insert commits, ``hunter_meme_worker.main._wake_publisher``)
and sets an ``asyncio.Event`` on every message; ``main.py`` hands that same
event to ``forever(..., wake_event=...)`` so the entries loop wakes early and
the timer becomes a fallback, never the only path.

Not Postgres ``LISTEN``/``NOTIFY``: banned project-wide
(``docs/SPEC_REVIEW.md`` R7) because every connection in this stack goes
through a transaction-mode pooler, which a session-scoped ``LISTEN`` cannot
survive. Redis pub/sub costs nothing durable to lose (ARCHITECTURE.md §5.3) —
a dropped connection here only delays the next pick to the fallback tick, it
never drops a proposal (the entries loop's own ``SELECT`` is still the only
source of truth).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, Protocol

from redis.backoff import ExponentialWithJitterBackoff

from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = ["ProposalWakeListener"]

logger = get_logger(__name__)

_BACKOFF_BASE_S = 0.25
_BACKOFF_CAP_S = 5.0


class _PubSubLike(Protocol):
    async def subscribe(self, *channels: str) -> object: ...
    def listen(self) -> AsyncIterator[dict[str, Any]]: ...
    async def aclose(self) -> None: ...


class _RedisLike(Protocol):
    def pubsub(self) -> _PubSubLike: ...


class ProposalWakeListener:
    """One background task (``run``): subscribe, set ``event`` on every real
    message, reconnect with jittered backoff on any error. Never raises —
    the caller's ``TaskGroup`` supervises every other loop, but this one must
    not take the process down just because Redis blipped; the fallback timer
    on ``event``'s other reader keeps ``entries_once`` running regardless.
    """

    def __init__(self, redis_client: _RedisLike, event: asyncio.Event) -> None:
        self._redis = redis_client
        self.event = event
        self._backoff = ExponentialWithJitterBackoff(base=_BACKOFF_BASE_S, cap=_BACKOFF_CAP_S)

    async def run(self) -> None:
        failures = 0
        while True:
            try:
                await self._listen_once()
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("meme_proposal_wake_listener_failed", failures=failures)
                await asyncio.sleep(self._backoff.compute(failures))
                failures += 1

    async def _listen_once(self) -> None:
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(keys.meme_proposals_wake())
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    self.event.set()
        finally:
            with contextlib.suppress(Exception):
                await pubsub.aclose()
