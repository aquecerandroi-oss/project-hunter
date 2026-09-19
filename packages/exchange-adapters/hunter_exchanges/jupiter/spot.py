"""Generic mint-pair spot swap helpers over the Jupiter client (T4.73).

``client.py``'s ``quote``/``swap`` already take arbitrary ``input_mint``/
``output_mint`` strings — T4.54's treasury only ever called them with USDC and
wrapped SOL. This module is the thin, exchange-side layer any caller outside
``hunter_meme_executor.treasury`` (an ops script, a future desk) uses instead
of building the raw request itself: it resolves the one convenience symbol
("SOL") to the wrapped-SOL mint and otherwise passes mints through unchanged
— there is no registry of tickers here, on purpose (a base58 mint address is
unambiguous; a symbol like "WIF" is not, and this package never guesses).

Nothing here signs, sends, or verifies anything. Same wall as ``client.py``:
verification is ``hunter_meme_executor``'s job on the executor side of
``docs/EXCHANGE_INTEGRATION.md``.
"""

from __future__ import annotations

from hunter_exchanges.jupiter.client import JupiterClient
from hunter_exchanges.jupiter.models import (
    WRAPPED_SOL_MINT,
    JupiterQuote,
    JupiterSwapTransaction,
)

__all__ = ["resolve_mint", "quote", "swap_tx"]


def resolve_mint(symbol_or_mint: str) -> str:
    """``"SOL"`` (any case) resolves to the wrapped-SOL mint; anything else is
    returned unchanged — the caller is expected to pass a real mint address."""
    stripped = symbol_or_mint.strip()
    if stripped.upper() == "SOL":
        return WRAPPED_SOL_MINT
    return stripped


def quote(
    client: JupiterClient,
    *,
    input_mint: str,
    output_mint: str,
    amount_atoms: int,
    slippage_bps: int,
) -> JupiterQuote:
    """``GET /quote`` for any mint pair — ``input_mint``/``output_mint`` accept
    ``"SOL"`` as a convenience for :data:`WRAPPED_SOL_MINT`."""
    return client.quote(
        input_mint=resolve_mint(input_mint),
        output_mint=resolve_mint(output_mint),
        amount=amount_atoms,
        slippage_bps=slippage_bps,
    )


def swap_tx(
    client: JupiterClient, *, quote: JupiterQuote, user_public_key: str
) -> JupiterSwapTransaction:
    """``POST /swap`` for a quote already fetched through :func:`quote` (or any
    other ``JupiterQuote`` naming the same pair) — the unsigned versioned
    transaction, unchanged from ``client.swap``."""
    return client.swap(quote=quote, user_public_key=user_public_key)
