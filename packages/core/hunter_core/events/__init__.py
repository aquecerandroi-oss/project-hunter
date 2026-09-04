"""Redis Streams envelope, stream registry and idempotent produce/consume helpers.

Public API (see ARCHITECTURE.md §5.1 and PIPELINE.md §10):

- :class:`EventEnvelope` — the fixed envelope every message carries.
- :class:`Streams` / :data:`DEFAULT_MAXLEN` — stream names and their trim target.
- :func:`publish` — ``XADD`` with an approximate ``MAXLEN``.
- :func:`ensure_group` — idempotent consumer-group creation.
- :func:`consume` — an async generator over ``(message_id, envelope)``.
- :func:`ack` — mark an event processed, then ``XACK``.
"""

from hunter_core.events.consume import ack, consume
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import ensure_group, publish
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams

__all__ = [
    "DEFAULT_MAXLEN",
    "EventEnvelope",
    "Streams",
    "ack",
    "consume",
    "ensure_group",
    "publish",
]
