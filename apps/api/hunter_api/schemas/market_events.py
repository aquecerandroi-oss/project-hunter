"""``GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/events`` — the news
lane of the confluence screen (T4.82, design §7a item 4).

``published_at`` and ``ingested_at`` travel separately and both are exposed.
That pair is the whole reason §4C ("Depois deste instante") can exist: a
headline published before the cursor but ingested after it is knowledge we did
**not** have at 11:45, and a screen that folded the two into one instant would
quietly claim we did.

``published_at`` may be ``null``. The screen then lists the item with "horário
de publicação desconhecido" and never draws it on the chart (§3, overlay 4) —
the read below places it by ``observed_at`` so it still falls inside the
window, but it never invents a publication instant for it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from hunter_core.db.models.market_events import MarketEvent

__all__ = ["MarketEventOut", "MarketEventsOut"]


class MarketEventOut(BaseModel):
    id: uuid.UUID
    market_id: uuid.UUID | None
    """``null`` while the pair is not (yet) in ``markets`` — a headline can be
    recorded before the market enters the monitored universe."""
    exchange: str | None
    """``null`` = not about one venue (a macro headline); it reaches this
    symbol's screen on every venue."""
    symbol: str
    source: str
    kind: str
    title: str
    url: str | None
    published_at: datetime | None
    observed_at: datetime
    ingested_at: datetime
    confidence: str
    """``confirmed`` / ``reported`` / ``rumor`` — rendered as a **shape**, never
    as a colour (colour stays semantic, design §3 overlay 4)."""
    notes: dict[str, Any]
    recorded_by: str

    @classmethod
    def from_row(cls, row: MarketEvent) -> MarketEventOut:
        return cls(
            id=row.id,
            market_id=row.market_id,
            exchange=row.exchange,
            symbol=row.symbol,
            source=row.source,
            kind=row.kind,
            title=row.title,
            url=row.url,
            published_at=row.published_at,
            observed_at=row.observed_at,
            ingested_at=row.ingested_at,
            confidence=row.confidence,
            notes=dict(row.notes or {}),
            recorded_by=row.recorded_by,
        )


class MarketEventsOut(BaseModel):
    as_of: datetime
    since: datetime
    until: datetime
    """The window the server applied, echoed back — see ``DeskOut``."""
    items: list[MarketEventOut]
    """Newest first, ordered by ``COALESCE(published_at, observed_at)``."""
    truncated: bool
    """``true`` when the server's row cap bit. No cursor by design; the remedy
    is a narrower window. The screen must not turn a capped list into "nenhuma
    notícia registrada", which is a different fact."""
