"""``market_events`` — what happened *around* a non-meme market: a listing, an
incident, a macro headline (T4.82, revision ``0059_market_events``, design
``docs/design/tela-confluencia-mercado.md`` §7a item 4).

**A new table rather than a ``kind`` on ``meme_events``**, and the reason is a
concrete failure, not taste: ``meme_events.mint`` is an FK to
``meme_tokens.mint``, and the per-minute matching job
(``services/meme-worker/hunter_meme_worker/events_repo.py``) scans by
``observed_at`` **without filtering ``mint IS NULL``**, matching an event to a
coin through ``symbol_hint``. A Zcash headline filed as ``symbol_hint = 'ZEC'``
would find a homonymous meme minted in the same window and start
contextualising that meme's proposals. A partial index would not help: an index
does not change the matcher's ``SELECT``.

**Global, like ``meme_events`` and ``meme_live_*``** (DATABASE.md §1.1): a
headline belongs to the world, not to an organization — no ``organization_id``
and therefore no RLS. Who may read it is decided by the router's gate
(``apps/api/hunter_api/routers/market_desk.py``, ``require_org(VIEWER)``),
which is the same door the ``meme_live`` ledger sits behind.

Three columns carry decisions:

- **``symbol`` is ``NOT NULL``, ``market_id`` is not.** A headline can be
  recorded before the pair enters the monitored universe; losing it for want of
  a ``markets`` row would be worse than carrying a null for a few days (§9,
  where this is written down as a divergence from Astra's review, who asked for
  the FK to be the link).
- **``published_at`` and ``ingested_at`` are separate, and ``published_at`` may
  be ``NULL``.** "What was known at 11:45" cannot silently absorb what we only
  learned at 13:00 (§4C); an item whose publication instant is unknown is
  honest about it and is listed rather than drawn on the chart (§3, overlay 4).
- **``exchange`` is nullable, meaning "not about one venue".** A Binance
  delisting notice names ``binance``; a macro headline about ZEC names nobody,
  and must still reach the ZEC screen of every venue.

**Idempotence is ``(source, url, symbol)``, not ``(source, url)``** as the
design first wrote it. Astra's review of this table found the failure: one
Binance announcement can name ZECUSDT *and* BTCUSDT, and on ``(source, url)``
the second filing would be swallowed as a duplicate — the BTCUSDT screen would
never show a headline that is genuinely about it. Adding ``symbol`` keeps the
property the design wanted (re-running the same link for the same market writes
one row) and drops the one it did not intend.

Written today only by ``infra/scripts/market_event.py`` (audited, dry-run by
default). When a collector eventually replaces the plantão's hand, it writes
the same rows and no screen changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY

MARKET_EVENT_SOURCES = ("baha", "manual", "plantao", "exchange_notice")
"""``baha``: the plantão's own reading of baha.com. ``plantao``: anything else
the shift saw. ``manual``: a backfill by hand. ``exchange_notice``: the venue's
own announcement page."""

MARKET_EVENT_KINDS = (
    "listing",
    "delisting",
    "upgrade",
    "incident",
    "macro",
    "company",
    "narrative",
)

MARKET_EVENT_CONFIDENCES = ("confirmed", "reported", "rumor")
"""Same ladder as ``meme_events``: ``confirmed`` is the source's own channel
read directly, ``reported`` is a credible mirror, ``rumor`` is everything else
worth a line. The screen renders this as **shape**, never as colour (§3,
overlay 4) — colour stays semantic."""


class MarketEvent(Base, UUIDPrimaryKeyMixin):
    """One dated thing that happened around a market, with who recorded it."""

    __tablename__ = "market_events"
    __table_args__ = (
        # Plain ascending columns, not ``text("... DESC")``: Postgres reads a
        # b-tree backwards at no cost for ``ORDER BY ... DESC``, and an
        # expression index is something ``alembic check`` cannot compare
        # against the model (§17.3), so the DESC would buy nothing and cost
        # the one guard that catches drift between this file and ``0059``.
        Index("ix_market_events_symbol_published_at", "symbol", "published_at"),
        Index("ix_market_events_symbol_observed_at", "symbol", "observed_at"),
        Index(
            "uq_market_events_source_url_symbol",
            "source",
            "url",
            "symbol",
            unique=True,
            postgresql_where=text("url IS NOT NULL"),
        ),
        CheckConstraint(f"source IN {MARKET_EVENT_SOURCES!r}", name="source_is_a_known_label"),
        CheckConstraint(f"kind IN {MARKET_EVENT_KINDS!r}", name="kind_is_a_known_label"),
        CheckConstraint(
            f"confidence IN {MARKET_EVENT_CONFIDENCES!r}", name="confidence_is_a_known_label"
        ),
        CheckConstraint(
            "char_length(title) > 0 AND char_length(symbol) > 0 AND char_length(recorded_by) > 0",
            name="identity_is_not_empty",
        ),
        CheckConstraint("url IS NULL OR char_length(url) > 0", name="a_url_is_not_empty"),
        CheckConstraint(
            "exchange IS NULL OR char_length(exchange) > 0", name="an_exchange_is_not_empty"
        ),
    )

    market_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("markets.id"))
    """``NULL`` until the pair exists in ``markets`` — see the module docstring."""

    exchange: Mapped[str | None] = mapped_column(Text)
    """``NULL`` = not about one venue; the read then matches every venue."""

    symbol: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)

    published_at: Mapped[datetime | None]
    """When the world could first have known. ``NULL`` when the source does not
    say — the screen lists the row and names the gap instead of guessing."""

    observed_at: Mapped[datetime]
    """When *we* saw it. Never ``now()`` by default: the script passes it."""

    ingested_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    """When the row was written. With ``published_at`` this is what separates
    "o que se sabia" from "o que descobrimos depois" (§4C)."""

    confidence: Mapped[str] = mapped_column(Text)
    notes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    recorded_by: Mapped[str] = mapped_column(Text)


__all__ = [
    "MARKET_EVENT_CONFIDENCES",
    "MARKET_EVENT_KINDS",
    "MARKET_EVENT_SOURCES",
    "MarketEvent",
]
