"""Connection <-> channel fan-out for the ``/ws`` gateway.

ARCHITECTURE.md §5.2: the api subscribes to a Redis channel only while at
least one client wants it, and forwards to every WebSocket subscribed to
that channel. Auth/authorization (only members of an org may subscribe to
``rt:org:{id}:*``) is a T06 concern; this class only tracks the fan-out.
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
