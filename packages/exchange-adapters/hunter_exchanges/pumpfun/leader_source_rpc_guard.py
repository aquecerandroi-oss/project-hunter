"""One cool-down for every RPC call of the leader source (H-037).

A ``429`` (``RateLimited``) or a ``401``/``403``/``418`` (the RPC client turns them into
``ExchangeUnavailable("... HTTP 403")``) is the node saying no. It is a ``system_event`` and a **pause for
all callers** — the transaction fetch, the signature listing of the recovery and the balance seed alike —
checked right before each call, so a request that was already queued behind another cannot slip through
the pause. While paused no call leaves; callers get :class:`RpcRefused` with the reason and decide what
that means for them (a confirmation says ``rpc_error``, a seed retries after its backoff).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited

logger = get_logger(__name__)

REFUSAL_STATUS = frozenset({401, 403, 418})
COOLDOWN_S = 30.0
_HTTP_STATUS = re.compile(r"HTTP (\d{3})")

__all__ = ["RpcCall", "RpcGuard", "RpcRefused"]


class RpcCall(Protocol):
    async def call(self, method: str, params: list[Any]) -> Any: ...


class RpcRefused(Exception):
    """The node refused (or we are still inside the pause after it did). ``reason`` is
    ``rate_limited`` or ``refused_<status>``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RpcGuard:
    def __init__(
        self,
        rpc: RpcCall,
        *,
        wall: Callable[[], datetime] = utcnow,
        cooldown_s: float = COOLDOWN_S,
    ) -> None:
        self._rpc, self._wall, self._cooldown_s = rpc, wall, cooldown_s
        self._until: datetime | None = None
        self._reason = "rate_limited"

    async def call(self, method: str, params: list[Any]) -> Any:
        if self._until is not None and self._wall() < self._until:
            raise RpcRefused(self._reason)
        try:
            return await self._rpc.call(method, params)
        except RateLimited as exc:
            self._trip("rate_limited", max(exc.retry_after_s, 1.0))
            raise RpcRefused("rate_limited") from None
        except Exception as exc:
            found = _HTTP_STATUS.search(str(exc))
            if found is not None and int(found[1]) in REFUSAL_STATUS:
                self._trip(f"refused_{found[1]}", self._cooldown_s)
                raise RpcRefused(self._reason) from None
            raise

    def _trip(self, reason: str, seconds: float) -> None:
        self._reason = reason
        self._until = self._wall() + timedelta(seconds=seconds)
        logger.warning("system_event", kind="leader_rpc_refused", reason=reason, cool_s=seconds)
