"""Readiness and the heartbeat hash -- ARCHITECTURE.md section 11.

``/ready`` is false unless all of these hold, and each is registered under its
own ``__name__`` so the payload names what failed instead of returning an
anonymous ``false``:

- **``scanner_consumers``** -- every stream loop is keeping up. A quiet stream
  is not a stuck consumer and must not read as one: ``market.liquidations``
  published sixty events in half an hour during the operational proof and turned
  ``/ready`` red, because the loop can only record progress when a message
  arrives. So the check compares what the consumer last saw with what the
  *stream* last published (``XREVRANGE``, the same probe the strategy-worker
  uses): behind means stuck, level means idle;
- **``scanner_evaluation``** -- the evaluation cycle is running. This is the one
  that matters: consumers that mark work nobody performs would otherwise report
  a perfectly healthy worker producing nothing;
- **``scanner_outbox``** -- nothing queued and unpublished for too long. An
  event stuck in Postgres means the streams no longer reflect the database;
- **``scanner_baselines``** -- the archive was loaded **and** every market's
  baseline state is either usable or declared under construction, for at least
  ``baseline_ready_ratio`` of the universe. Deliberately not "the archive is
  mature": a fresh install has no seven-day history and saying so is the honest
  state, not a failure. While the bootstrap is still walking the universe the
  check stays green *as long as it is advancing* -- a bootstrap that stopped
  advancing below the ratio is a worker that will never have baselines, and that
  is a failure. ``/ready`` carries the sentence itself as a status detail
  (``baselines: "bootstrapping BTCUSDT (37/200)"``), which is a diagnostic and
  never a verdict.

The heartbeat (``hb:scanner:<instance>``) carries the numbers an operator reads
during an incident: universe size, dirty markets, baseline maturity, open
anomalies and the coverage proof the collector is publishing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys
from hunter_scanner_worker.metrics import (
    scanner_anomalies_open,
    scanner_baselines,
    scanner_detectors_disarmed,
    scanner_dirty_markets,
    scanner_hot_rows_decoded_total,
    scanner_hot_rows_resident,
    scanner_universe_size,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import redis.asyncio as redis_asyncio

    from hunter_core.events.outbox import OutboxHealth
    from hunter_core.runtime import WorkerRuntime
    from hunter_scanner_worker.baseline_runner import BootstrapProgress
    from hunter_scanner_worker.config import ScannerConfig
    from hunter_scanner_worker.consumers import ConsumerHealth
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

HB_TTL_S = 30
MAX_CONSUMER_IDLE_S = 60.0
MAX_CYCLE_IDLE_S = 30.0
OUTBOX_MAX_PENDING = 5_000
OUTBOX_MAX_LAG_S = 60.0

_DISARMED_SEEN: set[tuple[str, str]] = set()

_DECODED_SEEN: dict[str, int] = {}
"""Rows each market had decoded at the previous heartbeat: the metric is a
counter, so what is published is the delta, never the running total."""
"""Label pairs this process has published, so a rearmed detector can be
set back to zero instead of keeping its last value forever."""

__all__ = ["CycleHealth", "newest_stream_entry_at", "readiness_checks", "write_heartbeat"]


class CycleHealth:
    """Liveness and the last cycle's shape, shared with ``/ready``."""

    __slots__ = ("baselines_loaded", "evaluated", "last_cycle_at", "started_at")

    def __init__(self) -> None:
        self.started_at = utcnow()
        self.last_cycle_at = None
        self.evaluated = 0
        self.baselines_loaded = False

    def touch(self, evaluated: int) -> None:
        self.last_cycle_at = utcnow()
        self.evaluated += evaluated

    def alive(self, *, max_idle_s: float = MAX_CYCLE_IDLE_S) -> bool:
        reference = self.last_cycle_at or self.started_at
        return (utcnow() - reference).total_seconds() <= max_idle_s


async def newest_stream_entry_at(redis: redis_asyncio.Redis, stream: str) -> datetime | None:
    """When the newest entry reached ``stream``, from its ``<ms>-<seq>`` id."""
    try:
        entries: Any = await cast(Any, redis).xrevrange(stream, count=1)
    except Exception:
        logger.warning("scanner_stream_probe_failed", stream=stream)
        return None
    if not entries:
        return None
    raw = entries[0][0]
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        milliseconds = int(text.split("-", 1)[0])
    except ValueError:  # pragma: no cover - Redis ids are always <ms>-<seq>
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


def readiness_checks(
    scanner: Scanner,
    consumers: ConsumerHealth,
    cycle: CycleHealth,
    outbox: OutboxHealth,
    config: ScannerConfig,
    redis: redis_asyncio.Redis | None = None,
    progress: BootstrapProgress | None = None,
) -> list[Callable[[], Awaitable[bool]]]:

    async def scanner_consumers() -> bool:
        if not consumers.last_iteration_at:
            return False
        for stream in list(consumers.last_iteration_at):
            if consumers.alive(stream, max_idle_s=MAX_CONSUMER_IDLE_S):
                continue
            if redis is None:
                return False
            # The loop has not moved for a while. That is only a failure if the
            # stream moved *without* it: a market that printed no liquidation
            # for half an hour is a quiet market, not a stuck worker.
            newest = await newest_stream_entry_at(redis, stream)
            seen = consumers.last_iteration_at.get(stream)
            if newest is not None and seen is not None and newest > seen:
                return False
            if newest is None:
                continue
        return True

    async def scanner_evaluation() -> bool:
        return cycle.alive()

    async def scanner_outbox() -> bool:
        return outbox.ready(max_pending=OUTBOX_MAX_PENDING, max_lag_s=OUTBOX_MAX_LAG_S)

    async def scanner_baselines() -> bool:
        if not cycle.baselines_loaded or scanner.cache is None:
            return False
        if progress is None:
            return True
        if progress.ratio >= config.baseline_ready_ratio:
            return True
        # Still building. Green while it advances, red once it stops: a
        # bootstrap that is not moving will never produce a baseline, and a
        # scanner that will never have baselines cannot score anything.
        return progress.active()

    return [scanner_consumers, scanner_evaluation, scanner_outbox, scanner_baselines]


async def write_heartbeat(
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    scanner: Scanner,
    cycle: CycleHealth,
    consumers: ConsumerHealth,
    progress: BootstrapProgress | None = None,
) -> None:
    """``hb:scanner:<instance>`` plus the gauges the dashboards read."""
    markets = list(scanner.state.markets.values())
    open_anomalies = sum(
        1 for market in markets for state in market.anomalies.values() if state.is_open
    )
    maturity = (
        scanner.cache.maturity([market.ref.market_id for market in markets])
        if scanner.cache is not None
        else None
    )
    scanner_universe_size.set(len(markets))
    scanner_dirty_markets.set(scanner.state.dirty)
    # The incremental context, in numbers an operator can see: how many decoded
    # rows are resident and how many rows this process had to decode. In a
    # steady state the second grows by one per market per minute; if it grows by
    # 1500, the reuse stopped happening and the latency is about to say so.
    resident = sum(market.hot.rows for market in markets)
    scanner_hot_rows_resident.labels(kind="candles").set(
        sum(len(market.hot.candles) for market in markets)
    )
    scanner_hot_rows_resident.labels(kind="trades").set(
        sum(len(market.hot.trades) for market in markets)
    )
    # Per market, never a global sum: a market that leaves the universe takes
    # its counter with it, and a delta over the sum would swallow everybody
    # else's increments in that heartbeat (Astra, T2.5c diff review).
    live = {market.ref.symbol for market in markets}
    for symbol in [key for key in _DECODED_SEEN if key not in live]:
        del _DECODED_SEEN[symbol]
    for market in markets:
        decoded = market.hot.decoded
        scanner_hot_rows_decoded_total.inc(
            max(0, decoded - _DECODED_SEEN.get(market.ref.symbol, 0))
        )
        _DECODED_SEEN[market.ref.symbol] = decoded
    scanner_anomalies_open.labels(state="active").set(open_anomalies)
    if maturity is not None:
        scanner_baselines.labels(state="usable").set(maturity.usable)
        scanner_baselines.labels(state="under_construction").set(maturity.under_construction)
    under_construction = sum(1 for market in markets if market.baseline_note is not None)
    disarmed: dict[tuple[str, str], int] = {}
    for market in markets:
        for kind, reason in market.disarmed:
            disarmed[(kind, reason)] = disarmed.get((kind, reason), 0) + 1
    for label in _DISARMED_SEEN - set(disarmed):
        # The last market rearmed: the series has to go to zero, or the gauge
        # keeps reporting detectors that are armed again.
        scanner_detectors_disarmed.labels(type=label[0], reason=label[1]).set(0)
    for (kind, reason), count in disarmed.items():
        scanner_detectors_disarmed.labels(type=kind, reason=reason).set(count)
    _DISARMED_SEEN.update(disarmed)
    mapping = {
        "ts": utcnow().isoformat(),
        "markets": str(len(markets)),
        "dirty": str(scanner.state.dirty),
        "evaluations": str(cycle.evaluated),
        "anomalies_open": str(open_anomalies),
        "baselines_usable": str(maturity.usable if maturity else 0),
        "baselines_under_construction": str(maturity.under_construction if maturity else 0),
        "baselines_state": progress.describe() if progress is not None else "unknown",
        "markets_under_construction": str(under_construction),
        "detectors_disarmed": ",".join(
            f"{kind}:{reason}={count}" for (kind, reason), count in sorted(disarmed.items())
        ),
        "hot_rows_resident": str(resident),
        "coverage": "live" if scanner.coverage.fresh() else "unproven",
        "consumer_errors": str(consumers.errors),
        "errors": str(runtime.error_count),
    }
    key = keys.heartbeat("scanner", runtime.instance)
    try:
        await cast(Any, redis).hset(key, mapping=mapping)
        await redis.expire(key, HB_TTL_S)
    except Exception:
        logger.warning("scanner_heartbeat_write_failed")
