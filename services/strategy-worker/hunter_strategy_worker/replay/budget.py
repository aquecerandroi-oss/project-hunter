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
  Since T3.74b it also reads the live consumer's own backlog
  (:mod:`.consumer_lag`, ``REPLAY_CONSUMER_LAG_MAX``) — the heartbeat alone
  missed the worst decision lag ever measured (125 s+, T3.74 notes §3), where
  ``outbox_lag_s`` read ``0.0`` throughout because the outbox was never the
  bottleneck. Since T3.80 it also reads the heartbeat's own
  ``decision_lag_p50_s``/``_p95_s`` (:mod:`.decision_lag`) — T3.76 ran a
  replay inside the live worker's own container and neither the outbox lag
  nor the consumer's own backlog moved while the live median climbed to 90 s.

The queue is a Redis list, ``replay:queue``, oldest at the tail
(``LPUSH``/``RPOP``): the plantão enqueues "replicate version X over this
window" and the engine drains it one run at a time. It carries a *request*, not
a command — nothing in it can activate, promote or size anything, and the worst
a malformed entry can do is be refused with its reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker.replay.consumer_lag import LIVE_CONSUMER_GROUP, topology_group_lag
from hunter_strategy_worker.replay.decision_lag import decision_lag_reason
from hunter_strategy_worker.replay.queue import (
    QUEUE_KEY,
    ReplayRequest,
    enqueue,
    queue_depth,
    take_next,
)
from hunter_strategy_worker.shard import consumer_groups, heartbeat_keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_core.settings import Settings

logger = get_logger(__name__)

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
    "refuse_direct_run",
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
    decision_lag_p50_max_s: float = 10.0
    decision_lag_p95_max_s: float = 30.0
    decision_lag_resume_healthy_s: float = 300.0
    """T3.80: mirrors ``ShadowConfig.decision_lag_p50_alert_s``/``_p95_alert_s``
    — pause while the live worker's own heartbeat reports a median/p95 past
    these, the signal T3.76's in-container replay moved (90 s / 171 s) while
    ``outbox_lag_s`` and :func:`.consumer_lag.group_lag` stayed healthy. Resumes
    only after ``decision_lag_resume_healthy_s`` (5 min) of continuously-healthy
    readings (:mod:`.decision_lag`), so a lane that just recovered is not handed
    a new slice while the backlog the replay itself caused is still draining."""
    consumer_lag_max: int = 100
    """T3.74b, :func:`.consumer_lag.group_lag`'s reading: entries the stream
    has added minus entries the group has read, independent of
    ``outbox_lag_s`` (which measures what happens *after* a decision is made).

    100, **provisional** (Astra, T3.74b review): read live on the VPS
    (2026-09-10, notes-T3.74b.md §1) the group sat at ``lag=0`` almost always
    and briefly touched 13 on an ordinary 5-minute-aligned burst with no
    reported degradation — one sample, not a calibrated distribution. 100
    clears that one observed blip with margin; it is not claimed to be the
    right size for the confirmed 125 s+ decision lag (below), and moving it
    needs synchronized samples of lag, ``XPENDING`` and decision lag across
    several aligned bars, healthy and degraded, not one more live read.

    Honest limit: the same live read caught that confirmed 125 s+ decision lag
    (T3.74 notes §3) with this group's ``lag`` at or near zero throughout.
    Upstream publish stagger is a *hypothesis* for why, not an established
    cause — ``consume()`` delivers batches of up to 10 entries and marks them
    read before each is individually processed and ACKed
    (``hunter_core.events.consume``), so work already delivered but not yet
    finished would not raise this ``lag`` either. This gate catches a stalled
    or crashed consumer group; it is not a substitute for a lag measured in
    seconds from the consumer's own timings (open, notes-T3.74b.md §1)."""
    queue_key: str = QUEUE_KEY
    shard_total: int = 1
    """T3.87: how many ``strategy-worker`` shards the live lane runs as
    (``STRATEGY_SHARDS``, the same count ``infra/vps/compose.sh``/the compose
    profile use to render ``STRATEGY_SHARD=i/N`` for shards ``0..N-1``).

    The bug this closes: T3.74f split the live worker into ``N`` processes,
    each with its **own** heartbeat key and consumer group
    (``hunter_strategy_worker.shard.heartbeat_key``/``consumer_group``), but
    this gate kept reading one hard-coded key/group -- a key nobody wrote
    anymore and a group nobody advanced anymore, so every replay refused
    forever with ``heartbeat_missing``/a ``lag`` that only ever grew
    (notes-T3.84.md §3). ``shard_total <= 1`` (the default) reproduces every
    reason string byte-for-byte from before this field existed --
    :attr:`heartbeat_key` and :data:`.consumer_lag.LIVE_CONSUMER_GROUP` are
    still read directly, not derived, so ``REPLAY_HEARTBEAT_KEY`` keeps
    working exactly as it always did. ``shard_total > 1`` derives every
    shard's heartbeat key and consumer group from the *same*
    :mod:`hunter_strategy_worker.shard` functions every shard itself uses
    (never a second formula that could drift) and takes the **worst** of the
    ``N`` readings on every axis: any missing heartbeat fails the whole gate
    closed, naming which shard; every other reason (staleness, outbox lag,
    decision lag, consumer lag) is the maximum across all ``N`` shards. A
    consumer group on the stream that belongs to no shard in this topology
    (e.g. the pre-shard ``strategy-worker.shadow`` left behind by a resize) is
    never counted toward that maximum -- it is not live -- and is logged once
    per check as ``orphan_consumer_group`` so an operator can destroy it."""


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
        decision_lag_p50_max_s=_float("REPLAY_DECISION_LAG_P50_MAX_S", 10.0),
        decision_lag_p95_max_s=_float("REPLAY_DECISION_LAG_P95_MAX_S", 30.0),
        decision_lag_resume_healthy_s=_float("REPLAY_DECISION_LAG_RESUME_HEALTHY_S", 300.0),
        consumer_lag_max=_int("REPLAY_CONSUMER_LAG_MAX", 100),
        queue_key=os.environ.get("REPLAY_QUEUE_KEY", QUEUE_KEY).strip() or QUEUE_KEY,
        shard_total=_int("STRATEGY_SHARDS", 1),
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


def _decode_fields(raw: dict[Any, Any]) -> dict[str, str]:
    return {
        (k.decode() if isinstance(k, bytes) else str(k)): (
            v.decode() if isinstance(v, bytes) else str(v)
        )
        for k, v in raw.items()
    }


def _try_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _worst_decision_lag_fields(all_fields: list[dict[str, str]]) -> dict[str, str]:
    """The single ``(p50, p95)`` pair fed to :func:`.decision_lag.decision_lag_reason`
    (T3.87) -- the maximum of each axis across every shard's own heartbeat, so
    one slow shard's backlog pauses the whole lane even while the others read
    healthy. A shard with no reading yet (``""``, T3.74c's "nobody has decided
    anything this process lifetime") contributes nothing to either axis,
    matching :func:`.decision_lag.decision_lag_reason`'s own "no evidence"
    rule for the single-heartbeat case."""
    p50s = [v for f in all_fields if (v := _try_float(f.get("decision_lag_p50_s"))) is not None]
    p95s = [v for f in all_fields if (v := _try_float(f.get("decision_lag_p95_s"))) is not None]
    worst: dict[str, str] = {}
    if p50s:
        worst["decision_lag_p50_s"] = str(max(p50s))
    if p95s:
        worst["decision_lag_p95_s"] = str(max(p95s))
    return worst


async def live_lane_degraded(
    redis: redis_asyncio.Redis, budget: ReplayBudget, *, now: datetime | None = None
) -> str | None:
    """The reason the replay should pause, or ``None`` when the live lane is fine.

    Reasons are names, never booleans: ``heartbeat_missing`` (or, with
    ``shard_total > 1``, ``heartbeat_missing:<key>`` naming the absent shard),
    ``heartbeat_stale:<age>s``, ``outbox_lag:<lag>s``, ``heartbeat_unreadable``,
    ``decision_lag:p50=..,p95=..`` / ``decision_lag_cooldown:<s>`` (T3.80,
    :mod:`.decision_lag`), ``consumer_lag:<n>`` (T3.74b), ``consumer_lag_unreadable``.
    A Redis failure answers *degraded*, on the same principle as
    ``eligibility.universe_changed_after``: when health cannot be established,
    the answer that costs a replay is the safe one.

    **Sharded topologies (T3.87).** ``budget.shard_total <= 1`` reproduces the
    single-key/single-group behaviour above byte-for-byte (``budget.heartbeat_key``,
    honouring ``REPLAY_HEARTBEAT_KEY``, and :data:`.consumer_lag.LIVE_CONSUMER_GROUP`).
    ``shard_total > 1`` reads every shard's own heartbeat
    (:func:`hunter_strategy_worker.shard.heartbeat_keys`) and consumer group
    (:func:`hunter_strategy_worker.shard.consumer_groups`) -- the same functions
    every live shard already uses to name itself, never a second formula.
    A missing heartbeat on *any* shard fails the gate closed immediately,
    naming which one; every other axis takes the **worst** (maximum) reading
    across all ``N`` shards. A consumer group on the stream that is not part of
    this topology (e.g. a pre-resize orphan) never counts toward that maximum
    and is logged once per check as ``orphan_consumer_group``.
    """
    if not budget.pause_on_degraded:
        return None
    clock = ensure_utc(now or utcnow())
    shard_total = max(1, budget.shard_total)
    keys = heartbeat_keys(shard_total) if shard_total > 1 else (budget.heartbeat_key,)
    groups = consumer_groups(shard_total) if shard_total > 1 else (LIVE_CONSUMER_GROUP,)

    all_fields: list[dict[str, str]] = []
    for key in keys:
        try:
            raw: dict[Any, Any] = await cast("Any", redis).hgetall(key)
        except Exception:
            logger.warning("replay_heartbeat_unreadable", key=key)
            return "heartbeat_unreadable"
        fields = _decode_fields(raw)
        if not fields:
            return "heartbeat_missing" if shard_total <= 1 else f"heartbeat_missing:{key}"
        all_fields.append(fields)

    max_age = 0.0
    max_outbox_lag = 0.0
    for fields in all_fields:
        stamp = fields.get("ts") or ""
        try:
            age = (clock - ensure_utc(datetime.fromisoformat(stamp))).total_seconds()
        except ValueError:
            return "heartbeat_unreadable"
        max_age = max(max_age, age)
        try:
            outbox_lag = float(fields.get("outbox_lag_s") or 0.0)
        except ValueError:
            return "heartbeat_unreadable"
        max_outbox_lag = max(max_outbox_lag, outbox_lag)

    if max_age > budget.heartbeat_max_age_s:
        return f"heartbeat_stale:{max_age:.0f}s"
    if max_outbox_lag > budget.outbox_lag_max_s:
        return f"outbox_lag:{max_outbox_lag:.0f}s"

    lag_reason = await decision_lag_reason(
        redis,
        _worst_decision_lag_fields(all_fields),
        p50_max_s=budget.decision_lag_p50_max_s,
        p95_max_s=budget.decision_lag_p95_max_s,
        resume_healthy_s=budget.decision_lag_resume_healthy_s,
        now=clock,
    )
    if lag_reason is not None:
        return lag_reason

    consumer_lag, orphans = await topology_group_lag(redis, groups=groups)
    for orphan in orphans:
        logger.warning("orphan_consumer_group", name=orphan)
    if consumer_lag is None:
        return "consumer_lag_unreadable"
    if consumer_lag > budget.consumer_lag_max:
        return f"consumer_lag:{consumer_lag}"
    return None


async def refuse_direct_run(settings: Settings, budget: ReplayBudget) -> str | None:
    """:func:`live_lane_degraded`, for a direct (non-queued) invocation (T3.74).

    A queue drain already holds one Redis client for the whole loop; a single
    ``--version``/``--from``/``--to`` run has none in hand, so this opens and
    closes its own just for the check.
    """
    from hunter_core.redis import create_redis

    redis = create_redis(settings)
    try:
        return await live_lane_degraded(redis, budget)
    finally:
        await redis.aclose()
