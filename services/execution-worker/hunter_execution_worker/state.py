"""What the cycles tell the readiness endpoint and the heartbeat about themselves.

Deliberately **not** a source of truth about the wallet. Everything that decides
money is read from Postgres inside the transaction that acts on it (T3.5 item 7:
"nada em memória é fonte de verdade"); this object only remembers *when* each
cycle last succeeded and how many attempts produced what, so an operator can see
a stalled worker instead of inferring one from silence.

``protection_delay_s`` is the number that matters most: how long the oldest
fired-but-unfilled protection has been waiting. A paper wallet whose stop cannot
find a book is not wrong, it is *late*, and being late is the only failure of a
simulation that destroys information.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from hunter_execution_worker.bridge_inputs import MarkCoverage

__all__ = ["CycleHealth"]

_ONE = Decimal(1)


@dataclass
class CycleHealth:
    """Per-process cycle telemetry. Reset by a restart, and that is correct."""

    started_at: datetime = field(default_factory=utcnow)
    kill_switch_read_at: datetime | None = None
    mtm_written_at: datetime | None = None
    admission_at: datetime | None = None
    entries_at: datetime | None = None
    protection_at: datetime | None = None
    errors: int = 0

    equity: str = ""
    """The last equity written, as a string — the heartbeat shows it and a
    ``Decimal`` never becomes a float on the way there."""

    kill_switch: str = ""
    open_positions: int = 0
    marked_positions: int = 0
    """How many of them the last pass priced with a **live** print. The pair is
    the ``mark_quality`` of T3.29 item 4: ``mtm_fresh`` says a curve point was
    written, this says the prices in it were observed, and only the second one
    can tell a stopped tape from a stable wallet."""

    pending_requests: int = 0
    unreadable_requests: int = 0
    risk_profile: str = "unknown"
    """How the wallet's linked ``risk_profiles`` row resolved on the last
    admission pass — ``risk_profile_linked`` when the engine is applying it, or
    the named refusal that is admitting nothing (T3.69b). ``unknown`` until the
    first pass: a process that has not looked yet must not claim it is fine."""

    bridge_at: datetime | None = None
    """When the autonomy bridge last completed a cycle. ``None`` for ever while
    ``ENABLE_PAPER_AUTONOMY`` is false, which is the normal state."""

    bridge_events: int = 0
    bridge_candidates: int = 0
    degraded_protections: dict[uuid.UUID, datetime] = field(default_factory=lambda: {})
    """Intent id -> when it first went degraded. Emptied when it fills."""

    def record_marks(self, coverage: MarkCoverage) -> None:
        """Take both numbers from one pass, so they can never disagree."""
        self.open_positions = coverage.open_positions
        self.marked_positions = coverage.marked

    def mark_quality(self) -> Decimal:
        """Share of open positions marked live — ``1`` for an empty wallet.

        An empty wallet has nothing whose price could be stale; reporting ``0``
        would make the normal state a permanent alarm.
        """
        if self.open_positions <= 0:
            return _ONE
        return Decimal(self.marked_positions) / Decimal(self.open_positions)

    def age_since_start(self) -> float:
        return (utcnow() - self.started_at).total_seconds()

    def protection_delay_s(self) -> float:
        """Seconds the oldest degraded protection has been waiting. ``0`` if none."""
        if not self.degraded_protections:
            return 0.0
        oldest = min(self.degraded_protections.values())
        return max(0.0, (utcnow() - oldest).total_seconds())

    def mark_degraded(self, intent_id: uuid.UUID, since: datetime) -> None:
        self.degraded_protections.setdefault(intent_id, since)

    def clear_degraded(self, intent_id: uuid.UUID) -> None:
        self.degraded_protections.pop(intent_id, None)
