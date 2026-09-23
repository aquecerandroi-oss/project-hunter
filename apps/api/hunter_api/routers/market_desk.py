"""``/api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/{desk,events}`` — the
``spot/1`` trail and the news lane of the confluence screen (T4.82, design
``docs/design/tela-confluencia-mercado.md`` §7a items 3 and 4).

**Why these two live under ``/orgs/{org_id}`` while the rest of ``/markets``
does not.** ``spot_desk_markets``/``spot_orders``/``spot_positions`` (``0057``)
and ``market_events`` (``0059``) are global: no ``organization_id``, therefore
no RLS. Nothing in the row decides who may read it, so the whole authorisation
is this router's declared dependency. The design asked for them on the
principal-only ``/api/v1/markets`` prefix, whose gate is "authenticated" and
**not** "member of an organization" — weaker than the gate the equivalent meme
ledger sits behind, on data that is the record of what the desk did with real
money. Everton decided on 23/09/2026 that the gate wins and the path moves;
``require_org(OrganizationRole.VIEWER)`` + ``OrgSession`` below is byte for
byte ``routers/meme_live.py``'s, and ``tests/unit/test_market_desk_guard.py``
asserts the two agree.

``OrgSession`` sets ``app.current_org`` for the transaction as it does
everywhere else. It changes nothing about *these* tables — they carry no
policy to key on — but using the tenant session rather than a second, weaker
one is what keeps "a tenant route opens a tenant transaction" a rule with no
exceptions to remember.

**What this gate does and does not buy, stated exactly** (Astra's review of
T4.82 asked for this in writing, and the ``security-reviewer`` should read it
as the claim being made):

- a caller who is not an active member of the ``{org_id}`` in the path gets a
  404, and one below ``VIEWER`` gets a 403 — ``get_org_context``/
  ``require_org`` (``auth/rbac.py``);
- a ``VIEWER`` of organization **B**, calling B's own path, reads the **same
  global desk** a ``VIEWER`` of A reads. These rows have no
  ``organization_id``, so there is nothing to isolate them by, and no session
  setting can invent one.

That is the ``meme_live`` property, inherited deliberately — the product is
single-tenant in practice today. It is **not** privacy of Everton's desk from
a future second tenant: that would need an owner column on ``spot_*`` and a
policy, which is a schema decision, not a routing one. Copying ``meme_live``
proves the gate is not weaker; it does not prove isolation, and this docstring
should not be read as claiming it does.

**No market lookup.** Neither read joins ``markets``. The desk trail is keyed
on ``spot_desk_markets.binance_symbol`` and the news on
``market_events.symbol``, and a headline may legitimately exist before the pair
enters the monitored universe (design §9). A 404 derived from ``markets`` would
also have to pick a ``market_type``, and picking the wrong one would hide a
real trail. An unknown symbol therefore answers an empty trail, which is true,
and which the screen already has a sentence for (§5).

Both routes are ``GET`` and nothing here writes: design §6, "Sem POST".
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession
from hunter_api.repositories.market_desk import DESK_EXCHANGE, MarketDeskRepository
from hunter_api.repositories.market_events import MarketEventsRepository
from hunter_api.schemas.market_desk import DeskMarketOut, DeskOrderOut, DeskOut, DeskPositionOut
from hunter_api.schemas.market_events import MarketEventOut, MarketEventsOut
from hunter_api.time_window import UtcDatetime, resolve_window
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow

__all__ = [
    "DEFAULT_WINDOW",
    "MAX_DESK_ROWS",
    "MAX_EVENT_ROWS",
    "MAX_WINDOW",
    "router",
]

router = APIRouter(prefix="/api/v1/orgs/{org_id}/markets", tags=["markets"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
"""The ``meme_live`` gate, verbatim — see the module docstring and
``tests/unit/test_market_desk_guard.py``."""

Exchange = Annotated[str, Path(max_length=32)]
Symbol = Annotated[str, Path(max_length=32)]

DEFAULT_WINDOW = timedelta(hours=1)
"""What the caller gets without ``since``/``until``: the screen's second step
(±60 min around a cursor, design §4B), which contains the ±15 min default as
well, so one call serves both without the client having to ask twice."""

MAX_WINDOW = timedelta(days=7)
"""The widest window either read answers in one call. Generous on purpose —
these tables hold a handful of rows a day, and the screen legitimately asks for
a whole cycle (a position's horizon is 4 h) or for "ampliar para 24 h" (§5). A
week past that is a request for a report, not for a screen."""

MAX_DESK_ROWS = 500
MAX_EVENT_ROWS = 200
"""Row caps, the ``meme_live`` shape: the trail of one market over a week is a
few dozen rows, so these never bind in practice. When one does it is the
**oldest** row that is dropped (both reads are ordered newest first), and the
payload says so — ``orders_truncated``/``positions_truncated``/``truncated``.
Astra's review of T4.82 is why the flags exist: the oldest row is precisely
the long-open position the screen most needs, so a silent cap would let it
print "nada estava vigente" over a page that merely ran out of room."""


@router.get(
    "/{exchange}/{symbol}/desk",
    response_model=DeskOut,
    summary="Read the spot/1 desk trail for one market",
)
async def get_market_desk(
    exchange: Exchange,
    symbol: Symbol,
    session: OrgSession,
    context: ViewerOrg,
    since: UtcDatetime | None = None,
    until: UtcDatetime | None = None,
) -> DeskOut:
    """Orders and positions of the ``spot/1`` desk on this market.

    ``positions`` is an **interval intersection**, not a point query: one
    opened at 10:00 and still open is part of what was true at 11:45, and a
    query on ``entry_at`` alone would answer that the desk held nothing
    (design §4A). ``orders`` is a plain cut on ``received_at`` — an attempt is
    an instant — and refusals are *not* filtered out: they are the screen's
    most valuable line.

    Outside Binance the trail is empty by construction:
    ``spot_desk_markets`` is keyed on ``binance_symbol``, so answering a
    ``bybit`` symbol from it would be an invented trail, not a translated one.
    """
    del context  # the dependency is the gate; the handler needs nothing from it
    now = utcnow()
    window = resolve_window(
        since=since, until=until, now=now, default_span=DEFAULT_WINDOW, max_span=MAX_WINDOW
    )
    if exchange != DESK_EXCHANGE:
        return DeskOut(
            as_of=now,
            since=window.since,
            until=window.until,
            desk_market=None,
            orders=[],
            orders_truncated=False,
            positions=[],
            positions_truncated=False,
        )

    repository = MarketDeskRepository(session)
    desk_market = await repository.get_desk_market(symbol)
    orders = await repository.list_orders(
        symbol, since=window.since, until=window.until, limit=MAX_DESK_ROWS
    )
    positions = await repository.list_positions(
        symbol, since=window.since, until=window.until, limit=MAX_DESK_ROWS
    )
    return DeskOut(
        as_of=now,
        since=window.since,
        until=window.until,
        desk_market=None if desk_market is None else DeskMarketOut.from_row(desk_market),
        orders=[DeskOrderOut.from_row(row) for row in orders.rows],
        orders_truncated=orders.truncated,
        positions=[DeskPositionOut.from_row(row) for row in positions.rows],
        positions_truncated=positions.truncated,
    )


@router.get(
    "/{exchange}/{symbol}/events",
    response_model=MarketEventsOut,
    summary="Read the recorded news for one market",
)
async def get_market_events(
    exchange: Exchange,
    symbol: Symbol,
    session: OrgSession,
    context: ViewerOrg,
    since: UtcDatetime | None = None,
    until: UtcDatetime | None = None,
) -> MarketEventsOut:
    """Headlines recorded for this market, newest first.

    A row whose ``exchange`` is ``NULL`` is not about one venue and reaches
    this symbol's screen whatever ``{exchange}`` says. ``published_at`` and
    ``ingested_at`` both travel, because "what was known at 11:45" must not
    absorb what we only read at 13:00 (design §4C).

    An empty list means "nothing was recorded for this market in this period",
    never "this market has no news": today the only source is the plantão's own
    hand through ``infra/scripts/market_event.py`` (design §8), and saying so
    is the screen's job, not this payload's.
    """
    del context
    now = utcnow()
    window = resolve_window(
        since=since, until=until, now=now, default_span=DEFAULT_WINDOW, max_span=MAX_WINDOW
    )
    page = await MarketEventsRepository(session).list_events(
        symbol,
        exchange=exchange,
        since=window.since,
        until=window.until,
        limit=MAX_EVENT_ROWS,
    )
    return MarketEventsOut(
        as_of=now,
        since=window.since,
        until=window.until,
        items=[MarketEventOut.from_row(row) for row in page.rows],
        truncated=page.truncated,
    )
