"""Redis Streams envelope, stream registry and idempotent produce/consume helpers.

Public API (see ARCHITECTURE.md §5.1 and PIPELINE.md §10):

- :class:`EventEnvelope` — the fixed envelope every message carries.
- :class:`Streams` / :data:`DEFAULT_MAXLEN` — stream names and their trim target.
- :func:`publish` — ``XADD`` with an approximate ``MAXLEN``.
- :func:`ensure_group` — idempotent consumer-group creation.
- :func:`consume` — an async generator over ``(message_id, envelope)``.
- :func:`consume_batches` — the same, one whole read batch at a time (T2.5d).
- :func:`ack` / :func:`ack_many` — mark events processed, then ``XACK``.
"""

from hunter_core.events.consume import ack, ack_many, consume, consume_batches
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import ensure_group, publish
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams

__all__ = [
    "DEFAULT_MAXLEN",
    "EventEnvelope",
    "Streams",
    "ack",
    "ack_many",
    "consume",
    "consume_batches",
    "ensure_group",
    "publish",
]
