"""Liveness of the shadow decision loop -- read by ``/ready`` and the heartbeat.

Split out of ``consumer.py`` (T3.82) purely for that file's own 350-line
budget: this is state two other modules (``heartbeat.py``, ``main.py``)
already import across process boundaries, not logic that belongs to the
consume loop itself. ``consumer.py`` re-exports :class:`ConsumerHealth`
unchanged, so nothing importing it from there needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hunter_core.domain.types import utcnow

__all__ = ["ConsumerHealth"]


@dataclass
class ConsumerHealth:
    """Liveness of the decision loop, read by ``/ready``."""

    last_iteration_at: datetime | None = None
    started_at: datetime | None = None
    """When the loop entered ``consume()`` — a worker that has started but has
    seen no message yet is not stuck, it is idle."""
    evaluated_bars: int = 0
    errors: int = 0
    states: dict[str, int] = field(default_factory=lambda: {})
    universe_size: int | None = None  # T3.82: this shard's markets in the shadow universe
    universe_total: int | None = None  # denominator -- None until measured or when disabled

    def touch(self) -> None:
        self.last_iteration_at = utcnow()

    def record(self, state: str) -> None:
        self.states[state] = self.states.get(state, 0) + 1
