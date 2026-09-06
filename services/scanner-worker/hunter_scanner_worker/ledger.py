"""What "already bootstrapped" means, and why one source cannot answer it alone.

A market is skipped only when *both* sources agree: the archive holds bootstrap
revisions recent enough (``settings.max_age_h``) **and** the ledger says that run
finished against the same feature roster. Neither alone is sufficient, and each
covers the other's blind spot:

- the archive cannot distinguish "wrote 288 buckets because that is all there is"
  from "wrote 288 buckets and died before the rest", and ``max(window_end)`` per
  market would skip a market for a day after a two-hour partial run — the exact
  scenario Astra raised (T2.5b design review, must-fix 1);
- the ledger is in Redis, so losing it must never *authorise* a skip. It does not:
  a missing record means the market is bootstrapped again, which is wasted CPU
  and not a wrong number (``ON CONFLICT`` on the fingerprint makes the rewrite a
  no-op). The declared cost of a flushed Redis is one full bootstrap pass.

A market that ends incomplete (holes in its history, a backfill asked for) is
retried with exponential backoff instead of every cycle: the repair it is waiting
for is somebody else's work, and asking again before it lands only burns the
replay budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import orjson
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_indicators.baselines.bootstrap import BOOTSTRAP_ALGO_VERSION, bootstrap_feature_keys
from hunter_indicators.features import DEFAULT_REGISTRY
from hunter_scanner_worker.bootstrap import BootstrapSettings

if TYPE_CHECKING:
    from collections.abc import Sequence

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_scanner_worker.bootstrap import BootstrapOutcome, BootstrapWindow
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

LEDGER_TTL_S = 30 * 24 * 3600
DB_ROLE = "hunter_worker"

_ARCHIVED = text(
    """
    SELECT market_id, max(window_end) AS newest
      FROM feature_baselines
     WHERE source = 'bootstrap'
       AND market_id = ANY(:ids)
     GROUP BY market_id
    """
)

__all__ = [
    "BootstrapLedger",
    "LedgerEntry",
    "pending_markets",
    "roster_id",
]


def roster_id(settings: BootstrapSettings) -> str:
    """Identity of *what* a bootstrap produces: features, versions, window, algo.

    A feature version bump or a different window makes the previous run's
    revisions describe another population, so the ledger entry that recorded it
    must stop authorising a skip (Astra, must-fix 1, second scenario).
    """
    versions = {definition.key: definition.version for definition in DEFAULT_REGISTRY.definitions()}
    payload = [[key, versions.get(key, 0)] for key in sorted(bootstrap_feature_keys())]
    digest = sha256(
        orjson.dumps([payload, settings.window_days, BOOTSTRAP_ALGO_VERSION])
    ).hexdigest()
    return digest[:16]


@dataclass(slots=True)
class LedgerEntry:
    """One market's last bootstrap attempt, as remembered in Redis."""

    window_end: datetime
    roster: str
    complete: bool
    buckets: int = 0
    attempts: int = 0
    retry_at: datetime | None = None
    reason: str | None = None

    def as_wire(self) -> dict[str, Any]:
        return {
            "window_end": self.window_end.isoformat(),
            "roster": self.roster,
            "complete": self.complete,
            "buckets": self.buckets,
            "attempts": self.attempts,
            "retry_at": None if self.retry_at is None else self.retry_at.isoformat(),
            "reason": self.reason,
        }

    @classmethod
    def from_wire(cls, wire: dict[str, Any]) -> LedgerEntry:
        retry = wire.get("retry_at")
        return cls(
            window_end=ensure_utc(datetime.fromisoformat(str(wire["window_end"]))),
            roster=str(wire.get("roster") or ""),
            complete=bool(wire.get("complete")),
            buckets=int(wire.get("buckets") or 0),
            attempts=int(wire.get("attempts") or 0),
            retry_at=None if not retry else ensure_utc(datetime.fromisoformat(str(retry))),
            reason=wire.get("reason"),
        )


class BootstrapLedger:
    """What was attempted, per market. Never the proof that it was written."""

    __slots__ = ("key",)

    def __init__(self, exchange: str) -> None:
        self.key = f"scan:bootstrap:{exchange}"

    async def read(self, redis: redis_asyncio.Redis) -> dict[UUID, LedgerEntry]:
        raw: Any = await cast(Any, redis).hgetall(self.key)
        out: dict[UUID, LedgerEntry] = {}
        for field_name, value in dict(raw or {}).items():
            name = field_name.decode() if isinstance(field_name, bytes) else str(field_name)
            try:
                out[UUID(name)] = LedgerEntry.from_wire(orjson.loads(value))
            except Exception:
                logger.warning("scanner_bootstrap_ledger_unreadable", market=name)
        return out

    async def record(
        self,
        redis: redis_asyncio.Redis,
        outcome: BootstrapOutcome,
        *,
        settings: BootstrapSettings | None = None,
        previous: LedgerEntry | None = None,
        now: datetime | None = None,
    ) -> LedgerEntry:
        """Write the attempt, with the backoff an incomplete one earns."""
        moment = now or utcnow()
        config = settings or BootstrapSettings()
        attempts = 0 if outcome.complete else (previous.attempts if previous else 0) + 1
        retry_at = None
        if not outcome.complete:
            delay = min(config.retry_s * (2 ** (attempts - 1)), config.max_retry_s)
            retry_at = moment + timedelta(seconds=delay)
        entry = LedgerEntry(
            window_end=outcome.window.end,
            roster=roster_id(config),
            complete=outcome.complete,
            buckets=outcome.buckets,
            attempts=attempts,
            retry_at=retry_at,
            reason=outcome.reason,
        )
        await cast(Any, redis).hset(
            self.key, str(outcome.ref.market_id), orjson.dumps(entry.as_wire())
        )
        await redis.expire(self.key, LEDGER_TTL_S)
        return entry


async def _archived(session: AsyncSession, market_ids: Sequence[UUID]) -> dict[UUID, datetime]:
    if not market_ids:
        return {}
    result = await session.execute(_ARCHIVED, {"ids": [str(item) for item in market_ids]})
    return {UUID(str(row[0])): ensure_utc(row[1]) for row in result if row[1] is not None}


async def pending_markets(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    refs: Sequence[MarketRef],
    *,
    window: BootstrapWindow,
    settings: BootstrapSettings,
    now: datetime | None = None,
    ledger: BootstrapLedger | None = None,
) -> list[MarketRef]:
    """The markets whose bootstrap still has to run, oldest evidence first."""
    if not refs:
        return []
    moment = now or utcnow()
    book = ledger or BootstrapLedger(refs[0].exchange)
    entries = await book.read(redis)
    async with role_session(factory, db_role=DB_ROLE) as session:
        archived = await _archived(session, [ref.market_id for ref in refs])
    current = roster_id(settings)
    floor = window.end - timedelta(hours=settings.max_age_h)
    pending: list[MarketRef] = []
    for ref in refs:
        entry = entries.get(ref.market_id)
        newest = archived.get(ref.market_id)
        if (
            newest is not None
            and newest >= floor
            and entry is not None
            and entry.complete
            and entry.roster == current
        ):
            continue
        if (
            entry is not None
            and entry.retry_at is not None
            and entry.roster == current
            and moment < entry.retry_at
        ):
            # Incomplete and waiting on a repair somebody else owns. The roster
            # has to match: a seven-day backoff earned by v1 must not dismiss a
            # market whose v2 features were never computed at all (Astra, T2.5b
            # diff review, must-fix 5).
            continue
        pending.append(ref)
    return pending
