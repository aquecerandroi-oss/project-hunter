"""One membership rule for "the markets whose 1m history can validate anything".

T3.88. The rule was written twice. ``hunter_strategy_worker.universe`` (T3.82,
Everton approved 2026-09-10) refuses a shadow bar whose market has less than
``SHADOW_UNIVERSE_MIN_HISTORY_DAYS`` days of 1-minute candles, because the funnel
that turns a live decision into evidence (90-day replay + replication) can only
ever run on such a market -- 16 of 200 on the VPS that day. The ``breadth_5m``
producer (T3.77) measured a *different* universe: all ~200 monitored perpetuals,
which is why a 90-day backfill of it would have been ``insufficient_coverage`` on
87 of 91 days and EXP-0027 was prospective-only.

Two universes, one question ("which markets can this experiment ever be about"),
so one rule -- here, in the package both workers already depend on. The scanner
must not import the strategy-worker's package (nothing does; they share only
``hunter_core``/``hunter_indicators``), and a rule stated in two places is a rule
that drifts the first time one of them is tuned.

**The rule, in full.** A market is a *candidate* when it is monitored
(``markets.is_monitored``), its type is ``perpetual`` and its status is
``active``; a candidate is *eligible* when the oldest **final** 1-minute candle
on record for it opened at or before ``as_of - min_history_days days``.

Three clauses worth naming, because each one was a decision:

- ``is_final`` only. The minute still printing is not history.
- ``status = 'active'``. A suspended-but-monitored symbol prints no candles, so
  keeping it would only ever lower a coverage ratio, and the funnel could not
  replay it either. T3.82's query did not carry this clause and T3.77's did; this
  module keeps the stricter of the two, which means the shadow universe's
  ``universe_total`` may now be a hair smaller than it was -- declared here
  rather than discovered later (``.claude/state/notes-T3.88.md``).
- ``<=``, not ``<``: a market whose oldest candle opened *exactly*
  ``min_history_days`` days before ``as_of`` qualifies. The inclusive convention
  T3.82 chose, kept byte for byte.

**What this is not.** Not an eligibility rule on versions (no ``code_ref``, no
derivation) and not a risk limit. It answers "which markets", and the *number* of
days comes from the caller: an environment knob for the shadow dispatch gate
(``SHADOW_UNIVERSE_MIN_HISTORY_DAYS``, which an operator may set to ``0`` to
disable that gate) and a frozen constant of the series version for
``breadth_v2`` (:mod:`hunter_indicators.breadth.spec`). That asymmetry is
deliberate: turning the operational knob must never silently redefine a
persisted series.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

MarketKey = tuple[str, str]
"""``(exchange_code, symbol)`` -- the identity the shadow path keys members by."""

__all__ = [
    "HistoryUniverse",
    "MarketKey",
    "UniverseMember",
    "has_min_history",
    "load_history_universe",
]


@dataclass(frozen=True, slots=True)
class UniverseMember:
    """One candidate market and the one fact membership turns on."""

    market_id: uuid.UUID
    exchange: str
    symbol: str
    first_candle_open_time: datetime | None
    """``min(candles.open_time)`` over final 1m candles; ``None`` when the market
    has no final 1m candle at all (never eligible, whatever the window)."""

    @property
    def key(self) -> MarketKey:
        return (self.exchange, self.symbol)


def has_min_history(
    first_candle_open_time: datetime | None, *, as_of: datetime, min_history_days: int
) -> bool:
    """The boundary check, pure and unit-testable without a database.

    ``min_history_days = 0`` admits anything with any history at all -- the
    arithmetic of "no window", which is what the shadow gate's "disabled" value
    means at the one place it is still evaluated.
    """
    if first_candle_open_time is None:
        return False
    return first_candle_open_time <= as_of - timedelta(days=min_history_days)


@dataclass(frozen=True, slots=True)
class HistoryUniverse:
    """One load of the rule: every candidate, and which of them are eligible.

    ``members`` is ordered by ``(exchange, symbol)`` so that every consumer --
    the breadth producer's id list, a heartbeat count, a log line -- reads the
    same order for the same database state, and a diff of two loads is a diff of
    membership rather than of row order.
    """

    as_of: datetime
    min_history_days: int
    members: tuple[UniverseMember, ...]

    @property
    def eligible(self) -> tuple[UniverseMember, ...]:
        return tuple(
            member
            for member in self.members
            if has_min_history(
                member.first_candle_open_time,
                as_of=self.as_of,
                min_history_days=self.min_history_days,
            )
        )

    @property
    def eligible_ids(self) -> tuple[uuid.UUID, ...]:
        """The market ids the ``breadth_5m`` producer folds over."""
        return tuple(member.market_id for member in self.eligible)

    @property
    def eligible_keys(self) -> frozenset[MarketKey]:
        return frozenset(member.key for member in self.eligible)

    @property
    def candidate_keys(self) -> frozenset[MarketKey]:
        """Every candidate considered -- the denominator of "16 of 200"."""
        return frozenset(member.key for member in self.members)


async def load_history_universe(
    session: AsyncSession,
    *,
    min_history_days: int,
    exchange: str | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> HistoryUniverse:
    """One query: the candidates of ``exchange`` (or of every venue) and, for
    each, the open time of its oldest final 1m candle.

    A plain ``GROUP BY``/``MIN`` over a ``LEFT JOIN``, not a per-market
    ``LATERAL ... LIMIT 1`` skip-scan: ~200 rows, read at most once an hour by
    the shadow cache and once per pass by the breadth producer. The tradeoff is
    named rather than silently accepted (T3.82's own words, kept).

    ``clock`` is the ``as_of`` seam. The caller decides what instant membership
    is asked about -- the cache's load time for the shadow gate, the fold's cut
    for a breadth backfill -- and nothing here reads a clock the caller did not
    hand it.
    """
    as_of = clock()
    conditions = [
        Market.market_type == MarketType.PERPETUAL,
        Market.is_monitored.is_(True),
        Market.status == MarketStatus.ACTIVE,
    ]
    if exchange is not None:
        conditions.append(Exchange.code == exchange)
    rows = (
        await session.execute(
            select(
                Market.id.label("market_id"),
                Exchange.code.label("exchange"),
                Market.symbol.label("symbol"),
                func.min(Candle.open_time).label("first_candle_open_time"),
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
            .where(*conditions)
            .group_by(Market.id, Exchange.code, Market.symbol)
            .order_by(Exchange.code, Market.symbol)
        )
    ).all()
    return HistoryUniverse(
        as_of=as_of,
        min_history_days=min_history_days,
        members=tuple(
            UniverseMember(
                market_id=row.market_id,
                exchange=row.exchange,
                symbol=row.symbol,
                first_candle_open_time=row.first_candle_open_time,
            )
            for row in rows
        ),
    )
