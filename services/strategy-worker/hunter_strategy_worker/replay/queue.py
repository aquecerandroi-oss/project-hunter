"""``replay:queue`` — the request the plantão enqueues and the engine drains.

Split from :mod:`.budget` for the same reason :mod:`.consumer_lag` was: one
cohesive concern (the request's shape and the Redis list it travels on) with
its own failure modes, kept out of the module that has to stay under the
350-line budget. Re-exported by :mod:`.budget` so every existing
``from hunter_strategy_worker.replay.budget import ReplayRequest, ...`` keeps
working unchanged.
"""

from __future__ import annotations

import json
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

__all__ = ["QUEUE_KEY", "ReplayRequest", "enqueue", "queue_depth", "take_next"]


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
