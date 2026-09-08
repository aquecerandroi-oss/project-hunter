"""The ledger row of one replay slice — what was replayed, over what, and at what cost.

The receipt is written to **three** places, and each one is there because the
other two cannot do its job:

1. ``replay_runs`` (``0013_replay_runs``, DATABASE.md §25) — the durable record.
   One row per slice, ``SELECT``/``INSERT`` for ``hunter_worker`` and never
   ``UPDATE``/``DELETE``, so a receipt cannot be edited by the process that
   wrote it. This is the only copy that outlives thirty days, and it is the one
   the scoreboard queries;
2. ``system_events`` (``component = 'replay_engine'``), the same audited channel
   the activation and replication scripts use. It is the **operational** record
   — it carries ``level = warning`` when the slice dropped bars, which is what
   an alarm reads — and it is *not* durable on its own: retention deletes it
   after 30 days (DATABASE.md §1.3), shorter than the 15 and 30 days of results
   the replication protocol counts;
3. a JSONL file (``--ledger``), append-only, one object per slice. Ugly and
   honest: it is what survives a database that had to be rebuilt.

The three are written in that order, the first two inside the caller's single
transaction, so a persisted receipt and a published event can never disagree.

``to_jsonable`` is the row column for column, which is why T3.19b could define
the shape here before the table existed and why the migration
(``.claude/state/brief-T3.19b-db-replay-runs.md``) was a transcription.

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

TABLE = "replay_runs"
"""The durable half of the receipt — ``0013_replay_runs``, DATABASE.md §25."""

__all__ = [
    "COMPONENT",
    "EVENT_FINISHED",
    "TABLE",
    "ReplayRun",
    "append_jsonl",
    "record_run",
    "record_slice",
]


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


_INSERT_SLICE = text(
    f"INSERT INTO {TABLE} (id, run_id, cohort, strategy_version_id, window_from, window_to, "  # noqa: S608
    "markets, started_at, finished_at, bars_evaluated, signals, outcomes_resolved, "
    "outcomes_open, seconds, decision_lag_s, workers, evaluations_by_state, errors) "
    "VALUES (:id, :run_id, :cohort, :strategy_version_id, :window_from, :window_to, "
    "CAST(:markets AS text[]), :started_at, :finished_at, :bars_evaluated, :signals, "
    ":outcomes_resolved, :outcomes_open, CAST(:seconds AS numeric), :decision_lag_s, "
    ":workers, CAST(:evaluations_by_state AS jsonb), :errors) "
    "ON CONFLICT (run_id, window_from, window_to) DO NOTHING RETURNING id"
)
"""``seconds`` is bound as a *string* and cast, never as a float.

``NUMERIC(12,3)`` is the column (§25.2) and a float parameter is exactly the
round trip through binary floating point the project refuses everywhere else.
``ON CONFLICT ... DO NOTHING`` is the idempotence ``uq_replay_runs_slice``
promises: replaying the same slice twice writes one receipt, the same way
``uuid5`` signal identity makes the decisions themselves idempotent. It is
``DO NOTHING`` and not ``DO UPDATE`` because the role has no ``UPDATE`` — and
that is the point, not a limitation to work around.
"""


async def _table_exists(session: AsyncSession) -> bool:
    """Whether ``0013_replay_runs`` has been applied to this database.

    Asked instead of discovered, for the reason §17.2 gives about the scanner's
    baseline-lock probe: a statement that fails on a missing relation **aborts
    the whole transaction**, so an unmigrated database would lose the
    ``system_events`` half of the receipt as well — a run of thirty minutes
    reporting nothing at all because of a deploy ordering. One extra round trip
    per slice (never per bar) buys the degraded path.
    """
    return bool(await session.scalar(text(f"SELECT to_regclass('public.{TABLE}')")))


async def record_slice(session: AsyncSession, run: ReplayRun) -> uuid.UUID | None:
    """Insert the durable receipt. Returns its id, or ``None`` if it existed.

    Also ``None`` — with an ``error`` log, never silence — when the table is not
    there: the caller's other two branches still write, and the log names the
    revision to apply.
    """
    if not await _table_exists(session):
        logger.error(
            "replay_run_table_missing",
            table=TABLE,
            cohort=run.cohort,
            hint="apply 0013_replay_runs; this run is only in system_events and the JSONL",
        )
        return None
    row_id = uuid7()
    stored = await session.scalar(
        _INSERT_SLICE,
        {
            "id": row_id,
            "run_id": run.run_id,
            "cohort": run.cohort,
            "strategy_version_id": run.strategy_version_id,
            "window_from": ensure_utc(run.window_from),
            "window_to": ensure_utc(run.window_to),
            "markets": list(run.markets),
            "started_at": ensure_utc(run.started_at),
            "finished_at": ensure_utc(run.finished_at),
            "bars_evaluated": run.bars_evaluated,
            "signals": run.signals,
            "outcomes_resolved": run.outcomes_resolved,
            "outcomes_open": run.outcomes_open,
            "seconds": f"{run.seconds:.3f}",
            "decision_lag_s": run.decision_lag_s,
            "workers": run.workers,
            "evaluations_by_state": json.dumps(dict(run.evaluations_by_state)),
            "errors": run.errors,
        },
    )
    if stored is None:
        logger.info(
            "replay_run_slice_already_recorded",
            cohort=run.cohort,
            window_from=ensure_utc(run.window_from).isoformat(),
            window_to=ensure_utc(run.window_to).isoformat(),
        )
        return None
    return uuid.UUID(str(stored))


async def record_run(session: AsyncSession, run: ReplayRun) -> uuid.UUID:
    """Write the durable receipt and the operational event. Returns the event id.

    Both in the caller's transaction, ``replay_runs`` first: a published event
    that no stored row explains is the disagreement the outbox pattern exists to
    prevent, one table over.

    ``level`` is ``warning`` when the run had errors and ``info`` otherwise: a
    replay that dropped bars is still a result, but it must not read like a
    clean one (plantão rule 10 — silence in a research log is indistinguishable
    from a broken instrument).
    """
    await record_slice(session, run)
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
