"""``REPLAY_BUDGET`` — how much machine a replay may take, and the queue it drains.

T3.19b, entrega 2. The replay lane exists to produce validation mass, and the
live lane exists to produce the only population nobody can recompute. When they
compete, **the live lane wins**: a replayed bar can be replayed again tomorrow; a
minute of market the collector missed while the CPU was busy is gone.

Three knobs and one gate, all read from the environment because they are
operational and never part of a frozen experiment (``config.py``'s rule):

- ``REPLAY_CPU_SHARE`` — the fraction of the machine's vCPUs the pool may use.
  0.33 by default: on the VPS's 12 vCPU that is 3 processes (floor), leaving the
  market-worker shards, the scanner, the strategy worker and the execution
  worker the nine they already run on (DEPLOYMENT.md §5);
- ``REPLAY_MAX_WORKERS`` — a hard ceiling regardless of the share, so a bigger
  machine does not silently become a bigger experiment;
- ``REPLAY_MAX_CONCURRENT_RUNS`` — how many *runs* may be in flight. One, by
  default: two runs interleaved make the throughput number of neither of them
  interpretable, and the queue exists precisely so the second waits;
- the **readiness gate** (:func:`live_lane_degraded`): before every slice, the
  live lane's own heartbeat is read. A heartbeat that is missing, stale or
  reporting an outbox lag past the alert threshold pauses the replay. The gate
  reads what the live lane already publishes (``hb:strategy:shadow``,
  ``heartbeat.write_heartbeat``) instead of inventing a second health model.

The queue is a Redis list, ``replay:queue``, oldest at the tail
(``LPUSH``/``RPOP``): the plantão enqueues "replicate version X over this
window" and the engine drains it one run at a time. It carries a *request*, not
a command — nothing in it can activate, promote or size anything, and the worst
a malformed entry can do is be refused with its reason.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.enums import ShadowCohort
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

QUEUE_KEY = "replay:queue"
LIVE_HEARTBEAT_KEY = "hb:strategy:shadow"

__all__ = [
    "LIVE_HEARTBEAT_KEY",
    "QUEUE_KEY",
    "ReplayBudget",
    "ReplayRequest",
    "enqueue",
    "live_lane_degraded",
    "load_budget",
    "queue_depth",
    "take_next",
    "workers_for",
]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else float(raw)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ReplayBudget:
    """What one replay lane is allowed to consume."""

    cpu_share: float = 0.33
    max_workers: int = 4
    max_concurrent_runs: int = 1
    pause_on_degraded: bool = True
    heartbeat_key: str = LIVE_HEARTBEAT_KEY
    heartbeat_max_age_s: float = 60.0
    """Older than this and the live lane is treated as degraded. The live worker
    writes every 10 s with a 60 s TTL (``heartbeat.INTERVAL_S``/``TTL_S``), so a
    heartbeat this old is one the key itself is about to lose."""
    outbox_lag_max_s: float = 60.0
    """Mirrors ``ShadowConfig.outbox_lag_alert_s`` — the same number that makes
    the live worker's own ``/ready`` false."""
    queue_key: str = QUEUE_KEY


def load_budget() -> ReplayBudget:
    """Read the budget from the environment (``REPLAY_*``)."""
    return ReplayBudget(
        cpu_share=_float("REPLAY_CPU_SHARE", 0.33),
        max_workers=_int("REPLAY_MAX_WORKERS", 4),
        max_concurrent_runs=_int("REPLAY_MAX_CONCURRENT_RUNS", 1),
        pause_on_degraded=_bool("REPLAY_PAUSE_ON_DEGRADED", True),
        heartbeat_key=os.environ.get("REPLAY_HEARTBEAT_KEY", LIVE_HEARTBEAT_KEY).strip()
        or LIVE_HEARTBEAT_KEY,
        heartbeat_max_age_s=_float("REPLAY_HEARTBEAT_MAX_AGE_S", 60.0),
        outbox_lag_max_s=_float("REPLAY_OUTBOX_LAG_MAX_S", 60.0),
        queue_key=os.environ.get("REPLAY_QUEUE_KEY", QUEUE_KEY).strip() or QUEUE_KEY,
    )


def workers_for(budget: ReplayBudget, cpu_count: int) -> int:
    """How many processes this budget allows on a machine with ``cpu_count`` vCPU.

    ``floor(cpu_count * cpu_share)`` clamped to ``[1, max_workers]``. The floor
    at one is deliberate: a budget so small it rounds to zero should run slowly,
    not silently do nothing. A pool larger than the number of markets is capped
    by the caller, not here — this function answers about the machine.
    """
    allowed = int(max(0.0, budget.cpu_share) * max(1, cpu_count))
    return max(1, min(budget.max_workers, allowed))


async def live_lane_degraded(
    redis: redis_asyncio.Redis, budget: ReplayBudget, *, now: datetime | None = None
) -> str | None:
    """The reason the replay should pause, or ``None`` when the live lane is fine.

    Reasons are names, never booleans: ``heartbeat_missing``,
    ``heartbeat_stale:<age>s``, ``outbox_lag:<lag>s``, ``heartbeat_unreadable``.
    A Redis failure answers *degraded*, on the same principle as
    ``eligibility.universe_changed_after``: when health cannot be established,
    the answer that costs a replay is the safe one.
    """
    if not budget.pause_on_degraded:
        return None
    clock = ensure_utc(now or utcnow())
    try:
        raw: dict[Any, Any] = await cast("Any", redis).hgetall(budget.heartbeat_key)
    except Exception:
        logger.warning("replay_heartbeat_unreadable", key=budget.heartbeat_key)
        return "heartbeat_unreadable"
    fields = {
        (k.decode() if isinstance(k, bytes) else str(k)): (
            v.decode() if isinstance(v, bytes) else str(v)
        )
        for k, v in raw.items()
    }
    if not fields:
        return "heartbeat_missing"
    stamp = fields.get("ts") or ""
    try:
        age = (clock - ensure_utc(datetime.fromisoformat(stamp))).total_seconds()
    except ValueError:
        return "heartbeat_unreadable"
    if age > budget.heartbeat_max_age_s:
        return f"heartbeat_stale:{age:.0f}s"
    try:
        lag = float(fields.get("outbox_lag_s") or 0.0)
    except ValueError:
        return "heartbeat_unreadable"
    if lag > budget.outbox_lag_max_s:
        return f"outbox_lag:{lag:.0f}s"
    return None


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    """ "Replicate version X over this window" — what the plantão enqueues.

    The cohort travels with the request instead of being minted at drain time so
    that whoever enqueued it can find the population afterwards: a request whose
    label is decided by the consumer is a run nobody can name until it is over.
    """

    strategy_version_id: uuid.UUID
    window_from: datetime
    window_to: datetime
    markets: tuple[str, ...]
    """Symbols, or empty for "every monitored market of the exchange"."""
    cohort: str
    requested_by: str
    requested_at: datetime

    @staticmethod
    def new(
        *,
        strategy_version_id: uuid.UUID,
        window_from: datetime,
        window_to: datetime,
        markets: tuple[str, ...] = (),
        requested_by: str,
        run_id: uuid.UUID | None = None,
        requested_at: datetime | None = None,
    ) -> ReplayRequest:
        """A request with a freshly minted ``replay:<run_id>`` cohort."""
        return ReplayRequest(
            strategy_version_id=strategy_version_id,
            window_from=ensure_utc(window_from),
            window_to=ensure_utc(window_to),
            markets=markets,
            cohort=ShadowCohort.replay(run_id or uuid.uuid4()),
            requested_by=requested_by,
            requested_at=ensure_utc(requested_at or utcnow()),
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "strategy_version_id": str(self.strategy_version_id),
                "window_from": self.window_from.isoformat(),
                "window_to": self.window_to.isoformat(),
                "markets": list(self.markets),
                "cohort": self.cohort,
                "requested_by": self.requested_by,
                "requested_at": self.requested_at.isoformat(),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def from_json(raw: str | bytes) -> ReplayRequest:
        """Parse one queue entry, refusing anything the cohort grammar would not
        accept — a malformed cohort here would become a row the database CHECK
        rejects halfway through a run."""
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        data: dict[str, Any] = json.loads(text)
        cohort = str(data["cohort"])
        if not cohort.startswith(ShadowCohort.REPLAY_PREFIX) or not ShadowCohort.is_valid(cohort):
            raise ValueError(f"{cohort!r} is not a replay cohort")
        return ReplayRequest(
            strategy_version_id=uuid.UUID(str(data["strategy_version_id"])),
            window_from=ensure_utc(datetime.fromisoformat(str(data["window_from"]))),
            window_to=ensure_utc(datetime.fromisoformat(str(data["window_to"]))),
            markets=tuple(str(s) for s in data.get("markets") or ()),
            cohort=cohort,
            requested_by=str(data.get("requested_by") or "unknown"),
            requested_at=ensure_utc(datetime.fromisoformat(str(data["requested_at"]))),
        )


async def enqueue(
    redis: redis_asyncio.Redis, request: ReplayRequest, *, key: str = QUEUE_KEY
) -> int:
    """Put one request at the head of the queue; returns the new depth."""
    depth: int = await cast("Any", redis).lpush(key, request.to_json())
    logger.info(
        "replay_run_enqueued",
        cohort=request.cohort,
        strategy_version_id=str(request.strategy_version_id),
        depth=depth,
    )
    return depth


async def take_next(redis: redis_asyncio.Redis, *, key: str = QUEUE_KEY) -> ReplayRequest | None:
    """Pop the oldest request, or ``None`` when the queue is empty.

    A malformed entry is dropped with its reason logged rather than blocking the
    queue forever — and it is *dropped*, not retried: a request that cannot be
    parsed cannot be run, and leaving it at the tail would starve every valid
    one behind it.
    """
    raw: Any = await cast("Any", redis).rpop(key)
    if raw is None:
        return None
    try:
        return ReplayRequest.from_json(cast("str | bytes", raw))
    except Exception as exc:
        logger.error("replay_queue_entry_unreadable", error=str(exc))
        return None


async def queue_depth(redis: redis_asyncio.Redis, *, key: str = QUEUE_KEY) -> int:
    """How many requests are waiting."""
    return int(await cast("Any", redis).llen(key))
