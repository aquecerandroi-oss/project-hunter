"""Serving ``market.backfill.requested``: history someone else needs, fetched here.

The joint M2 decision (``docs/plans/M2.md``) gives REST to the market-worker
alone — it owns the rate limit, ``ingestion_gaps`` and the recovery loop — so a
worker that needs older candles states the need on this stream instead of
fetching them. The scanner has been publishing since T2.5b and, until this
module, nobody was listening: 29 messages on the stream and ``XINFO GROUPS``
empty. A market with no history stayed "under construction" forever, which was
the highest blocker of the M2.

**What this consumer does is planning, not fetching.** It turns one request into
``ingestion_gaps`` rows and stops. The rows are drained by the recovery loop that
already exists, under the REST budget that already exists, in the tier that
already puts live collection first (``recovery.MAX_HISTORY_GAPS_PER_CYCLE`` and
``HISTORY_BUDGET_S``). Nothing here calls an exchange, and the answer to a served
request is the one the pipeline already has: ``upsert_candles`` enqueues
``market.candles.closed`` for every backfilled minute, in the transaction that
persisted it (``durable.enqueue_candles``).

**One group per shard.** Every shard subscribes to the whole stream with a group
of its own, and only the shard that owns the market (``universe.shard_symbols``,
``MARKET_SHARD=i/N``) plans it; the others acknowledge and write nothing. A
single shared group would deliver each request to exactly one shard, which would
then have to discard the ones it does not own — the request would be lost. The
cost is stated: the groups are named after the exchange and the topology, so
changing ``N`` leaves the old groups behind (they must be deleted by hand, and
deleting one with pending entries loses them) and each group carries its own
``hunter:processed:{group}`` set.

**An acknowledgement is not always a mark.** A refusal that depends on the
present state of the world — the market is not in this universe *right now*, the
window has not closed *yet*, the partition does not exist *yet* — is ``XACK``ed
without recording the ``event_id`` as processed, so the hourly republication of
the same identity is evaluated again from scratch. Only a request this pass
planned in full is marked. (Astra, T2.5-backfill design review, must-fix 1 and 4.)
"""

from __future__ import annotations

import asyncio
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from prometheus_client import Counter

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.events.consume import ack, is_processed
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_core.observability import registry
from hunter_market_worker import backfill_plan as planning
from hunter_market_worker import backfill_request as requests
from hunter_market_worker import recovery_queries as queries
from hunter_market_worker.backfill_reader import CLAIM_IDLE_MS, DEFAULT_BLOCK_MS, read_batch
from hunter_market_worker.partitions import storable_months
from hunter_market_worker.persist import load_market_ids
from hunter_market_worker.recovery import DETECTION_GRACE, server_now

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.events.envelope import EventEnvelope
    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_market_worker.universe import MonitoredUniverse

logger = get_logger(__name__)

STREAM = Streams.MARKET_BACKFILL_REQUESTED
IDLE_SLEEP_S = 1.0
MAX_MESSAGE_ATTEMPTS = 3
"""Transient failures tolerated before a message is acknowledged and dropped.

A Postgres error is not a refusal: the message stays pending and comes back
through ``XAUTOCLAIM``. But a message that fails every time would come back
forever, so after this many attempts it is acknowledged with ``outcome=failed``
and an ``error`` log — the request is lost, said out loud, instead of a silent
loop."""

market_backfill_requests_total = Counter(
    "market_backfill_requests_total",
    "Backfill requests read from market.backfill.requested, by outcome.",
    ["outcome"],
    registry=registry,
)
market_backfill_minutes_total = Counter(
    "market_backfill_minutes_total",
    "Minutes of history turned into ingestion_gaps rows by a backfill request.",
    registry=registry,
)


@dataclass(frozen=True)
class Outcome:
    """What happened to one request, in one word plus the reason."""

    name: str
    reason: str = ""
    minutes: int = 0
    chunks: int = 0
    deferred: int = 0
    final: bool = False


@dataclass
class BackfillConsumer:
    """One shard's consumer of the backfill stream."""

    session_factory: async_sessionmaker[AsyncSession]
    adapter: Any
    redis: redis_asyncio.Redis
    universe: MonitoredUniverse
    settings: Settings
    instance: str = "0"
    claim_idle_ms: int = CLAIM_IDLE_MS
    block_ms: int = DEFAULT_BLOCK_MS
    _attempts: dict[str, int] = field(default_factory=dict[str, int])

    @property
    def group(self) -> str:
        return (
            f"market-worker.backfill.{self.adapter.code}"
            f".{self.settings.shard_index}of{self.settings.shard_total}"
        )

    def owns(self, symbol: str) -> bool:
        """The same slice ``universe.shard_symbols`` applies, for one symbol."""
        return (
            zlib.crc32(symbol.encode("utf-8")) % self.settings.shard_total
            == self.settings.shard_index
        )

    async def run_once(self, *, block_ms: int | None = None) -> list[Outcome]:
        messages = await read_batch(
            self.redis,
            STREAM,
            self.group,
            self.instance,
            block_ms=self.block_ms if block_ms is None else block_ms,
            claim_idle_ms=self.claim_idle_ms,
        )
        return [await self._process(message_id, envelope) for message_id, envelope in messages]

    async def _process(self, message_id: str, envelope: EventEnvelope | None) -> Outcome:
        if envelope is None:
            logger.warning("market_backfill_unreadable_message", message_id=message_id)
            await self.redis.xack(STREAM, self.group, message_id)
            return self._counted(Outcome("malformed", "unreadable_envelope"))
        event_id = str(envelope.event_id)
        if await is_processed(self.redis, self.group, event_id):
            await self.redis.xack(STREAM, self.group, message_id)
            return self._counted(Outcome("duplicate", "already_processed"))
        try:
            outcome = await self.plan(envelope.payload, event_id=event_id)
        except Exception:
            return await self._failed(message_id, event_id)
        self._attempts.pop(event_id, None)
        if outcome.final:
            await ack(self.redis, STREAM, self.group, message_id, envelope)
        else:
            # Acknowledged, deliberately unmarked: the same event_id republished
            # later must be evaluated again (see the module docstring).
            await self.redis.xack(STREAM, self.group, message_id)
        return self._counted(outcome)

    async def _failed(self, message_id: str, event_id: str) -> Outcome:
        attempts = self._attempts.get(event_id, 0) + 1
        self._attempts[event_id] = attempts
        if attempts >= MAX_MESSAGE_ATTEMPTS:
            logger.exception("market_backfill_giving_up", event_id=event_id, attempts=attempts)
            await self.redis.xack(STREAM, self.group, message_id)
            self._attempts.pop(event_id, None)
            return self._counted(Outcome("failed", "given_up"))
        # Left pending on purpose: XAUTOCLAIM brings it back, and an
        # infrastructure error is not the request's fault.
        logger.exception("market_backfill_failed", event_id=event_id, attempts=attempts)
        return self._counted(Outcome("failed", "retry"))

    def _counted(self, outcome: Outcome) -> Outcome:
        market_backfill_requests_total.labels(outcome=outcome.name).inc()
        if outcome.minutes:
            market_backfill_minutes_total.inc(outcome.minutes)
        return outcome

    async def plan(
        self, payload: dict[str, Any], *, now: datetime | None = None, event_id: str = ""
    ) -> Outcome:
        """Validate one request and write the gap rows it earns."""
        try:
            request = requests.parse_request(payload)
        except planning.Refused as exc:
            return self._refuse(exc.reason, payload.get("symbol", "?"), event_id)
        if request.exchange != self.adapter.code:
            return Outcome("ignored", "other_exchange")
        if not self.owns(request.symbol):
            return Outcome("ignored", "other_shard")
        if request.timeframe != Timeframe.M1.value:
            return self._refuse("unsupported_timeframe", request.symbol, event_id)
        if request.symbol not in set(self.universe.symbols):
            return self._refuse("market_not_monitored", request.symbol, event_id)

        moment = now if now is not None else await server_now(self.adapter)
        detection_last = align_open_time(moment, Timeframe.M1) - DETECTION_GRACE
        try:
            window = planning.normalize_window(
                request.gap_start, request.gap_end, detection_last=detection_last
            )
        except planning.Refused as exc:
            return self._refuse(exc.reason, request.symbol, event_id)
        return await self._write(request, window, event_id)

    async def _write(
        self, request: requests.Request, window: planning.Window, event_id: str
    ) -> Outcome:
        async with role_session(self.session_factory, db_role="hunter_worker") as session:
            # Held across the read and the insert: the periodic detection runs
            # the same protocol for the same markets (recovery.check_gaps).
            await queries.lock_gap_planning(session, request.exchange)
            market_id = await _market_id(session, request)
            if market_id is None:
                return self._refuse("unknown_market", request.symbol, event_id)
            storable = await storable_months(
                session, requests.months_between(window.first_minute, window.last_minute)
            )
            unstorable = {
                minute
                for minute in window.every_minute()
                if (minute.year, minute.month) not in storable
            }
            if len(unstorable) == window.minutes:
                return self._refuse("no_partition", request.symbol, event_id)
            persisted = await queries.persisted(
                session, market_id, window.first_minute, window.last_minute
            )
            blocked = await queries.gap_coverage(
                session, market_id, window.first_minute, window.last_minute
            )
            plan = planning.plan_chunks(window, persisted=persisted, blocked=blocked | unstorable)
            for gap_start, gap_end in plan.chunks:
                session.add(
                    IngestionGap(
                        market_id=market_id,
                        timeframe=Timeframe.M1,
                        gap_start=gap_start,
                        gap_end=gap_end,
                        status="open",
                        attempts=0,
                    )
                )
            await session.flush()

        # Everything this pass did not account for, in one number: the row
        # budget, another gap's minutes, a month with no partition and the tail
        # that has not closed yet. It decides the word *and* the mark, so the
        # metric cannot say "accepted" while the ACK withholds the mark.
        left_out = plan.deferred_minutes + plan.blocked_minutes + window.clamped_minutes
        name = planning.outcome_name(plan, window, left_out)
        logger.info(
            "market_backfill_planned",
            outcome=name,
            exchange=request.exchange,
            symbol=request.symbol,
            shard=f"{self.settings.shard_index}/{self.settings.shard_total}",
            event_id=event_id,
            reason=request.reason,
            requested_by=request.requested_by,
            requested_minutes=window.requested_minutes,
            gap_start=window.first_minute.isoformat(),
            gap_end=window.last_minute.isoformat(),
            minutes=plan.planned_minutes,
            chunks=len(plan.chunks),
            deferred_minutes=plan.deferred_minutes,
            unstorable_minutes=len(unstorable),
            not_settled_minutes=window.clamped_minutes,
        )
        return Outcome(
            name,
            reason=request.reason,
            minutes=plan.planned_minutes,
            chunks=len(plan.chunks),
            deferred=plan.deferred_minutes + window.clamped_minutes,
            final=left_out == 0,
        )

    def _refuse(self, reason: str, symbol: str, event_id: str) -> Outcome:
        logger.warning(
            "market_backfill_refused",
            reason=reason,
            symbol=symbol,
            event_id=event_id,
            exchange=self.adapter.code,
        )
        return Outcome("refused", reason)

    async def run(self, runtime: WorkerRuntime) -> None:
        """Consume forever. Waits for the universe before the first read."""
        # ASYNC110 suggests an event; there is none. ``MonitoredUniverse`` exposes
        # ``initialized`` as a flag and its ``changed`` event is *not* set when the
        # first refresh yields the same (possibly empty) set — waiting on it would
        # park this task forever on a legitimately empty universe.
        while not self.universe.initialized:  # noqa: ASYNC110
            await asyncio.sleep(IDLE_SLEEP_S)
        logger.info("market_backfill_consumer_started", group=self.group, consumer=self.instance)
        while True:
            try:
                await self.run_once()
                runtime.mark_success()
            except Exception:
                logger.exception("market_backfill_cycle_failed", group=self.group)
                runtime.mark_error()
                await asyncio.sleep(IDLE_SLEEP_S)


async def _market_id(session: AsyncSession, request: requests.Request) -> Any:
    """This database's id for the requested market.

    The payload's ``market_id`` is **checked, not trusted**: the symbol and the
    exchange decide, and an identity that disagrees with them is refused rather
    than quietly followed (Astra: "identidade inconsistente recusada").
    """
    ids = await load_market_ids(session, request.exchange, {request.symbol})
    market_id = ids.get(request.symbol)
    if market_id is None or (request.market_id is not None and request.market_id != market_id):
        return None
    return market_id


async def run_backfill(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: Any,
    redis: redis_asyncio.Redis,
    universe: MonitoredUniverse,
    settings: Settings,
    runtime: WorkerRuntime,
) -> None:
    """The task ``main.py`` supervises."""
    consumer = BackfillConsumer(
        session_factory, adapter, redis, universe, settings, instance=runtime.instance
    )
    await consumer.run(runtime)
