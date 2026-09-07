"""Market identity for the Binance **SPOT** adapter - and why it is shaped
like this (T3.0a, ``.claude/state/map-T3.0-market-identity.md`` option B,
Astra review ``.claude/state/astra-review-T3.0a-spot.md``).

``BTCUSDT`` exists twice on Binance: as a spot pair and as a USDS-M
perpetual. They are **different markets** with different prices, different
fees and different filters, and nothing in the system may confuse them.

The venue, however, is the same: one row in ``exchanges`` (``code =
'binance'``), one IP, one 429/418 ban surface. So:

- ``exchange`` stays ``"binance"`` for both adapters. Making the spot side
  ``"binance_spot"`` (option A of the map) would need a second ``exchanges``
  row and would touch ~40 files across ``services/**`` - and the database
  already discriminates correctly, with ``UNIQUE (exchange_id, symbol,
  market_type)`` on ``markets``;
- the discriminator is ``market_type``. ``NormalizedMarket`` carries it, and
  every adapter now declares its own (:attr:`BinanceSpotAdapter.market_type`
  = ``SPOT``, :attr:`BinanceAdapter.market_type` = ``PERPETUAL``), so a
  caller holding an adapter and a symbol can always build the full identity
  with :func:`market_identity`.

**The gap this docstring used to describe is closed.** T3.0b gave every event
model (``NormalizedTicker``/``Trade``/``OrderBook``/``Candle``) a
``market_type`` field, defaulting to ``PERPETUAL`` so every payload already on
a stream or in Redis keeps meaning exactly what it meant before. The spot
parsers in this package pass ``SPOT`` explicitly — nothing is ever inferred
from which adapter produced an event, because a wrong guess here would
silently relabel a spot market as a perpetual one.

Every Redis key builder in ``hunter_core.redis.keys`` now takes the same
``market_type`` and folds it into the *venue* segment: the perpetual's key is
byte-identical to what it always was (``mkt:binance:BTCUSDT:ticker``, no
segment for ``market_type is PERPETUAL``), and the spot pair gets its own
(``mkt:binance:spot:BTCUSDT:ticker``). The two listings of one symbol no
longer share a hot-state key.

**Deliberate exception (KB-0044).** The ticker *hash's own fields* never
include ``market_type`` — it is already the key's discriminator, and the hash
is written by two disjoint producers (the REST 24h refresh and the WS
``bookTicker``) whose whole contract is "touch only the fields you own"; adding
an unowned field to that shared hash was exactly the class of bug KB-0044
fixed. So a reader confirms which market it holds from the *key* it asked for,
never from a field inside the hash.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hunter_core.domain.enums import MarketType

__all__ = [
    "EXCHANGE",
    "MARKET_TYPE",
    "MarketTyped",
    "market_identity",
]

#: One venue, one ``exchanges`` row, one rate-limit IP: the same code the
#: USDS-M adapter uses.
EXCHANGE = "binance"

#: What this adapter lists, streams and prices.
MARKET_TYPE = MarketType.SPOT


@runtime_checkable
class MarketTyped(Protocol):
    """An adapter that says which market family it speaks for.

    Additive to :class:`~hunter_exchanges.base.ExchangeAdapter` on purpose:
    an adapter (or fake) written before T3.0a is not forced to grow the
    attribute mid-milestone, and readers use ``isinstance``/``getattr``
    rather than assuming a default - a wrong default here would silently
    label a spot market as a perpetual one.
    """

    code: str
    market_type: MarketType


def market_identity(exchange: str, symbol: str, market_type: MarketType) -> str:
    """The full identity of one market: ``"binance:spot:BTCUSDT"``.

    Never ``exchange`` + ``symbol`` alone - that string is the same for the
    spot pair and the perpetual, which is exactly the collision T3.0 exists
    to prevent. Meant for an in-adapter dict keyed by market (the adapter's own
    ``.identity(symbol)``) — it always spells out the type.

    **Not** the shape of a real hot-state key. ``hunter_core.redis.keys``
    keeps the perpetual's key byte-identical to what it was before spot
    existed (``mkt:{exchange}:{symbol}:...``, no segment at all) and only
    spot gets one (``mkt:{exchange}:spot:{symbol}:...``) — every writer that
    shipped before T3.0 keeps meaning exactly what it always meant. A template
    that always inserted ``market_type`` here would break that.
    """
    return f"{exchange}:{market_type.value}:{symbol}"
