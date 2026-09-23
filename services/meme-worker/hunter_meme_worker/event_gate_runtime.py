"""What the event gate's loops share (T4.52b-3) — split out of ``event_gate.py``
for the 350-line budget: the per-mint debounce (plan-T4.52b.md §4/§5) and the
one object every loop reads from and writes to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from hunter_meme_worker.decision_tape_writer import DecisionTapeWriter
from hunter_meme_worker.event_book import EventBook
from hunter_meme_worker.event_gate_rows import EventReserves
from hunter_meme_worker.event_gate_stats import EventGateStats

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from hunter_exchanges.pumpfun.rpc_ws_models import Notification
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.decision_tape import DecisionTape
    from hunter_meme_worker.event_gate_config import EventGateConfig
    from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
    from hunter_meme_worker.lab import LabContext

__all__ = ["ConnectionStateLike", "Debouncer", "EventGateRuntime", "SolanaWs", "Subscription"]


class ConnectionStateLike(Protocol):
    """The two fields this package reads off ``SolanaWsClient.state``
    (``rpc_ws_models.ConnectionState``) — narrowed so a ``FakeWs`` test double
    needs no other field of the real one."""

    ws_state: str
    reconnects: int


class SolanaWs(Protocol):
    """What :mod:`hunter_exchanges.pumpfun.rpc_ws`'s ``SolanaWsClient`` gives
    this package — narrowed so a ``FakeWs`` test double is a legitimate one.
    ``state`` is a property here (never assigned through this protocol) so a
    plain mutable attribute on the real client still satisfies it — a
    Protocol's own mutable-attribute invariance would otherwise reject
    ``ConnectionState`` for not matching :class:`ConnectionStateLike` exactly."""

    @property
    def state(self) -> ConnectionStateLike: ...

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int: ...
    async def subscribe_account(self, pubkey: str, *, commitment: str) -> int: ...
    async def subscribe_slot(self) -> int: ...
    async def unsubscribe(self, logical_id: int) -> bool: ...
    async def aclose(self) -> None: ...

    def listen(self) -> AsyncIterator[Notification]: ...


@dataclass(slots=True)
class Subscription:
    logs_id: int
    account_id: int
    first_seen_at: datetime


class Debouncer:
    """Per-mint minimum interval between evaluations (plan §4/§5). Pure and
    synchronous, driven by a monotonic clock the caller supplies."""

    def __init__(self, *, interval_s: float) -> None:
        self._interval = interval_s
        self._last: dict[str, float] = {}
        self._dirty: set[str] = set()

    def poll(self, mint: str, now_s: float) -> bool:
        """``True``: evaluate ``mint`` right now. ``False``: too soon since
        its last evaluation — marked dirty for :meth:`drain_ready`."""
        last = self._last.get(mint)
        if last is None or now_s - last >= self._interval:
            self._last[mint] = now_s
            self._dirty.discard(mint)
            return True
        self._dirty.add(mint)
        return False

    def drain_ready(self, now_s: float) -> list[str]:
        ready = [m for m in self._dirty if now_s - self._last.get(m, 0.0) >= self._interval]
        for mint in ready:
            self._dirty.discard(mint)
            self._last[mint] = now_s
        return ready

    def forget(self, mint: str) -> None:
        """F1: called on unsubscribe — a mint no longer tracked keeps no seat
        in ``_last``/``_dirty`` forever."""
        self._last.pop(mint, None)
        self._dirty.discard(mint)

    def prune(self, *, keep: frozenset[str], now_s: float, max_age_s: float) -> None:
        """F1: called every sync — a mint outside ``keep`` (``young_mints``)
        or whose last poll is older than ``max_age_s`` is forgotten too, not
        only the ones ``forget`` catches via an explicit unsubscribe."""
        stale = [m for m, last in self._last.items() if m not in keep or now_s - last > max_age_s]
        for mint in stale:
            self.forget(mint)

    @property
    def size(self) -> int:
        return len(self._last)


@dataclass
class EventGateRuntime:
    """Everything the loops share — one object so a test builds one and reads
    ``stats``/``book`` back afterward."""

    radar: RadarContext
    lab: LabContext
    ws: SolanaWs
    config: EventGateConfig
    heartbeat: Callable[[dict[str, str]], Awaitable[None]] | None = None
    book: EventBook = field(init=False)
    debouncer: Debouncer = field(init=False)
    stats: EventGateStats = field(default_factory=EventGateStats)
    subs: dict[str, Subscription] = field(default_factory=dict[str, Subscription])
    subs_by_logical: dict[int, str] = field(default_factory=dict[int, str])
    reserves: dict[str, EventReserves] = field(default_factory=dict[str, EventReserves])
    slot: int | None = None
    seen_reconnects: int = 0
    pending_trail: dict[str, list[RefusalTrailRow]] = field(
        default_factory=dict[str, list["RefusalTrailRow"]]
    )
    """F6/F7's own batching: a mint's latest refusal-trail candidates, queued
    here instead of written per evaluation — flushed in the same session as
    an insert for that mint, or by the periodic trail-flush loop."""
    trail_last_written: dict[str, datetime] = field(default_factory=dict[str, "datetime"])
    """The last time this mint's trail was actually written — the 60-second
    per-mint cooldown F7 wants."""
    pending_tapes: dict[str, DecisionTape] = field(default_factory=dict[str, "DecisionTape"])
    """T4.89: the capture taken with ``pending_trail[mint]``'s candidates,
    replaced and popped together (``event_gate_trail.py``)."""
    proposing: set[str] = field(default_factory=set[str])
    """T4.89 (review): mints whose proposal transaction is open right now —
    ``flush_pending_trail`` skips them (``event_gate_trail.py``)."""
    tapes: DecisionTapeWriter = field(default_factory=DecisionTapeWriter)
    """T4.89: the bounded buffer of decision tapes and its counters — on the
    runtime, so a gate restart keeps what was not flushed yet."""

    def __post_init__(self) -> None:
        self.book = EventBook(max_mints=self.config.max_mints)
        self.debouncer = Debouncer(interval_s=self.config.debounce_ms / 1000)
