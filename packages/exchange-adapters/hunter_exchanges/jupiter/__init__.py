"""Jupiter v6 aggregator adapter (T4.54) — quote + swap-transaction build only.

Public HTTP, no key, no signing, no ``sendTransaction``. Used by
``hunter_meme_executor.treasury`` for the treasury top-up (USDC -> SOL);
nothing else in the repo depends on this package.
"""

from __future__ import annotations

from hunter_exchanges.jupiter.client import JupiterClient, JupiterQuoteError
from hunter_exchanges.jupiter.models import (
    WRAPPED_SOL_MINT,
    JupiterQuote,
    JupiterSwapTransaction,
)
from hunter_exchanges.jupiter.versioned_tx import (
    AddressTableLookup,
    VersionedCompiledInstruction,
    VersionedMessage,
    VersionedTransaction,
    decode_versioned_message,
    decode_versioned_transaction,
)

__all__ = [
    "WRAPPED_SOL_MINT",
    "AddressTableLookup",
    "JupiterClient",
    "JupiterQuote",
    "JupiterQuoteError",
    "JupiterSwapTransaction",
    "VersionedCompiledInstruction",
    "VersionedMessage",
    "VersionedTransaction",
    "decode_versioned_message",
    "decode_versioned_transaction",
]
