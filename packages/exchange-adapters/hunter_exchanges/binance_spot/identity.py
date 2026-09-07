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

**Known gap, deliberately not closed here (T3.0b/core).** The *event* models
(``NormalizedTicker``/``Trade``/``OrderBook``/``Candle``) have no
``market_type`` field, and this task must not edit ``packages/core``. So a
spot ticker and a perpetual ticker for ``BTCUSDT`` are, on the wire, still
distinguishable only by *which adapter produced them*. Until T3.0b adds
``market_type`` to those models and to the Redis key builders
(``hunter_core.redis.keys``), spot events must not be written into the same
hot state as perpetual ones: ``mkt:binance:BTCUSDT:ticker`` would be
overwritten by whichever arrived last. This is recorded in
``.claude/state/notes-T3.0a.md`` as a blocker for the market-worker
integration, not worked around with a local subclass or an extra field.
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
    to prevent. Intended as the discriminating part of a Redis key
    (``mkt:{exchange}:{market_type}:{symbol}:...``) and of any in-memory
    dict keyed by market.
    """
    return f"{exchange}:{market_type.value}:{symbol}"
