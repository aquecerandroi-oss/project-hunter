"""The shadow universe: markets whose 1m history can ever validate (T3.82).

**The decision.** Everton approved 2026-09-10: the Shadow Lab evaluates every
active version, on every 15-min boundary, against the *whole* monitored
perpetual universe (~200 symbols) -- but the funnel that turns a live decision
into anything usable (90-day replay + replication, ``docs/plans/
REPLICATION.md``) can only ever run on a market with 90 days of ``candles_1m``.
Measured on the VPS the same day: 16 of 200 qualify. The other 184 never pass
the funnel no matter how many decisions accumulate for them -- their live
evaluations are unvalidatable research cost, not a smaller population of the
same experiment. T3.74g §5 (iii) had already named this as an open question
("the cost is linear in the universe, and the versions decide on ~200 markets
when only 16 have 90 days of history"); this module is the answer.

**What this is not.** Not a version-eligibility rule (no ``code_ref`` change,
no version derivation -- ``docs/plans/SHADOW-LAB.md`` §1's catalogue is
untouched) and not a risk limit (``packages/risk-core`` never sees this). It is
a worker-level universe policy, checked once per bar, identically for every
version -- ``research_only`` and ``paper`` purposes alike. The paper wallet's
own executable universe (``execution-worker``/the admission bridge) is a
separate concept and is not read or written here.

**The rule.** A market is in the shadow universe when it is monitored
(``markets.is_monitored``, the T3.73 perpetual-only door already narrows the
venue before this ever runs) and the oldest **final** 1m candle on record for
it closes far enough in the past --
``min(candles.open_time) <= as_of - SHADOW_UNIVERSE_MIN_HISTORY_DAYS days``.
``as_of`` is this cache's own load time (``utcnow()`` by default), not the
bar's own ``bar_close`` -- a deliberate approximation: the cache is refreshed
at most once an hour (:data:`CACHE_TTL_S`), so within one refresh window every
bar checked against it is at most an hour younger than the instant the
snapshot was taken, and ``candles_1m``'s own 90-day retention (DATABASE.md
§1.3) means a market that has ever crossed the line stays past it (the
retention job never lets the oldest surviving row get older than the window,
so once true this predicate does not flip back to false by itself). A market
that crosses the line mid-hour joins within the hour, never instantly -- named
in the brief as an accepted looseness, not a bug.

**Why in-process, not Redis (the brief asks to say which).** Membership does
not need to agree *across* shards or processes the way, say, a slot lock does
-- two shards computing "16 of 200" a few seconds apart from two independent
queries is exactly as correct as one shared cache would be, and this check
sits on the same hot per-bar path :mod:`.shard`'s ``not_my_shard`` refusal
already occupies, so adding a Redis round trip to every bar to consult a value
that changes at most once an hour would trade network latency for no
consistency gain. A single query, refreshed at most once per ``CACHE_TTL_S``
per process, the same shape :class:`hunter_strategy_worker.versions.
VersionCache` already uses for the active-version roster.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker.shard import owns_market

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

CACHE_TTL_S = 3600.0
"""One hour, fixed (the brief's own number). Not an environment knob: unlike
``SHADOW_UNIVERSE_MIN_HISTORY_DAYS`` this is an implementation detail of the
cache, not a parameter of the experiment."""

MarketKey = tuple[str, str]
"""``(exchange_code, symbol)`` -- the same identity :func:`.dispatch.market_key`
uses, minus the market type (this module only ever looks at perpetuals)."""

__all__ = [
    "CACHE_TTL_S",
    "MarketKey",
    "UniverseCache",
    "UniverseSnapshot",
    "in_universe",
    "load_universe_snapshot",
    "shard_counts",
]


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    """One load of the shadow universe."""

    eligible: frozenset[MarketKey]
    """Monitored perpetual markets with >= ``min_history_days`` of 1m history."""

    candidates: frozenset[MarketKey]
    """Every monitored perpetual market considered, eligible or not -- the
    denominator of "16 of 200"."""

    min_history_days: int
    loaded_at: datetime


def _is_eligible(min_open_time: datetime | None, *, as_of: datetime, min_history_days: int) -> bool:
    """Pure boundary check, unit-testable without a database.

    ``min_history_days`` counts whole days: a market whose oldest final candle
    opened *exactly* ``min_history_days`` days before ``as_of`` qualifies
    (``<=``, not ``<``) -- the same inclusive convention
    ``ShadowConfig.eligibility_max_lag_s`` and ``late_delay_backlog_max_s``
    already use for their own boundaries elsewhere in this package.
    """
    if min_open_time is None:
        return False
    return min_open_time <= as_of - timedelta(days=min_history_days)


async def load_universe_snapshot(
    session: AsyncSession, *, min_history_days: int, clock: Callable[[], datetime] = utcnow
) -> UniverseSnapshot:
    """One query: every monitored perpetual market and the open time of its
    oldest final 1m candle (``NULL`` when it has none yet).

    A plain ``GROUP BY``/``MIN`` over a ``LEFT JOIN`` -- not the per-market
    ``LATERAL ... ORDER BY open_time LIMIT 1`` an index-per-group skip-scan
    would use. ~200 monitored perpetuals, once an hour, is not the budget this
    module needs to protect (that fight is T3.74g's, on the per-*bar* path);
    kept simple on purpose, with the tradeoff named rather than silently
    accepted.
    """
    as_of = clock()
    rows = (
        await session.execute(
            select(
                Exchange.code.label("exchange"),
                Market.symbol.label("symbol"),
                func.min(Candle.open_time).label("min_open_time"),
            )
            .select_from(Market)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .outerjoin(
                Candle,
                and_(
                    Candle.market_id == Market.id,
                    Candle.timeframe == Timeframe.M1,
                    Candle.is_final.is_(True),
                ),
            )
            .where(
                Market.market_type == MarketType.PERPETUAL,
                Market.is_monitored.is_(True),
            )
            .group_by(Exchange.code, Market.symbol)
        )
    ).all()
    candidates: set[MarketKey] = set()
    eligible: set[MarketKey] = set()
    for row in rows:
        key = (row.exchange, row.symbol)
        candidates.add(key)
        if _is_eligible(row.min_open_time, as_of=as_of, min_history_days=min_history_days):
            eligible.add(key)
    return UniverseSnapshot(
        eligible=frozenset(eligible),
        candidates=frozenset(candidates),
        min_history_days=min_history_days,
        loaded_at=as_of,
    )


async def _load_via_session(
    factory: async_sessionmaker[AsyncSession],
    *,
    min_history_days: int,
    clock: Callable[[], datetime],
) -> UniverseSnapshot:
    """:class:`UniverseCache`'s default loader: open the one session
    :func:`load_universe_snapshot` needs. Kept separate so a test can inject
    a fake loader that never touches ``role_session``/the database at all.
    """
    from hunter_core.db.session import role_session

    async with role_session(factory, db_role="hunter_worker") as session:
        return await load_universe_snapshot(session, min_history_days=min_history_days, clock=clock)


def in_universe(snapshot: UniverseSnapshot, *, exchange: str, symbol: str) -> bool:
    """Whether ``exchange:symbol`` is in the shadow universe of ``snapshot``."""
    return (exchange, symbol) in snapshot.eligible


def shard_counts(
    snapshot: UniverseSnapshot, *, shard_index: int, shard_total: int
) -> tuple[int, int]:
    """``(eligible, total)`` restricted to the markets this shard owns --
    the heartbeat's ``universe_size``/``universe_total`` fields. Sharding is
    by plain symbol (:mod:`.shard`), so this filters on the second element of
    each key.
    """
    eligible = sum(
        1
        for _exchange, symbol in snapshot.eligible
        if owns_market(symbol, shard_index, shard_total)
    )
    total = sum(
        1
        for _exchange, symbol in snapshot.candidates
        if owns_market(symbol, shard_index, shard_total)
    )
    return eligible, total


class UniverseCache:
    """``load_universe_snapshot`` with a TTL and a last-known-good fallback.

    Mirrors :class:`hunter_strategy_worker.versions.VersionCache`: reloaded at
    most once per :data:`CACHE_TTL_S`, and a failed reload logs a warning and
    keeps serving the last snapshot rather than raising into the hot per-bar
    path (:mod:`.consumer`) -- the same fail-open-on-staleness the brief
    accepts by construction ("a market crossing the line joins within an
    hour"). The TTL clock still advances on a failed reload, so an outage
    retries once per hour, not once per bar.
    """

    def __init__(
        self,
        min_history_days: int,
        *,
        ttl_s: float = CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
        loader: Callable[..., Awaitable[UniverseSnapshot]] = _load_via_session,
    ) -> None:
        self._min_history_days = min_history_days
        self._ttl_s = ttl_s
        self._clock = clock
        self._loader = loader
        self._loaded_at: float | None = None
        self._snapshot = UniverseSnapshot(
            eligible=frozenset(),
            candidates=frozenset(),
            min_history_days=min_history_days,
            loaded_at=utcnow(),
        )
        self._counted_snapshot: UniverseSnapshot | None = None
        self._counts: dict[tuple[int, int], tuple[int, int]] = {}

    async def check(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        exchange: str,
        symbol: str,
        shard_index: int,
        shard_total: int,
        clock: Callable[[], datetime] = utcnow,
    ) -> tuple[bool, int | None, int | None]:
        """``(admitted, shard_size, shard_total_candidates)`` for one bar --
        the whole gate :mod:`.consumer` needs, in one call. The last two are
        ``None`` only before the very first call this process ever makes (no
        snapshot loaded yet); every call after that reports the shard counts
        of *some* snapshot, stale or fresh, never a blank read once a real one
        exists. Counts are recomputed only when :meth:`get` actually returned
        a new snapshot object -- ``(shard_index, shard_total)`` is constant
        for a process's whole lifetime, so the memo never grows past one
        entry in practice. ``clock`` is only consulted on an actual reload
        (module docstring's ``as_of``) -- the same test seam
        :func:`hunter_strategy_worker.consumer.run_consumer` already threads
        through for everything else on this path.
        """
        snapshot = await self.get(factory, clock=clock)
        if snapshot is not self._counted_snapshot:
            self._counted_snapshot = snapshot
            self._counts = {}
        key = (shard_index, shard_total)
        counts = self._counts.get(key)
        if counts is None:
            counts = shard_counts(snapshot, shard_index=shard_index, shard_total=shard_total)
            self._counts[key] = counts
        return in_universe(snapshot, exchange=exchange, symbol=symbol), counts[0], counts[1]

    async def get(
        self, factory: async_sessionmaker[AsyncSession], *, clock: Callable[[], datetime] = utcnow
    ) -> UniverseSnapshot:
        now = self._clock()
        if self._loaded_at is not None and now - self._loaded_at < self._ttl_s:
            return self._snapshot
        try:
            snapshot = await self._loader(
                factory, min_history_days=self._min_history_days, clock=clock
            )
        except Exception:
            logger.warning("shadow_universe_reload_failed")
            self._loaded_at = now
            return self._snapshot
        if snapshot.eligible != self._snapshot.eligible:
            logger.info(
                "shadow_universe_membership",
                eligible=len(snapshot.eligible),
                candidates=len(snapshot.candidates),
                min_history_days=self._min_history_days,
            )
        self._snapshot, self._loaded_at = snapshot, now
        return snapshot
