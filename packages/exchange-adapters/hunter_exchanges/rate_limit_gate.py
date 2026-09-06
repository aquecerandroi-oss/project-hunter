"""The IP-wide backoff gate, coordinated in Redis (T2.9).

Binance's ``429``/``418`` are per-**IP**, not per-bucket and not per-process: a
``Retry-After`` on one bucket means every other bucket *and every other process
sharing that egress IP* must back off too, or the next request escalates the
429 into an 418 ban. Until T2.9 the deadline was a process-local monotonic
float, which was correct for one process per IP and silently wrong the moment
the market-worker ran sharded — shard A took the 429, shard B never heard about
it and kept calling.

``blocked_until`` now lives at ``rl:{exchange}:ip:blocked_until``, written by an
extend-only Lua script that reads **Redis's own clock** (``TIME``). An absolute
deadline compared by several processes cannot use each process's wall clock: a
shard running a second fast would lift a ban another shard is still serving.

Two properties survive Redis being unreachable:

- a block this process *knows about* is never forgotten — it is mirrored to a
  local monotonic deadline, so a 429 still stops this process even if the
  coordinating write failed (the alternative is an immediate retry into an IP
  ban);
- the gate says so (:attr:`degraded`, plus a log). Note that this half of the
  gate is fail-closed by construction: it can only ever *add* a block, never
  admit anything. Admission is the limiter's side, and since T2.9 it suspends
  entirely while coordination is down (``rate_limit_suspension.py``), so a
  degraded gate can no longer be paired with several shards each spending a
  full local budget against one shared quota.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from hunter_core.logging import get_logger
from hunter_exchanges.rate_limit_lua import BLOCK_IP_SCRIPT, IP_WAIT_SCRIPT

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

_REPUBLISH_THRESHOLD_S = 1.0
"""How much longer the local mirror must be than the shared deadline before it
is written back. A margin, not zero: the shared value is always a little stale
by the time it crosses the network, and a zero threshold would rewrite the key
on every single read."""

_TTL_SLACK_S = 60
"""Kept on the key past its own deadline, so a clock nudge cannot expire a
still-active block a moment early."""


class _RedisEvalClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> Any: ...


def gate_key(exchange: str) -> str:
    """``rl:{exchange}:ip:blocked_until`` — one deadline per exchange per IP."""
    return f"rl:{exchange}:ip:blocked_until"


class IpRateGate:
    """ "This IP is blocked until ..." — shared through Redis, mirrored locally.

    ``clock`` is monotonic and only ever measures the *local* mirror; the
    shared deadline is compared against Redis's clock inside the Lua, never
    against this one.
    """

    __slots__ = ("_blocked_until", "_clock", "_exchange", "_redis", "degraded")

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._blocked_until = 0.0
        self._redis: _RedisEvalClient | None = None
        self._exchange: str | None = None
        self.degraded = False
        """True while Redis is not answering: this gate is protecting only its
        own process, and the shared quota is unguarded."""

    @property
    def bound_to(self) -> tuple[str, int] | None:
        """``(exchange, id(redis))`` once bound, else ``None`` (introspection)."""
        if self._exchange is None or self._redis is None:
            return None
        return self._exchange, id(self._redis)

    def bind(self, redis: _RedisEvalClient, exchange: str) -> None:
        """Attach the shared client. Idempotent, no IO.

        Called by :attr:`TokenBucketRateLimiter.ip_gate`'s setter, which is how
        a gate built by a caller that knows nothing about Redis
        (``BinanceRestClient``) still ends up coordinated. Rebinding to another
        exchange is refused rather than silently moving the key — that would
        un-block an IP that is still banned.
        """
        if self._exchange is not None and self._exchange != exchange:
            raise ValueError(
                f"IpRateGate is already bound to {self._exchange!r}, refusing to rebind "
                f"to {exchange!r}: the two use different keys and would not see each other"
            )
        self._redis = redis
        self._exchange = exchange

    def _mirror(self, seconds: float) -> None:
        """Remember a deadline locally. Extend-only, like the shared one."""
        if seconds > 0:
            self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    def _local_wait_s(self) -> float:
        return max(0.0, self._blocked_until - self._clock())

    def _fell_back(self, action: str, exc: Exception) -> None:
        if not self.degraded:
            logger.warning(
                "rate_limit_gate_degraded",
                exchange=self._exchange,
                action=action,
                error=str(exc),
            )
        self.degraded = True

    async def block_for(self, seconds: float) -> None:
        """Block this IP for at least ``seconds`` from now (never shortens it).

        The local mirror is written **first**: the shared write is the part
        that can fail, and a 429 must stop this process whether or not the
        other shards can be told about it.
        """
        if seconds <= 0:
            return
        self._mirror(seconds)
        if self._redis is None or self._exchange is None:
            return
        try:
            remaining = await self._redis.eval(
                BLOCK_IP_SCRIPT, 1, gate_key(self._exchange), seconds, _TTL_SLACK_S
            )
        except Exception as exc:
            self._fell_back("block", exc)
            return
        self.degraded = False
        self._mirror(float(remaining))  # another shard's longer block, adopted

    async def wait_s(self) -> float:
        """Seconds remaining until the IP-wide block lifts (0 if not blocked).

        Returns the longer of the shared deadline and this process's mirror, so
        neither a Redis outage nor a key that was evicted can shorten a block
        this process already knows about — and, when the mirror is the longer
        of the two, **puts it back** so the other processes learn about it.
        Without that re-publication, a block taken while Redis was down stayed
        private to this process forever: Redis comes back with no key, the
        other shards read zero and keep calling into a live ban (Astra, T2.9
        round 2).
        """
        local = self._local_wait_s()
        if self._redis is None or self._exchange is None:
            return local
        try:
            shared = float(await self._redis.eval(IP_WAIT_SCRIPT, 1, gate_key(self._exchange)))
        except Exception as exc:
            self._fell_back("wait", exc)
            return local
        self.degraded = False
        if local - shared > _REPUBLISH_THRESHOLD_S:
            await self.block_for(local)
            return local
        self._mirror(shared)
        return max(local, shared)
