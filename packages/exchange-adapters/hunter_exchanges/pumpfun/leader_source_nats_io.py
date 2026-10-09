"""The IO seams of the NATS leader source (H-037): the production fetch of the credential from the public
home page, the production WebSocket connect, and the types the source is injected with. Split from
:mod:`leader_source_nats` for the file-size budget; importing it opens nothing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol, cast

from hunter_exchanges.pumpfun.leader_source_nats_wire import (
    HOME_URL,
    NatsConfig,
    NatsRefused,
    home_nats_config,
)

REFUSAL_STATUS = frozenset({401, 403, 418, 429})
OPEN_TIMEOUT_S = 15.0

__all__ = [
    "OPEN_TIMEOUT_S",
    "REFUSAL_STATUS",
    "ConnectFn",
    "FetchConfig",
    "Seeder",
    "WalletSnapshot",
    "WsLike",
    "default_connect",
    "default_fetch_config",
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


async def default_fetch_config() -> NatsConfig:
    """The anonymous home page is where the site's own client gets its NATS credential."""
    import httpx

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(HOME_URL)
    if response.status_code in REFUSAL_STATUS:
        raise NatsRefused(response.status_code)
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
            max_size=8_000_000,
            ping_interval=20,
            ping_timeout=30,
            max_queue=None,
        ),
    )


def to_bytes(raw: str | bytes) -> bytes:
    return raw if isinstance(raw, bytes) else raw.encode()
