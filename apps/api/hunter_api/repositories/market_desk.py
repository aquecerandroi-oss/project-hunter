"""Reading the ``spot/1`` desk's trail on one Binance market — ``0057_spot_desk``
(T4.82, design ``docs/design/tela-confluencia-mercado.md`` §7a item 3).

Until T4.82 nothing but ``services/meme-executor`` ever read these three
tables. They are **global and RLS-free** (``hunter_core/db/models/spot_desk.py``:
an order signed against a Jupiter route belongs to no organization), exactly
like ``meme_live_*``, so the segment that decides who may look is the router's
gate, not a predicate here — see ``routers/market_desk.py``. Every query below
is read-only; ``hunter_app`` holds ``SELECT`` on ``spot_desk_markets``/
``spot_orders`` and nothing else on them.

**The one query worth reading twice is the positions one.** It is an interval
intersection, not a point query: a position opened at 10:00 and still open is
part of what was true at 11:45, and a screen that asked "which rows have
``entry_at`` inside my fifteen minutes" would answer that the desk held
nothing. :func:`position_intersects_window` is the same predicate in Python,
so the rule can be tested case by case without a database and cannot drift
from the SQL without a red test.

The statement builders are module-level functions rather than methods so that
their predicates can be asserted by compiling them
(``tests/unit/test_market_desk_queries.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Select, select

from hunter_api.repositories.bounded import BoundedRows, bounded
from hunter_core.db.models.spot_desk import SpotDeskMarket, SpotOrder, SpotPosition

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "DESK_EXCHANGE",
    "MarketDeskRepository",
    "build_desk_market_statement",
    "build_desk_orders_statement",
    "build_desk_positions_statement",
    "position_intersects_window",
]


DESK_EXCHANGE = "binance"
"""The only venue ``spot_desk_markets`` is keyed on (``binance_symbol``). The
router refuses to look up a desk trail for any other exchange rather than
matching on the bare symbol: ``bybit``'s ``ZECUSDT`` is a different listing,
and answering it with the Binance desk's orders would be an invented trail."""


def position_intersects_window(
    *, entry_at: datetime, exit_at: datetime | None, since: datetime, until: datetime
) -> bool:
    """Whether a position's life overlaps the half-open window ``[since, until)``.

    The position occupies ``[entry_at, exit_at]``, or ``[entry_at, +inf)`` while
    ``exit_at`` is ``NULL``. Two intervals overlap when each starts before the
    other ends, which here is ``entry_at < until AND exit_at >= since``.

    The two boundaries are deliberate and each has a failure it prevents:

    - ``entry_at < until`` (not ``<=``): a position opened exactly at ``until``
      belongs to the *next* window. With ``<=`` it would appear in two adjacent
      windows and the screen would show the same entry twice.
    - ``exit_at >= since`` (not ``>``): a position closed exactly at ``since``
      was still alive at that instant, which is inside the window.

    The Python twin of the SQL in :func:`build_desk_positions_statement`.
    """
    return entry_at < until and (exit_at is None or exit_at >= since)


def build_desk_positions_statement(
    symbol: str, *, since: datetime, until: datetime, limit: int
) -> Select[tuple[SpotPosition]]:
    """Every ``spot/1`` position whose life overlaps ``[since, until)``.

    The open leg is reached through ``exit_at IS NULL``, never through
    ``status = 'open'``: ``status`` and ``exit_at`` are two columns the
    executor writes, and reading the one that *is* the exit keeps this query
    right even mid-write. (The table's own CHECK keeps the pair honest; this
    read does not need to trust it.)

    ``LIMIT`` is ``limit + 1``: the extra row is the probe that tells the
    caller the cap swallowed something (:class:`BoundedRows`).
    """
    return (
        select(SpotPosition)
        .where(
            SpotPosition.market_symbol == symbol,
            SpotPosition.entry_at < until,
            (SpotPosition.exit_at.is_(None)) | (SpotPosition.exit_at >= since),
        )
        .order_by(SpotPosition.entry_at.desc(), SpotPosition.id.desc())
        .limit(limit + 1)
    )


def build_desk_orders_statement(
    symbol: str, *, since: datetime, until: datetime, limit: int
) -> Select[tuple[SpotOrder]]:
    """Every attempt of the lane on ``symbol`` received inside ``[since, until)``.

    An order is an instant, not an interval, so this one is a plain cut on
    ``received_at``. No status filter: the ``refused`` rows are the point —
    "olhamos e recusamos" (design §4A) is the most valuable line of the screen,
    and a read that treated a refusal as noise would delete it.

    Newest first, like ``MemeLiveRepository.list_orders``, so that if the row
    cap ever binds it is the oldest attempt that is dropped, not the last one.

    ``LIMIT`` is ``limit + 1``, for the same reason as the positions read.
    """
    return (
        select(SpotOrder)
        .where(
            SpotOrder.market_symbol == symbol,
            SpotOrder.received_at >= since,
            SpotOrder.received_at < until,
        )
        .order_by(SpotOrder.received_at.desc(), SpotOrder.id.desc())
        .limit(limit + 1)
    )


def build_desk_market_statement(symbol: str) -> Select[tuple[SpotDeskMarket]]:
    """The executable map row for ``symbol``, or nothing — "a mesa não opera
    este mercado" is an answer the screen has a text for (design §5)."""
    return select(SpotDeskMarket).where(SpotDeskMarket.binance_symbol == symbol).limit(1)


class MarketDeskRepository:
    """Global, read-only access to the ``spot/1`` ledger for one symbol."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_desk_market(self, symbol: str) -> SpotDeskMarket | None:
        return (
            (await self.session.execute(build_desk_market_statement(symbol)))
            .scalars()
            .one_or_none()
        )

    async def list_orders(
        self, symbol: str, *, since: datetime, until: datetime, limit: int
    ) -> BoundedRows[SpotOrder]:
        statement = build_desk_orders_statement(symbol, since=since, until=until, limit=limit)
        return await bounded(self.session, statement, limit)

    async def list_positions(
        self, symbol: str, *, since: datetime, until: datetime, limit: int
    ) -> BoundedRows[SpotPosition]:
        statement = build_desk_positions_statement(symbol, since=since, until=until, limit=limit)
        return await bounded(self.session, statement, limit)
