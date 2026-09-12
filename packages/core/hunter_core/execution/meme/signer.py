"""Local signing for the meme wallet — the only module that reads ``SOLANA_WALLET_SECRET_KEY``.

``docs/RISK_ENGINE_MEME.md`` §3.3, mechanised:

- **Read once.** :meth:`MemeSigner.from_environment` takes the variable out of the
  environment as it reads it (``scrub=True``); a second read in the same process
  finds nothing and fails with :class:`SecretKeyMissing`. Nothing else in the
  repo names the variable (``forbidden_patterns.sh`` also refuses a committed
  value).
- **Never rendered.** The signer keeps only an ``Ed25519PrivateKey`` object (a
  ``cryptography`` handle with no ``repr`` of its bytes) and the public key.
  ``repr``/``str`` show the public key; pickling and ``copy`` are refused; there
  is no attribute that holds the secret string, so ``vars()``, JSON dumps,
  heartbeats and exception reprs have nothing to leak. ``test_meme_signer.py``
  proves it by scanning every rendering for the secret and its prefixes.
- **Boot refusal.** :func:`boot_meme_execution` reads the §12 gates first
  (``gates.py``): with the live flag on and an invalid or missing
  ``meme_gates.json`` the process dies *before* the key is touched.

Accepted key shapes are the two Solana CLI/Phantom exports: a base58 string of
the 64-byte keypair (seed ‖ public key) or a JSON array of 64 integers. A 32-byte
seed is also accepted. The embedded public key must match the one derived from
the seed, or the key is refused as malformed — a truncated paste must not sign.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from datetime import date
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hunter_core.execution.meme.base58 import b58decode, b58encode
from hunter_core.execution.meme.gates import (
    MemeExecutionMode,
    MemeLiveTradingRefused,
    load_execution_mode,
)

__all__ = [
    "ENV_SECRET_KEY",
    "MemeSigner",
    "SecretKeyMalformed",
    "SecretKeyMissing",
    "SignerError",
    "boot_meme_execution",
]

ENV_SECRET_KEY = "SOLANA_WALLET_SECRET_KEY"  # noqa: S105 - the variable's *name*, not a value


class SignerError(RuntimeError):
    """Base of every signer refusal. Messages never carry key material."""


class SecretKeyMissing(SignerError):
    pass


class SecretKeyMalformed(SignerError):
    pass


def _parse_secret(text: str) -> bytes:
    """Return the raw keypair bytes (64) or seed (32). Errors name the *shape*, never the value."""
    stripped = text.strip()
    if not stripped:
        raise SecretKeyMissing(f"{ENV_SECRET_KEY} is empty")
    if stripped.startswith("["):
        try:
            parsed: Any = json.loads(stripped)
        except ValueError as exc:
            raise SecretKeyMalformed("JSON array form is not valid JSON") from exc
        if not isinstance(parsed, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
            for v in parsed  # pyright: ignore[reportUnknownVariableType]
        ):
            raise SecretKeyMalformed("JSON array form must hold integers 0..255")
        raw = bytes(parsed)  # pyright: ignore[reportUnknownArgumentType]
    else:
        try:
            raw = b58decode(stripped)
        except (ValueError, UnicodeEncodeError) as exc:
            raise SecretKeyMalformed("base58 form has an invalid character") from exc
    if len(raw) not in (32, 64):
        raise SecretKeyMalformed(f"key is {len(raw)} bytes; need a 64-byte keypair or 32-byte seed")
    return raw


class MemeSigner:
    """Holds the key; renders only the public key; signs message bytes."""

    __slots__ = ("_key", "_pubkey", "_pubkey_raw")

    def __init__(self, key: Ed25519PrivateKey) -> None:
        self._key = key
        self._pubkey_raw = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self._pubkey = b58encode(self._pubkey_raw)

    @classmethod
    def from_environment(cls, env: MutableMapping[str, str], *, scrub: bool = True) -> MemeSigner:
        """Read ``SOLANA_WALLET_SECRET_KEY`` **once** and remove it from ``env``."""
        text = env.get(ENV_SECRET_KEY)
        if text is None:
            raise SecretKeyMissing(f"{ENV_SECRET_KEY} is not set")
        try:
            raw = _parse_secret(text)
        finally:
            if scrub:
                env.pop(ENV_SECRET_KEY, None)
            del text
        key = Ed25519PrivateKey.from_private_bytes(raw[:32])
        if len(raw) == 64:
            derived = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            if derived != raw[32:]:
                raise SecretKeyMalformed("embedded public key does not match the seed")
        del raw
        return cls(key)

    @property
    def pubkey(self) -> str:
        return self._pubkey

    @property
    def pubkey_raw(self) -> bytes:
        return self._pubkey_raw

    def sign(self, message: bytes) -> bytes:
        """Ed25519 signature (64 bytes) over the serialized message."""
        if not message:
            raise SignerError("message to sign must be non-empty bytes")
        return self._key.sign(bytes(message))

    def __repr__(self) -> str:
        return f"MemeSigner(pubkey={self._pubkey})"

    __str__ = __repr__

    def __reduce__(self) -> Any:
        raise TypeError("MemeSigner cannot be pickled or copied")

    def __deepcopy__(self, memo: Any) -> Any:
        raise TypeError("MemeSigner cannot be pickled or copied")

    def __copy__(self) -> Any:
        raise TypeError("MemeSigner cannot be pickled or copied")


def boot_meme_execution(
    env: MutableMapping[str, str], *, today: date
) -> tuple[MemeExecutionMode, MemeSigner | None]:
    """Gates first, key second. Live with red gates never reaches the key.

    Returns the mode and, when a key is configured, the signer. Live mode
    **requires** the key; paper/devnet may run without one (nothing to sign).
    """
    mode = load_execution_mode(env, today=today)
    if mode.live:
        try:
            return mode, MemeSigner.from_environment(env)
        except SecretKeyMissing as exc:
            raise MemeLiveTradingRefused("secret_key_missing", str(exc)) from exc
    if not (env.get(ENV_SECRET_KEY) or "").strip():
        env.pop(ENV_SECRET_KEY, None)
        return mode, None
    return mode, MemeSigner.from_environment(env)


def environment_has_secret(env: Mapping[str, str]) -> bool:
    """For readiness reporting: whether the variable is still present (it should
    not be, after :meth:`MemeSigner.from_environment`)."""
    return ENV_SECRET_KEY in env
