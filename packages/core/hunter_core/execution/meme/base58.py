"""Base58 (Bitcoin/Solana alphabet), pure Python — ``hunter_core`` cannot import the adapter.

The same 20 lines live in ``hunter_exchanges.pumpfun.solana_codec``; duplicating
them here is cheaper than a distribution cycle (``packages/core/pyproject.toml``
explains why the dependency runs adapter → core, never back).
"""

from __future__ import annotations

__all__ = ["b58decode", "b58encode"]

_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {c: i for i, c in enumerate(_ALPHABET)}


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_ALPHABET[rem])
    out.reverse()
    return (_ALPHABET[0:1] * (len(raw) - len(raw.lstrip(b"\0"))) + out).decode("ascii")


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text.encode("ascii", errors="strict"):
        if ch not in _INDEX:
            raise ValueError("invalid base58 character")
        n = n * 58 + _INDEX[ch]
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + raw
