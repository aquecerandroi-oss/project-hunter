"""What ``/ready`` and the heartbeat know about the evaluation cycle.

Split out of ``health.py`` for the 350-line budget; ``health`` re-exports every
name here, so nothing that imports ``hunter_scanner_worker.health`` changes.
"""

from __future__ import annotations

from datetime import datetime

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker.failure_summary import summarize_exception

logger = get_logger(__name__)

MAX_CYCLE_IDLE_S = 30.0
MAX_FAILING_S = 120.0
"""How long cycles may fail, with no real commit between, before ``/ready`` is red.

A failing cycle repeats every ~1.25 s, so two minutes is ~100 failures in a row:
longer than a Postgres restart or failover. The 30/09 and 02/10 stops would have
turned ``/ready`` red two minutes after the first failure (Docker ``unhealthy``
~3 minutes after it) instead of after 14 h and 2.5 days. A starting point, not a
measured distribution: tune it from the heartbeat's ``failing_for_s``."""

__all__ = ["MAX_CYCLE_IDLE_S", "MAX_FAILING_S", "CycleHealth"]


class CycleHealth:
    """Liveness and the last cycle's shape, shared with ``/ready``."""

    __slots__ = (
        "baselines_loaded",
        "blocked",
        "checkpoint_failures_total",
        "evaluated",
        "failing_since",
        "failures",
        "failures_total",
        "last_commit_at",
        "last_cycle_at",
        "started_at",
    )

    def __init__(self) -> None:
        self.started_at = utcnow()
        self.last_cycle_at = None
        self.evaluated = 0
        self.baselines_loaded = False
        self.last_commit_at: datetime | None = None
        """The last flush that wrote rows. ``None`` until this process has one."""

        self.failing_since: datetime | None = None
        """First failed cycle of the current streak; only a real commit ends it."""

        self.failures = 0
        """Failed cycles in the current streak."""

        self.failures_total = 0
        """Failed cycles since the process started. The batch is retained and
        retried, not dropped, so this counts failed attempts, not lost rows."""

        self.checkpoint_failures_total = 0
        """Checkpoint passes that raised after a good flush: an ephemeral Redis
        projection, counted on its own because it is not a persistence failure."""

        self.blocked = False
        """The retained batch outlived its bound (``FlushLane``): evaluation is
        paused and ``/ready`` is red until a flush succeeds."""

    def touch(self, evaluated: int) -> None:
        self.last_cycle_at = utcnow()
        self.evaluated += evaluated

    def committed(self) -> None:
        """A flush that **wrote rows** returned without error."""
        self.last_commit_at = utcnow()
        self.failing_since = None
        self.failures = 0

    def failed(self, error: BaseException) -> None:
        """Count a failed cycle and log it as one short line (never the SQL)."""
        self.failures += 1
        self.failures_total += 1
        if self.failing_since is None:
            self.failing_since = utcnow()
        logger.error(
            "scanner_cycle_failed", consecutive=self.failures, **summarize_exception(error)
        )

    def checkpoint_failed(self, error: BaseException) -> None:
        self.checkpoint_failures_total += 1
        logger.warning("scanner_checkpoint_pass_failed", **summarize_exception(error))

    def recovered(self) -> None:
        """Nothing is left behind: the failure streak and the block are over."""
        self.failing_since = None
        self.failures = 0
        self.blocked = False

    def failing_for_s(self) -> float:
        if self.failing_since is None:
            return 0.0
        return (utcnow() - self.failing_since).total_seconds()

    def persistence_stalled(self, max_failing_s: float = MAX_FAILING_S) -> bool:
        return self.blocked or self.failing_for_s() > max_failing_s

    def alive(self, *, max_idle_s: float = MAX_CYCLE_IDLE_S) -> bool:
        reference = self.last_cycle_at or self.started_at
        return (utcnow() - reference).total_seconds() <= max_idle_s
