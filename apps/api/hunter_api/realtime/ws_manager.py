"""Connection <-> channel fan-out for the ``/ws`` gateway.

ARCHITECTURE.md §5.2: the api subscribes to a Redis channel only while at
least one client wants it, and forwards to every WebSocket subscribed to
that channel. Authorization (only members of an org may subscribe to
``rt:org:{id}:*``) lives in ``realtime.channels``; this class tracks the
fan-out — and, since it is already the process's register of live sockets,
how many of them one principal is holding (:meth:`try_register`).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from hunter_core.logging import get_logger

logger = get_logger(__name__)


class SendsText(Protocol):
    """The one method fan-out needs — matches ``starlette.WebSocket``."""

    async def send_text(self, data: str) -> None: ...


class ConnectionManager:
    """Tracks which connections are subscribed to which channels."""

    def __init__(self) -> None:
        self._channels: dict[str, set[SendsText]] = defaultdict(set)
        self._by_principal: dict[str, set[SendsText]] = {}
        self._principal_of: dict[SendsText, str] = {}

    def try_register(self, connection: SendsText, principal_id: str, limit: int) -> bool:
        """Claim one of ``principal_id``'s connection slots. ``False`` when full.

        Check and claim in one call because they must not be separable: two
        sockets authenticating at the same moment would both read "4 < 5" and
        both register. The event loop is single-threaded, and this function
        never awaits, so the pair is atomic.

        In-process on purpose. The cap bounds what *this* replica will hold —
        tasks, Redis subscriptions and sockets are per process, and that is
        what runs out. A cluster-wide cap would need a shared counter that has
        to be reconciled every time a process dies with sockets open.
        """
        holders = self._by_principal.setdefault(principal_id, set())
        if connection in holders:
            return True
        if len(holders) >= limit:
            return False
        holders.add(connection)
        self._principal_of[connection] = principal_id
        return True

    def release(self, connection: SendsText) -> None:
        """Give the slot back — called on disconnect, however it happened."""
        principal_id = self._principal_of.pop(connection, None)
        if principal_id is None:
            return
        holders = self._by_principal.get(principal_id)
        if holders is None:
            return
        holders.discard(connection)
        if not holders:
            del self._by_principal[principal_id]

    def connection_count(self, principal_id: str) -> int:
        return len(self._by_principal.get(principal_id, ()))

    def subscribe(self, connection: SendsText, channel: str) -> None:
        self._channels[channel].add(connection)

    def unsubscribe(self, connection: SendsText, channel: str) -> None:
        subscribers = self._channels.get(channel)
        if subscribers is None:
            return
        subscribers.discard(connection)
        if not subscribers:
            del self._channels[channel]

    def unsubscribe_all(self, connection: SendsText) -> None:
        """Drop ``connection`` from every channel — call this on disconnect."""
        for channel in list(self._channels):
            self.unsubscribe(connection, channel)

    def subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, ()))

    def channels(self) -> list[str]:
        """Every channel with at least one subscriber."""
        return list(self._channels)

    async def broadcast(self, channel: str, message: str) -> int:
        """Send ``message`` to every connection subscribed to ``channel``.

        A connection whose ``send_text`` raises (dropped socket, etc.) is
        evicted from every channel it was subscribed to — not just this one
        — and the exception is swallowed so the rest of the fan-out still
        happens. Returns how many connections were successfully delivered to.
        """
        delivered = 0
        for connection in list(self._channels.get(channel, ())):
            try:
                await connection.send_text(message)
            except Exception:
                logger.warning("ws_broadcast_send_failed", channel=channel)
                self.unsubscribe_all(connection)
            else:
                delivered += 1
        return delivered
