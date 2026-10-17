"""The IO seams of the NATS leader source (H-037): the production fetch of the credential from the public
home page, the production WebSocket connect, and the types the source is injected with. Split from
:mod:`leader_source_nats` for the file-size budget; importing it opens nothing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol, cast

import httpx

from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.leader_source_nats_wire import (
    HOME_URL,
    NatsConfig,
    NatsRefused,
    home_nats_config,
)

REFUSAL_STATUS = frozenset({401, 403, 418, 429})
OPEN_TIMEOUT_S = 15.0
RETRY_AFTER_MAX_S = 86_400.0
"""A day: what the page asks for is honoured up to here (a hostile ``Retry-After`` cannot park us forever)."""
RECV_QUEUE = 64
"""Frames the WebSocket library may hold unread: finite, so a flood is backpressure on the socket, not
unbounded memory (a ``None`` here removed it)."""
MAX_FRAME = 2 * 1024 * 1024


def is_refusal(status: object) -> bool:
    """401/403/418/429, and any 5xx: the first block stops the fast path (decision 06/10, REA)."""
    return isinstance(status, int) and (status in REFUSAL_STATUS or status >= 500)


def _retry_after(raw: str | None, now: datetime) -> float | None:
    """``Retry-After`` as seconds (a number, or an HTTP-date counted from ``now``), capped at a day;
    a past date or anything unreadable is ignored."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            return None
        value = (when - now).total_seconds()
    if not 0 < value < float("inf"):
        return None
    return min(value, RETRY_AFTER_MAX_S)


__all__ = [
    "OPEN_TIMEOUT_S",
    "REFUSAL_STATUS",
    "RETRY_AFTER_MAX_S",
    "ConnectFn",
    "FetchConfig",
    "Seeder",
    "WalletSnapshot",
    "WsLike",
    "default_connect",
    "default_fetch_config",
    "is_refusal",
    "to_bytes",
]


@dataclass(frozen=True, slots=True)
class WalletSnapshot:
    """A complete balance snapshot of a wallet — the seed of the delta baseline. Every read has its OWN
    slot (the answers of the node come at different slots): ``sol_slot`` for the lamports, and for each
    held mint ``(atoms, slot)`` of the token-program read that listed it; ``tokens_slot`` is the newest
    of the token reads — a mint absent from every list is zero only for legs after it."""

    sol_lamports: int
    sol_slot: int
    tokens: dict[str, tuple[int, int]] = field(default_factory=dict[str, tuple[int, int]])
    tokens_slot: int = 0


class WsLike(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...


ConnectFn = Callable[[str], AbstractAsyncContextManager[WsLike]]
FetchConfig = Callable[[], Awaitable[NatsConfig]]
Seeder = Callable[[str], Awaitable[WalletSnapshot]]


async def default_fetch_config(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    now: Callable[[], datetime] = utcnow,
) -> NatsConfig:
    """The anonymous home page is where the site's own client gets its NATS credential. A block or a
    server error (``is_refusal``) is a :class:`NatsRefused` carrying ``Retry-After``; the caller backs
    off on the slow ladder — the page is never hammered."""
    async with httpx.AsyncClient(
        timeout=15.0, follow_redirects=True, transport=transport
    ) as client:
        response = await client.get(HOME_URL)
    if is_refusal(response.status_code):
        raise NatsRefused(
            response.status_code, _retry_after(response.headers.get("Retry-After"), now())
        )
    if response.is_error:
        raise ConnectionError(f"home page HTTP {response.status_code}")
    return home_nats_config(response.text)


def default_connect(url: str) -> AbstractAsyncContextManager[WsLike]:
    import websockets

    return cast(
        "AbstractAsyncContextManager[WsLike]",
        websockets.connect(
            url,
            open_timeout=OPEN_TIMEOUT_S,
            max_size=MAX_FRAME,
            ping_interval=20,
            ping_timeout=30,
            max_queue=RECV_QUEUE,
        ),
    )


def to_bytes(raw: str | bytes) -> bytes:
    return raw if isinstance(raw, bytes) else raw.encode()
