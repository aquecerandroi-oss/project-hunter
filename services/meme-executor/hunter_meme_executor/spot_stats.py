"""T4.74-4 — the counters of the ``spot/1`` lane (design §7), one object per
process (``ExecutorContext.spot``, wired by T4.74-5), written by
``spot_entries.py`` / ``spot_exits.py`` and read by ``spot_heartbeat.py``.

Memory only, bounded (``refused_by_reason`` keeps every name it saw; the
heartbeat publishes the top 8); a restart starts at zero, never at a guess —
the durable numbers (``closed``, ``lane``) are re-read from Postgres on every
entries tick. Split from ``spot_entries.py`` so ``context.py`` can import the
type without dragging the money path in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hunter_meme_executor.spot_exit_rules import LaneState
    from hunter_meme_executor.spot_repo_positions import ClosedStats

__all__ = ["SpotStats"]


@dataclass(slots=True)
class SpotStats:
    signals_seen: int = 0
    """Candidates the entries loop picked up (``enabled`` only)."""
    admitted: int = 0
    """Buys the admission approved (a row ``admitted`` exists for each)."""
    buys_confirmed: int = 0
    buys_unconfirmed: int = 0
    """Buys left ``submitted_unconfirmed`` for the reconcile."""
    sells_confirmed: int = 0
    refused_by_reason: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    exits_by_reason: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    blocked_exits: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    """``position_id -> reason`` after ``MAX_EXIT_ATTEMPTS`` failed sells (design §4)."""
    closed: ClosedStats | None = None
    """§8's numbers as last read (``closed_stats``)."""
    lane: LaneState | None = None
    """``on`` / ``refuted`` / ``cooldown`` as last computed from ``closed``."""
    last_signature: str | None = None
    last_refusal: str | None = None
    last_entries_tick_at: datetime | None = None
    last_exits_tick_at: datetime | None = None
    tick_failures: int = 0
    """Entries ticks that raised (logged, counted, never propagated)."""
    exit_attempts: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    """``position_id -> sell attempts so far`` (seeded from the rows on first sight)."""
    exit_hard_failures: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    """``position_id -> sells that failed for a non-transient reason`` (seeded from
    the rows); ``MAX_EXIT_ATTEMPTS`` of them block the position."""
    exit_backoff_until: dict[str, datetime] = field(default_factory=lambda: dict[str, datetime]())
    """``position_id -> not before`` after a failed sell (``backoff_s``)."""
    mark_failures: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    """``position_id -> consecutive quote failures``; three ⇒ ``mark_stale_s`` (design §4)."""
    mark_ok_at: dict[str, datetime] = field(default_factory=lambda: dict[str, datetime]())
    """``position_id -> last good mark of this process`` (the first failure pins
    the floor of the staleness when none was seen — a lower bound, never a guess)."""
    reconciled_buys: int = 0
    """Buys the reconcile confirmed late and opened (T4.74-5)."""
    reconciled_expired: int = 0
    """Rows the reconcile settled ``failed:blockhash_expired_never_landed``."""

    def forget_position(self, position_id: str) -> None:
        """A closed position leaves every per-position memory."""
        for memory in (
            self.exit_attempts,
            self.exit_hard_failures,
            self.exit_backoff_until,
            self.mark_failures,
            self.mark_ok_at,
            self.blocked_exits,
        ):
            memory.pop(position_id, None)

    def record_refusal(self, reason: str) -> None:
        self.refused_by_reason[reason] = self.refused_by_reason.get(reason, 0) + 1
        self.last_refusal = reason

    def record_exit(self, reason: str) -> None:
        self.exits_by_reason[reason] = self.exits_by_reason.get(reason, 0) + 1
