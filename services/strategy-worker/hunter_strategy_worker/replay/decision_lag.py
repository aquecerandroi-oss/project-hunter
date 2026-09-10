"""Decision-lag hysteresis for the replay pause gate (T3.80).

T3.76 ran a replay via ``docker exec hunter-strategy-worker-1 ... replay.run``
-- inside the live worker's own container, sharing its CPU and DB pool. The
live lane's own decision lag (bar close -> persisted decision, T3.74c) climbed
from a 26 s median to a 90 s median / 171 s p95 while neither
:mod:`hunter_strategy_worker.replay.budget`'s ``outbox_lag_s`` check nor
:mod:`.consumer_lag`'s ``XINFO`` reading ever moved -- both stayed at their
healthy baseline throughout (``notes-T3.80.md``). ``decision_lag_p50_s``/
``decision_lag_p95_s`` (T3.74c, ``hb:strategy:shadow``) are the only signal
that actually saw it, so this reads them directly, the same way
:mod:`.budget` already reads ``outbox_lag_s`` off the same hash.

**Hysteresis.** The gate does not clear the instant one reading comes back
healthy: a single sample can be a burst that resolved between two 10 s
heartbeat writes, and resuming into a lane whose own backlog (the one the
replay itself caused) is still draining just restarts the same interference a
slice later. Recovery requires ``resume_healthy_s`` of continuously-healthy
readings. That state is kept in **Redis**, not in this process's memory,
because a queue drain is typically one process per slice (a fresh
``bash infra/vps/compose.sh replay ...`` invocation), which would otherwise
forget the last bad reading the moment it exits.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

DECISION_LAG_SINCE_KEY = "replay:decision_lag_last_bad_at"
"""When the last over-threshold reading happened, ISO 8601 UTC. TTL is
generous against any plausible ``resume_healthy_s`` so a crashed drain does
not leave a stale key blocking a resume forever, nor let one expire mid-wait."""

_SINCE_TTL_S = 3600

__all__ = ["DECISION_LAG_SINCE_KEY", "decision_lag_reason"]


def _parse(fields: dict[str, str], name: str) -> float | None:
    raw = fields.get(name)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _fmt(value: float | None) -> str:
    return "?" if value is None else f"{value:.0f}"


async def decision_lag_reason(
    redis: redis_asyncio.Redis,
    fields: dict[str, str],
    *,
    p50_max_s: float,
    p95_max_s: float,
    resume_healthy_s: float,
    now: datetime,
    key: str = DECISION_LAG_SINCE_KEY,
) -> str | None:
    """``decision_lag:p50=..,p95=..`` over threshold, ``decision_lag_cooldown:<s>``
    for ``resume_healthy_s`` after the last time it was, or ``None``.

    Missing readings (``""`` -- no signal has been persisted yet this process
    lifetime, ``heartbeat.py``) are treated as "no evidence", never as
    degraded: touching neither this axis nor Redis, so a worker that has not
    decided anything yet does not block a replay on that account alone, and a
    heartbeat fixture with no decision-lag fields at all (every gate test
    before T3.80) never has to know this check exists.
    """
    p50 = _parse(fields, "decision_lag_p50_s")
    p95 = _parse(fields, "decision_lag_p95_s")
    if p50 is None and p95 is None:
        return None
    now = ensure_utc(now)
    over = (p50 is not None and p50 > p50_max_s) or (p95 is not None and p95 > p95_max_s)
    if over:
        try:
            await cast("Any", redis).set(key, now.isoformat(), ex=_SINCE_TTL_S)
        except Exception:
            logger.warning("replay_decision_lag_since_unwritable")
        return f"decision_lag:p50={_fmt(p50)}s,p95={_fmt(p95)}s"
    try:
        raw_since: Any = await cast("Any", redis).get(key)
    except Exception:
        logger.warning("replay_decision_lag_since_unreadable")
        return "decision_lag_since_unreadable"
    if raw_since is None:
        return None
    text = raw_since.decode() if isinstance(raw_since, bytes) else str(raw_since)
    try:
        since = ensure_utc(datetime.fromisoformat(text))
    except ValueError:
        return None
    elapsed = (now - since).total_seconds()
    if elapsed < resume_healthy_s:
        return f"decision_lag_cooldown:{resume_healthy_s - elapsed:.0f}s"
    return None
