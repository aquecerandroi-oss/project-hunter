"""Readiness of the shadow worker — ARCHITECTURE.md §11, brief S2.

``/ready`` is false unless all four hold:

- the ``0002_shadow_lab`` objects exist. Without them nothing can be persisted,
  and a version must never be activated against a database that lacks them;
- at least one ``active`` version is runnable, whenever any exists. A roster the
  build cannot run means every consumed bar is dropped while the worker reports
  itself healthy — the same failure ``main.py`` refuses to start with, arriving
  after the start (risk-engine-guardian, S2 review, MUST-FIX 1(b));
- the decision consumer is alive: it iterated recently, or the stream itself has
  published nothing since it last did (a quiet market is not a stuck worker);
- the outbox is not lagging: an event queued but unpublished for longer than
  ``outbox_lag_alert_s`` means the Lab's stream no longer reflects the database.

Each check is registered under its own ``__name__`` so the ``/ready`` payload
names what failed instead of returning an anonymous ``false``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_strategy_worker.catalogue import load_version_roster

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.consumer import ConsumerHealth
    from hunter_strategy_worker.outbox import OutboxHealth

logger = get_logger(__name__)

_REQUIRED_OBJECTS = ("shadow_episodes", "shadow_outbox")
_REQUIRED_COLUMN = ("signal_outcomes", "tracking_state")

__all__ = ["migration_present", "newest_stream_entry_at", "readiness_checks"]


async def migration_present(factory: async_sessionmaker[AsyncSession]) -> bool:
    """Whether ``0002_shadow_lab`` has been applied to this database."""
    async with role_session(factory, db_role="hunter_worker") as session:
        return await _objects_exist(session)


async def _objects_exist(session: AsyncSession) -> bool:
    for table in _REQUIRED_OBJECTS:
        found = await session.scalar(text("SELECT to_regclass(:name)"), {"name": table})
        if found is None:
            logger.warning("shadow_migration_missing", table=table)
            return False
    column = await session.scalar(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": _REQUIRED_COLUMN[0], "column": _REQUIRED_COLUMN[1]},
    )
    if column is None:
        logger.warning("shadow_migration_missing", column=".".join(_REQUIRED_COLUMN))
        return False
    return True


async def newest_stream_entry_at(redis: redis_asyncio.Redis, stream: str) -> datetime | None:
    """When the newest entry was added to ``stream``, from its id (``<ms>-<seq>``)."""
    try:
        entries: Any = await redis.xrevrange(stream, count=1)
    except Exception:
        logger.warning("shadow_stream_probe_failed", stream=stream)
        return None
    if not entries:
        return None
    raw = entries[0][0]
    text_id = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        milliseconds = int(text_id.split("-", 1)[0])
    except ValueError:  # pragma: no cover - Redis ids are always <ms>-<seq>
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


def readiness_checks(
    factory: async_sessionmaker[AsyncSession],
    config: ShadowConfig,
    consumer: ConsumerHealth,
    outbox: OutboxHealth,
    redis: redis_asyncio.Redis | None = None,
) -> list[Callable[[], Awaitable[bool]]]:
    """The four checks, each named for the ``/ready`` payload."""

    async def shadow_migration() -> bool:
        return await migration_present(factory)

    async def shadow_versions() -> bool:
        """False only when the catalogue has ``active`` rows and none is runnable.

        Astra would turn it red for *any* unrunnable active row, so that one
        healthy strategy cannot hide a dead one. Not taken: an operator-visible
        red for a stale row that nothing depends on would train the team to
        ignore the light. The per-reason gauge
        (``hunter_shadow_versions_unrunnable``) is what surfaces the partial
        case; the readiness gate is reserved for total silence. Divergence
        recorded in ``notes-S2.md`` §15.
        """
        async with role_session(factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
        return not roster.blind

    async def shadow_consumer() -> bool:
        """Alive, or simply with nothing to consume.

        The loop only gets an iteration when a message arrives, so a quiet
        stream and a stuck consumer look identical from the stamp alone — and a
        healthy worker on a quiet market would go red (Astra, S2 diff review,
        must-fix 7). So past the stall window we ask the stream itself: if
        nothing was published since the last iteration, there was nothing to
        do and the worker is ready.
        """
        last = consumer.last_iteration_at or consumer.started_at
        if last is None:
            return False
        if (utcnow() - last).total_seconds() < config.consumer_stall_s:
            return True
        if redis is None:
            return False
        newest = await newest_stream_entry_at(redis, Streams.MARKET_CANDLES_CLOSED)
        return newest is not None and newest <= last

    async def shadow_outbox() -> bool:
        return outbox.lag_s() < config.outbox_lag_alert_s

    return [shadow_migration, shadow_versions, shadow_consumer, shadow_outbox]
