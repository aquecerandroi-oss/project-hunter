"""``market_id`` <-> ``exchange/symbol``, and who is in the universe.

The engines are keyed two different ways and neither is wrong: features and the
hot state are addressed by ``exchange/symbol`` (that is what a stream message and
a Redis key carry), while baselines, anomalies and opportunities are keyed by
``markets.id``. Something has to hold both, and it has to be the same something
that decides which markets exist at all — otherwise a symbol that was delisted
keeps being evaluated against a ``market_id`` nobody would write.

The universe is ``markets.is_monitored``, exactly as the strategy-worker reads it
(``docs/PIPELINE.md`` §6b: a tracking hold widens *collection*, never
eligibility). ``market.universe.changed`` only tells this registry to refresh
sooner; the database stays the source of truth, because the event carries symbols
and the scanner needs ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

__all__ = ["MarketRef", "MarketRegistry", "UniverseDiff"]


@dataclass(frozen=True, slots=True)
class MarketRef:
    """One monitored market, in both spellings."""

    market_id: UUID
    exchange: str
    symbol: str


@dataclass(frozen=True, slots=True)
class UniverseDiff:
    """What one refresh changed. Empty means the universe stood still."""

    added: tuple[MarketRef, ...] = ()
    removed: tuple[MarketRef, ...] = ()
    total: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


@dataclass
class MarketRegistry:
    """The monitored universe of one exchange, refreshed from Postgres."""

    exchange: str
    by_symbol: dict[str, MarketRef] = field(default_factory=dict[str, MarketRef])
    by_id: dict[UUID, MarketRef] = field(default_factory=dict[UUID, MarketRef])
    refreshed_at: datetime | None = None

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.by_symbol))

    @property
    def size(self) -> int:
        return len(self.by_symbol)

    def ref(self, symbol: str) -> MarketRef | None:
        return self.by_symbol.get(symbol)

    def ref_by_id(self, market_id: UUID) -> MarketRef | None:
        return self.by_id.get(market_id)

    def apply(self, refs: list[MarketRef], *, now: datetime | None = None) -> UniverseDiff:
        """Swap in a freshly read universe and report the difference."""
        fresh = {ref.symbol: ref for ref in refs}
        added = tuple(ref for symbol, ref in sorted(fresh.items()) if symbol not in self.by_symbol)
        removed = tuple(
            ref for symbol, ref in sorted(self.by_symbol.items()) if symbol not in fresh
        )
        self.by_symbol = fresh
        self.by_id = {ref.market_id: ref for ref in fresh.values()}
        self.refreshed_at = now or utcnow()
        return UniverseDiff(added=added, removed=removed, total=len(fresh))

    async def refresh(
        self, factory: async_sessionmaker[AsyncSession], *, limit: int
    ) -> UniverseDiff:
        """Re-read ``markets.is_monitored`` for this exchange."""
        async with role_session(factory, db_role="hunter_worker") as session:
            refs = await load_universe(session, self.exchange, limit=limit)
        diff = self.apply(refs)
        if diff.changed:
            logger.info(
                "scanner_universe_changed",
                added=[ref.symbol for ref in diff.added],
                removed=[ref.symbol for ref in diff.removed],
                total=diff.total,
            )
        return diff


async def load_universe(session: AsyncSession, exchange: str, *, limit: int) -> list[MarketRef]:
    """Every monitored perpetual of ``exchange``, ordered by symbol."""
    statement = (
        select(Market.id, Market.symbol)
        .join(Exchange, Exchange.id == Market.exchange_id)
        .where(
            Exchange.code == exchange,
            Market.is_monitored.is_(True),
            Market.market_type == MarketType.PERPETUAL,
        )
        .order_by(Market.symbol)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [MarketRef(market_id=row[0], exchange=exchange, symbol=row[1]) for row in rows]
