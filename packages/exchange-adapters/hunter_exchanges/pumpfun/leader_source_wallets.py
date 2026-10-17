"""The wallet set handed to a leader source (H-037), validated and fail closed.

A wallet ends up inside a NATS ``SUB account_balance_change.<wallet>.*`` line, so only a real public key
may pass: base58 that decodes to exactly 32 bytes (no ``*``/``>`` wildcard, no space, no CRLF). The set is
the pilot's frozen leaders — at most :data:`MAX_WALLETS` (20 from the rule plus up to 4 named by the
operator, ``docs/design/copiar-carteiras-papel.md`` §2.2). Errors never echo the offending text.
"""

from __future__ import annotations

from collections.abc import Collection

from hunter_exchanges.pumpfun.solana_codec import b58decode

MAX_WALLETS = 24
_MAX_B58_LEN = 44  # a 32-byte key is 43-44 characters

__all__ = ["MAX_WALLETS", "validate_wallets"]


def _is_pubkey(text: object) -> bool:
    if not isinstance(text, str) or not 32 <= len(text) <= _MAX_B58_LEN:
        return False
    try:
        return len(b58decode(text)) == 32
    except ValueError:
        return False


def validate_wallets(wallets: Collection[str]) -> frozenset[str]:
    """The wallets as a frozenset, or ``ValueError`` (fail closed) for an empty set, more than
    :data:`MAX_WALLETS`, or any entry that is not a 32-byte base58 key."""
    unique = frozenset(wallets)
    if not unique:
        raise ValueError("a leader source needs at least one wallet")
    if len(unique) > MAX_WALLETS:
        raise ValueError(f"at most {MAX_WALLETS} wallets can be followed, got {len(unique)}")
    for wallet in unique:
        if not _is_pubkey(wallet):
            raise ValueError("a followed wallet must be a 32-byte base58 public key")
    return unique
