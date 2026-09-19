"""What the event-exit loops share (T4.63) — split out of ``event_exits.py``
for the 350-line budget: the narrowed WS protocol a ``FakeWs`` can satisfy,
one ``Watched`` per open position, and the runtime object every loop reads
from and writes to.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.event_exits_config import EventExitsConfig
from hunter_meme_executor.repo import OpenPosition

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from hunter_exchanges.pumpfun.rpc_ws_models import Notification
    from hunter_meme_executor.event_exits_stats import EventExitsStats

__all__ = ["ConnectionStateLike", "EventExitsRuntime", "SolanaWs", "Watched"]


class ConnectionStateLike(Protocol):
    ws_state: str
    reconnects: int


class SolanaWs(Protocol):
    """What ``rpc_ws.SolanaWsClient`` gives this module — narrowed so a
    ``FakeWs`` test double is a legitimate one (as in the radar's gate)."""

    @property
    def state(self) -> ConnectionStateLike: ...

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int: ...
    async def subscribe_account(self, pubkey: str, *, commitment: str) -> int: ...
    async def unsubscribe(self, logical_id: int) -> bool: ...
    async def aclose(self) -> None: ...

    def listen(self) -> AsyncIterator[Notification]: ...


@dataclass(slots=True)
class Watched:
    """One open position under subscription — the row as last synced, the
    creator (``meme_tokens.creator``), the running peak, the two logical ids."""

    position: OpenPosition
    creator: str | None
    tape_creator_sold: bool | None
    logs_id: int
    account_id: int
    high_water: Decimal
    creator_initial_tokens: Decimal | None = None
    """``meme_tokens.creator_initial_tokens`` (``0048``): the denominator of the
    fraction a creator sell stamps on the row; ``None`` ⇒ memory-only sighting."""
    creator_sold: bool = False
    last_mark_write_at: datetime | None = None
    last_trigger_at: datetime | None = None
    selling: asyncio.Task[None] | None = None
    launch: bool = False
    """T4.67b: opened by the launch profile (``params.lane = launch``)."""
    third_party_rule: bool = False
    """The set's ``exit_on_first_third_party_sell`` — only a launch position has it."""
    third_party_sell_seen: bool = False
    """A sell by a wallet that is neither the creator, nor this wallet, nor a
    creation-slot buyer, seen in a ``TradeEvent`` of this curve."""
    known_buyers: set[str] = field(default_factory=set[str])
    """Creation-slot buyers: from the proposal (``params.known_buyers``) plus any
    buy this runtime sees at ``slot <= creation_slot``. Their sells are not third-party."""
    creation_slot: int | None = None


@dataclass
class EventExitsRuntime:
    ctx: ExecutorContext
    ws: SolanaWs
    config: EventExitsConfig
    watched: dict[str, Watched] = field(default_factory=dict[str, Watched])
    by_logical: dict[int, str] = field(default_factory=dict[int, str])
    seen_reconnects: int = 0
    sell_tasks: set[asyncio.Task[None]] = field(default_factory=set[asyncio.Task[None]])
    """Strong references: ``asyncio`` keeps only weak ones, and a sell in
    flight must not be collected because its position was unwatched."""

    @property
    def stats(self) -> EventExitsStats:
        return self.ctx.event_exits
