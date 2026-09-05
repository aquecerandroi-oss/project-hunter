"""Symbol conventions shared by every exchange adapter.

``docs/EXCHANGE_INTEGRATION.md`` §2: "interno = simbolo da exchange sem
separadores (BTCUSDT) mais exchange_code e market_type." Binance already
speaks this dialect natively (``BTCUSDT``, no separator), so
:func:`internal_symbol` is an identity mapping for it today; it exists so a
future adapter whose native symbol has a separator (e.g. ``BTC-USDT``) has
one place to normalize instead of every call site guessing.
"""

from __future__ import annotations


def internal_symbol(exchange_symbol: str) -> str:
    """The internal symbol for a raw exchange symbol: no separators, upper case."""
    return exchange_symbol.replace("-", "").replace("_", "").replace("/", "").upper()


def split_base_quote(base_asset: str, quote_asset: str) -> tuple[str, str]:
    """``(base, quote)`` from ``exchangeInfo``'s own ``baseAsset``/``quoteAsset``.

    Trusting the exchange's own split avoids guessing where a concatenated
    symbol like ``1000SHIBUSDT`` divides.
    """
    return base_asset.upper(), quote_asset.upper()
