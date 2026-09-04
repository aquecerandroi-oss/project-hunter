"""Connection <-> channel fan-out for the ``/ws`` gateway.

ARCHITECTURE.md §5.2: the api subscribes to a Redis channel only while at
least one client wants it, and forwards to every WebSocket subscribed to
that channel. Auth/authorization (only members of an org may subscribe to
``rt:org:{id}:*``) is a T06 concern; this class only tracks the fan-out.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol


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

    async def broadcast(self, channel: str, message: str) -> None:
        """Send ``message`` to every connection subscribed to ``channel``."""
        for connection in list(self._channels.get(channel, ())):
            await connection.send_text(message)
