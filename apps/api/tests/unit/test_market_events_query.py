"""T4.82: the news read behind
``GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/events``.

Two properties carry the design's arguments into SQL:

- **the venue filter is ``exchange IS NULL OR exchange = :exchange``.** A
  Binance delisting notice names ``binance``; a macro headline about ZEC names
  nobody and must still reach the ZEC screen of every venue. Matching on
  equality alone would silently drop every venue-less headline — which is most
  of them.
- **"when" is ``COALESCE(published_at, observed_at)``.** ``published_at`` is
  nullable on purpose (an item whose publication instant the source does not
  give), and placing such a row by when we saw it is the only honest fallback.
  Ordering by ``published_at`` alone would bunch every one of them at the end
  of the list under ``NULLS LAST``.

Compiled SQL; no database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql

from hunter_api.repositories.market_events import build_events_statement

pytestmark = pytest.mark.unit

SINCE = datetime(2026, 9, 23, 11, 30, tzinfo=UTC)
UNTIL = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _sql() -> str:
    statement = build_events_statement(
        "ZECUSDT", exchange="binance", since=SINCE, until=UNTIL, limit=200
    )
    return str(statement.compile(dialect=postgresql.dialect()))


def test_it_is_scoped_to_the_symbol() -> None:
    assert "market_events.symbol =" in _sql()


def test_a_headline_that_names_no_venue_still_reaches_the_screen() -> None:
    sql = _sql()
    assert "market_events.exchange IS NULL" in sql
    assert "market_events.exchange =" in sql
    assert " OR " in sql


def test_the_window_is_half_open_on_the_coalesced_instant() -> None:
    sql = _sql()
    assert "coalesce(market_events.published_at, market_events.observed_at) >=" in sql
    assert "coalesce(market_events.published_at, market_events.observed_at) <" in sql


def test_an_item_with_no_publication_instant_is_placed_by_when_we_saw_it() -> None:
    """``observed_at`` is ``NOT NULL``, so the COALESCE can never be null and
    the row can never fall out of the window for want of a ``published_at``."""
    assert "coalesce(market_events.published_at, market_events.observed_at)" in _sql()


def test_it_is_ordered_newest_first_and_bounded() -> None:
    sql = _sql()
    assert "ORDER BY coalesce(market_events.published_at, market_events.observed_at) DESC" in sql
    assert "LIMIT" in sql


def test_nothing_is_filtered_by_confidence() -> None:
    """A rumour is a fact about what the shift heard; the screen renders it as
    a shape (§3, overlay 4) and never as an absence."""
    where = _sql().split("WHERE", 1)[1]
    assert "confidence" not in where
