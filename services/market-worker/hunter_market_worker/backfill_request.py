"""Reading one ``market.backfill.requested`` payload, and the months it touches.

Split from ``backfill_plan`` for the 350-line budget, along the seam between
"what the producer said" (here) and "what this worker will do about it" (there).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hunter_core.domain.enums import Timeframe
from hunter_market_worker.backfill_plan import Refused
from hunter_market_worker.persist_rows import load_market_ids

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["KINDS", "Request", "market_id_for", "months_between", "parse_request"]

KINDS = frozenset({"candles", "funding"})
"""T3.7c: additive. ``candles`` is the default, so a producer written before
this field existed (the scanner) is understood exactly as before."""


@dataclass(frozen=True)
class Request:
    """The fields of the ``market.backfill.requested`` payload this worker acts on."""

    exchange: str
    symbol: str
    timeframe: str
    gap_start: datetime
    gap_end: datetime
    market_id: UUID | None
    reason: str
    requested_by: str
    kind: str = "candles"


def parse_request(payload: dict[str, Any]) -> Request:
    """Read the payload the scanner publishes, or refuse it as unreadable.

    Deliberately tolerant about the optional fields (``reason``,
    ``requested_by``, ``market_id``) and strict about the five that decide what
    is fetched -- ``kind`` joined the four original ones in T3.7c. A payload
    that fails here is a refusal, not a crash: the stream is shared and a
    producer's bug must not stop the collector.
    """
    try:
        market_id = payload.get("market_id")
        kind = str(payload.get("kind", "candles"))
        if kind not in KINDS:
            raise Refused("unsupported_kind")
        return Request(
            exchange=str(payload["exchange"]).strip().lower(),
            symbol=str(payload["symbol"]),
            timeframe=str(payload.get("timeframe", Timeframe.M1.value)),
            gap_start=datetime.fromisoformat(str(payload["gap_start"])),
            gap_end=datetime.fromisoformat(str(payload["gap_end"])),
            market_id=UUID(str(market_id)) if market_id else None,
            reason=str(payload.get("reason", "unspecified")),
            requested_by=str(payload.get("requested_by", "unknown")),
            kind=kind,
        )
    except Refused:
        raise
    except Exception as exc:
        raise Refused("unreadable_payload") from exc


async def market_id_for(session: AsyncSession, request: Request) -> Any:
    """This database's id for the requested market.

    The payload's ``market_id`` is **checked, not trusted**: the symbol and the
    exchange decide, and an identity that disagrees with them is refused rather
    than quietly followed (Astra: "identidade inconsistente recusada"). Shared
    by the candle lane (``backfill.py``) and the funding lane
    (``funding_backfill.py``, T3.7c) -- both ask the same question of the same
    table.
    """
    ids = await load_market_ids(session, request.exchange, {request.symbol})
    market_id = ids.get(request.symbol)
    if market_id is None or (request.market_id is not None and request.market_id != market_id):
        return None
    return market_id


def months_between(first: datetime, last: datetime) -> set[tuple[int, int]]:
    """Every ``(year, month)`` the inclusive window touches.

    Candles are partitioned by month, so this is the list of partitions a plan
    needs before it may promise anything (:func:`partitions.storable_months`).
    """
    months: set[tuple[int, int]] = set()
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.add((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months
