"""Publishing events and provisioning consumer groups.

ARCHITECTURE.md §5.1: "Streams com MAXLEN ~ N (aparado) por tipo; consumer
groups por servico consumidor."
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.events.envelope import EventEnvelope

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

FIELD_NAME = b"data"


async def publish(
    client: redis_asyncio.Redis,
    stream: str,
    envelope: EventEnvelope,
    maxlen: int,
) -> bytes | str:
    """``XADD`` with an approximately-trimmed ``MAXLEN``. Returns the stream id."""
    return await client.xadd(
        stream,
        {FIELD_NAME: envelope.to_bytes()},
        maxlen=maxlen,
        approximate=True,
    )


async def ensure_group(client: redis_asyncio.Redis, stream: str, group: str) -> None:
    """Create ``group`` on ``stream`` if it does not exist yet (idempotent).

    ``mkstream=True`` also creates the stream itself if this is the very
    first consumer group registered before any event was published.
    """
    try:
        await client.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
