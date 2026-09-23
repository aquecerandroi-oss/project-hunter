"""Reading ``market_events`` — the news lane of the confluence screen (T4.82,
revision ``0059_market_events``, design §7a item 4).

Global, no-RLS table (``hunter_core/db/models/market_events.py``): a headline
belongs to the world, not to an organization. ``hunter_app`` holds ``SELECT``
on it and nothing else — the screen is a pure read (design §6, "Sem POST"), and
the only writer today is the audited operator script
``infra/scripts/market_event.py``.

The statement builder is a module-level function so its predicates can be
asserted by compiling it (``tests/unit/test_market_events_query.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Select, func, select

from hunter_api.repositories.bounded import BoundedRows, bounded
from hunter_core.db.models.market_events import MarketEvent

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["EVENT_INSTANT", "MarketEventsRepository", "build_events_statement"]

EVENT_INSTANT = func.coalesce(MarketEvent.published_at, MarketEvent.observed_at)
"""When the row sits on the timeline.

``published_at`` is nullable — a source that does not say when it published is
a real case (§3, overlay 4: such an item goes to the list, never to the chart)
— and ``observed_at`` is ``NOT NULL``, so this expression can never be null. A
window cut on ``published_at`` alone would silently drop every item whose
publication instant is unknown; an ordering on it alone would bunch them all at
one end under ``NULLS LAST``.

The boundary this accepts, named rather than hidden: an item published long
before the window and only ingested inside it does **not** appear. Its
publication is what sits on the market's timeline; our late reading of it is
not an event of that market. §4C's case — published just before the cursor,
ingested after it — is inside the window by ``published_at`` and does appear,
which is the case the design asked for.
"""


def build_events_statement(
    symbol: str, *, exchange: str, since: datetime, until: datetime, limit: int
) -> Select[tuple[MarketEvent]]:
    """Every headline about ``symbol`` whose instant falls in ``[since, until)``.

    ``exchange IS NULL OR exchange = :exchange``: a venue notice names its
    venue, a macro headline names none and belongs to every venue's screen for
    that symbol. Equality alone would drop the second kind, which is most of
    them.

    No filter on ``confidence``: a rumour is a fact about what the shift heard.
    The screen renders confidence as a shape and never as an absence.

    ``LIMIT`` is ``limit + 1``: the extra row is the probe behind
    ``MarketEventsOut.truncated`` (Astra's review of T4.82 — a cap that drops
    rows without saying so lets the screen print "nenhuma notícia" over a page
    that merely ran out of room).
    """
    return (
        select(MarketEvent)
        .where(
            MarketEvent.symbol == symbol,
            (MarketEvent.exchange.is_(None)) | (MarketEvent.exchange == exchange),
            EVENT_INSTANT >= since,
            EVENT_INSTANT < until,
        )
        .order_by(EVENT_INSTANT.desc(), MarketEvent.id.desc())
        .limit(limit + 1)
    )


class MarketEventsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_events(
        self, symbol: str, *, exchange: str, since: datetime, until: datetime, limit: int
    ) -> BoundedRows[MarketEvent]:
        statement = build_events_statement(
            symbol, exchange=exchange, since=since, until=until, limit=limit
        )
        return await bounded(self.session, statement, limit)
