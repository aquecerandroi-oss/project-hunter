"""Fatal task exits and monotonic ingestion health/watchdogs."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from hunter_exchanges.rate_limit import REST_GATE_OK, REST_GATE_SUSPENDED


def connection_field(state: Any, name: str) -> Any:
    if isinstance(state, dict):
        return cast(dict[str, Any], state).get(name)
    return getattr(state, name, None)


def counter_delta(previous: int, current: int) -> int:
    """How much a monotonic per-connection counter advanced since ``previous``.

    A counter that went *down* was not decremented: the adapter replaced the
    whole :class:`~hunter_exchanges.base.ConnectionState` on reconnect
    (``binance/ws.py`` ``_start_group``), so everything it reports now happened
    since the reset. ``max(0, current - previous)`` — what this replaces —
    silently swallowed exactly those losses (Astra, T2.5g design review).
    """
    return current - previous if current >= previous else current


class DroppedEventsLedger:
    """Monotonic total of events the adapter's bounded queue discarded.

    T2.5g: ``streaming.py`` used to read ``dropped_events`` off the *adapter*
    itself, which never had that attribute — so the coverage tracker was told
    "nothing was lost" on every stamp and its "a drop breaks the interval" rule
    never fired in production (1.2M drops on the VPS, 8.3M on the local stack,
    zero breaks). The counter lives on each :class:`ConnectionState`, and each
    of those is recreated by a reconnect, hence :func:`counter_delta`.
    """

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}
        self.total = 0

    def observe(self, adapter: Any) -> int:
        states = getattr(adapter, "connection_states", None)
        if states is None:
            return self.total
        for name, connection in states().items():
            current = int(connection_field(connection, "dropped_events") or 0)
            self.total += counter_delta(self._seen.get(name, 0), current)
            self._seen[name] = current
        return self.total


def rest_gate_status(adapter: Any) -> str:
    """``"ok"``/``"suspended"``: is this adapter admitting REST calls? (T2.9)

    ``suspended`` means the shared rate-limit coordination (Redis) is
    unreachable, so the adapter refuses REST admissions rather than letting N
    shards each spend a full local budget against one shared Binance quota.
    It is a **degradation, not a failure**: the WebSocket keeps ingesting, so
    this is *reported* (heartbeat hash, ``rt:system``, and the ``rest_gate``
    status detail on ``/ready``) and never turns the readiness verdict red by
    itself. A total Redis outage still fails ``/ready`` through the ``redis``
    check — this field says *which* degradation is in progress, not that
    everything is fine.

    Read through ``getattr`` like ``connection_states()``: an adapter (or the
    suite's ``FakeAdapter``) that predates the method is simply admitting.
    """
    status = getattr(adapter, "rest_gate_status", None)
    return REST_GATE_OK if status is None else str(status())


def rest_gate_suspended(adapter: Any) -> bool:
    """T2.9: are this adapter's REST admissions suspended (Redis unreachable)?

    A backfill attempted anyway would fail on the way out, still increment
    ``ingestion_gaps.attempts`` and, after ``MAX_ATTEMPTS``, park the gap as
    ``failed`` for an hour — an infrastructure outage turned into lost market
    data. Waiting costs nothing: the gap stays open, the WebSocket keeps
    ingesting, and the recovery cycle resumes on its own.
    """
    return rest_gate_status(adapter) == REST_GATE_SUSPENDED


async def forever(name: str, coro: Awaitable[None]) -> None:
    await coro
    raise RuntimeError(f"task {name} exited unexpectedly")


class IngestionHealth:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.state = "initializing"
        self.last_data: float | None = None
        self.unhealthy_since: float | None = None
        self.connect_started = clock()
        self.connect_timed_out = False

    def update(self, state: str, *, active: bool) -> None:
        now = self.clock()
        if not active:
            self.state = "idle"
            self.unhealthy_since = None
            return
        if state != self.state and state == "connecting":
            self.connect_started = now
        if state in ("connecting", "reconnecting") and self.unhealthy_since is None:
            self.unhealthy_since = now
        self.state = state

    def data_event(self) -> None:
        self.last_data = self.clock()
        if self.state == "connected":
            self.unhealthy_since = None
            self.connect_timed_out = False

    def observe_adapter(self, adapter: Any, *, active: bool) -> None:
        self.update(adapter.connection_state(), active=active)
        states = getattr(adapter, "connection_states", None)
        if states is None:
            return
        self.connect_timed_out = False
        for state in states().values():
            started = connection_field(state, "connect_attempt_started_monotonic")
            if started is not None and self.clock() - started >= 15:
                self.connect_timed_out = True

    async def ingestion(self) -> bool:
        now = self.clock()
        if self.state == "idle":
            return True
        if self.last_data is None and self.state != "idle":
            return False
        if self.state == "initializing" or self.connect_timed_out:
            return False
        if self.state == "connected":
            return self.last_data is not None and now - self.last_data < 60
        if self.state in ("connecting", "reconnecting"):
            if self.last_data is None and now - self.connect_started >= 15:
                return False
            return self.unhealthy_since is not None and now - self.unhealthy_since < 120
        return False


@dataclass
class ConnectionProgress:
    seen: Any
    last_progress: float
    restarts: int = 0


class Watchdog:
    """Optional connection_states(): mapping id -> subscriptions,last_event_at.

    last_event_at is a progress token (UTC datetime or monotonic value); age
    always uses our monotonic clock, so wall-clock corrections cannot hide silence.
    """

    def __init__(
        self,
        adapter: Any,
        warning: Callable[[str], Awaitable[None]],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.adapter = adapter
        self.warning = warning
        self.clock = clock
        self.connections: dict[str, ConnectionProgress] = {}
        self.last_event: float | None = None
        self.restart_stream = False

    async def check(self, *, active: bool) -> None:
        if not active:
            self.connections.clear()
            return
        states_fn = getattr(self.adapter, "connection_states", None)
        states = (
            states_fn()
            if states_fn
            else {"stream": {"subscriptions": 1, "last_event_at": self.last_event}}
        )
        now = self.clock()
        for name in list(self.connections):
            if name not in states:
                del self.connections[name]
        for name, state in states.items():
            if not connection_field(state, "subscriptions"):
                self.connections.pop(name, None)
                continue
            token = connection_field(state, "last_data_event_monotonic")
            if token is None:
                token = connection_field(state, "last_event_at")
            progress = self.connections.setdefault(name, ConnectionProgress(token, now))
            if token is not None and token != progress.seen:
                progress.seen, progress.last_progress, progress.restarts = token, now, 0
            if now - progress.last_progress < 30:
                continue
            progress.restarts += 1
            progress.last_progress = now
            await self.warning(f"connection {name} silent for 30s; restart {progress.restarts}")
            restart = getattr(self.adapter, "restart_connection", None)
            if restart:
                await restart(name)
            else:
                self.restart_stream = True
            if progress.restarts >= 3:
                raise RuntimeError(f"connection {name} made no progress after 3 restarts")
