"""The fixed event envelope every Redis Stream message carries.

ARCHITECTURE.md §5.1 — exact shape:

    {"event_id": "uuid7", "type": "...", "ts": "...", "producer": "...", "key": "...", "payload": {}}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import orjson
from pydantic import BaseModel, ConfigDict, Field

from hunter_core.domain.types import utcnow, uuid7


class EventEnvelope(BaseModel):
    """One Redis Stream message, independent of which stream it lives on."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid7)
    type: str
    ts: datetime = Field(default_factory=utcnow)
    producer: str
    key: str
    payload: dict[str, Any]

    def to_bytes(self) -> bytes:
        """Serialize with orjson — used as the ``XADD`` field value."""
        return orjson.dumps(self.model_dump(mode="json"))

    @classmethod
    def from_bytes(cls, data: bytes) -> EventEnvelope:
        """Deserialize a value previously produced by :meth:`to_bytes`."""
        return cls.model_validate(orjson.loads(data))
