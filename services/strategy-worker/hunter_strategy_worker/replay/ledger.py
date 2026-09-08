"""The ledger row of one replay run — what was replayed, over what, and at what cost.

T3.19b asks for a ``replay_runs`` table (id, version, window, markets,
started/finished, signals, outcomes, bars, seconds) and, in the same breath,
forbids this task from writing the migration: a table is the
``database-architect``'s. So the shape is defined **here**, once, as
:class:`ReplayRun`, and it is written to the two places that already exist:

1. ``system_events`` (``component = 'replay_engine'``), the same audited channel
   the activation and replication scripts use. It is the operational record, and
   it is **not durable enough on its own**: retention deletes it after 30 days
   (DATABASE.md §12), which is shorter than a replication protocol's own window;
2. a JSONL file (``--ledger``), append-only, one object per run. Ugly and
   honest: until ``replay_runs`` exists, a run older than 30 days is only
   provable from a file somebody kept.

``to_jsonable`` is already the row a ``replay_runs`` INSERT would take, column
for column, so the migration is a transcription and this module's writer becomes
a third branch, not a rewrite. The brief for it is
``.claude/state/brief-T3.19b-db-replay-runs.md``.

Nothing here decides anything. A ledger row is a receipt.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc, uuid7
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

COMPONENT = "replay_engine"
"""``system_events.component`` of every replay run — its own name, so a query
for the Lab's replay history never has to guess which rows are runs."""

EVENT_FINISHED = "replay_run_finished"

__all__ = ["COMPONENT", "EVENT_FINISHED", "ReplayRun", "append_jsonl", "record_run"]


@dataclass(frozen=True, slots=True)
class ReplayRun:
    """One replay run, as the pending ``replay_runs`` row would hold it."""

    run_id: uuid.UUID
    cohort: str
    strategy_version_id: uuid.UUID
    version_label: str
    """``<strategies.key> <strategy_versions.version>`` — legible without a join."""
    window_from: datetime
    window_to: datetime
    markets: tuple[str, ...]
    """``<exchange>:<symbol>`` of every market actually visited, in the order
    they were dispatched. The exchange is in the key because the same
    ``BTCUSDT`` on two exchanges is a different market (REPLICATION.md §3.3)."""
    started_at: datetime
    finished_at: datetime
    bars_evaluated: int
    signals: int
    outcomes_resolved: int
    outcomes_open: int
    """Trackings whose horizon had not closed by the wall clock. Not a failure —
    the honest count of what this run could not resolve yet."""
    seconds: float
    decision_lag_s: int
    """The replay's assumed distance between a bar close and its decision
    (``environment.REPLAY_DECISION_LAG_S``); the only source of a replayed
    ``no_entry: late``, so it belongs in the receipt."""
    workers: int
    evaluations_by_state: Mapping[str, int] = field(default_factory=lambda: {})
    errors: int = 0

    @property
    def bars_per_second(self) -> float:
        return 0.0 if self.seconds <= 0 else self.bars_evaluated / self.seconds

    def to_jsonable(self) -> dict[str, Any]:
        """The row, with every instant ISO-8601 UTC and every number a number."""
        return {
            "run_id": str(self.run_id),
            "cohort": self.cohort,
            "strategy_version_id": str(self.strategy_version_id),
            "version_label": self.version_label,
            "window_from": ensure_utc(self.window_from).isoformat(),
            "window_to": ensure_utc(self.window_to).isoformat(),
            "markets": list(self.markets),
            "market_count": len(self.markets),
            "started_at": ensure_utc(self.started_at).isoformat(),
            "finished_at": ensure_utc(self.finished_at).isoformat(),
            "bars_evaluated": self.bars_evaluated,
            "signals": self.signals,
            "outcomes_resolved": self.outcomes_resolved,
            "outcomes_open": self.outcomes_open,
            "seconds": round(self.seconds, 3),
            "bars_per_second": round(self.bars_per_second, 2),
            "decision_lag_s": self.decision_lag_s,
            "workers": self.workers,
            "evaluations_by_state": dict(self.evaluations_by_state),
            "errors": self.errors,
        }


async def record_run(session: AsyncSession, run: ReplayRun) -> uuid.UUID:
    """Append the run to ``system_events``. Returns the event id.

    ``level`` is ``warning`` when the run had errors and ``info`` otherwise: a
    replay that dropped bars is still a result, but it must not read like a
    clean one (plantão rule 10 — silence in a research log is indistinguishable
    from a broken instrument).
    """
    event_id = uuid7()
    payload = run.to_jsonable()
    await session.execute(
        text(
            "INSERT INTO system_events (id, created_at, level, component, event, message, data) "
            "VALUES (:id, now(), CAST(:level AS event_severity), :component, :event, :message, "
            "CAST(:data AS jsonb))"
        ),
        {
            "id": event_id,
            "level": "warning" if run.errors else "info",
            "component": COMPONENT,
            "event": EVENT_FINISHED,
            "message": (
                f"replay {run.version_label} {len(run.markets)} mercados "
                f"{payload['window_from']}..{payload['window_to']}: "
                f"{run.bars_evaluated} barras, {run.signals} sinais, "
                f"{run.outcomes_resolved} desfechos, {payload['seconds']} s"
            ),
            "data": json.dumps(payload),
        },
    )
    return event_id


def append_jsonl(path: Path, run: ReplayRun) -> None:
    """Append one run to the JSONL ledger, creating the file if needed.

    Append and never rewrite: a ledger that can be edited is not a ledger. A
    failure to write it is logged and re-raised — losing the durable half of the
    receipt silently is exactly the failure this file exists to prevent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run.to_jsonable(), ensure_ascii=False) + "\n")


def market_keys(rows: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """``[(exchange, symbol), ...] -> ("binance:BTCUSDT", ...)``."""
    return tuple(f"{exchange}:{symbol}" for exchange, symbol in rows)
