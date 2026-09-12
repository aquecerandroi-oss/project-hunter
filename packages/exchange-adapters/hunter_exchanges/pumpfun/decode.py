"""Bonding curve account layout — the on-chain truth for reserves.

Field order and types come from the official pump.fun IDL
(``pump-fun/pump-public-docs``, ``BondingCurve`` account type), vendored and
read with an Anchor-style IDL parser by
``chainstacklabs/pumpfun-bonkfun-bot`` commit ``a0540fdc9e6bb108d52f0f512f2e396d2396bdef``
(``idl/pump_fun_idl.json``, 2026-08-24 — cited per T4.0's research, not
copied: this module hand-decodes the fixed layout below with ``struct``
instead of vendoring an IDL parser, since only one account type is ever
read here).

Layout (little-endian), 115 bytes before an observed 9-byte reserved tail
(``space=124`` on the one live account this task read — the extra bytes are
zero and unparsed):

======================  ====  ================================================
field                   size  notes
======================  ====  ================================================
discriminator             8   Anchor BondingCurve discriminator, validated
virtual_token_reserves     8  u64, raw subunits (``TOKEN_SUBUNITS_PER_TOKEN``)
virtual_quote_reserves     8  u64, raw lamports when ``quote_mint`` is native
                               SOL (``curve.py``'s ``virtual_sol_reserves``)
real_token_reserves        8  u64, raw subunits
real_quote_reserves        8  u64, raw lamports
token_total_supply         8  u64, raw subunits
complete                   1  bool
creator                   32  pubkey, base58-encoded below
is_mayhem_mode             1  bool, opaque pump.fun feature flag — not
                               modelled further by this package
is_cashback_coin           1  bool, opaque, same as above
quote_mint                32  pubkey — all-zero (System Program id,
                               base58 ``"111...1"``) means the quote asset is
                               native SOL, the only case this package models
======================  ====  ================================================

The inherited RPC fixture and the separately timestamped A4.1 capture exercise
this layout. REST and RPC reads are not atomic and their reserves can differ;
Mayhem enabled on-chain does not imply the REST agent state is active.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass

from hunter_exchanges.base import MalformedMessage

_DISCRIMINATOR_LEN = 8
_U64_FIELD_COUNT = 5
_MIN_LEN = _DISCRIMINATOR_LEN + _U64_FIELD_COUNT * 8 + 1 + 32 + 1 + 1 + 32  # 115
_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

#: The only bonding curve program this package trusts an account decode from
#: (T4.0 §1, confirmed live via ``getAccountInfo.value.owner``).
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

#: Native SOL as a quote mint is the System Program id, 32 zero bytes.
NATIVE_SOL_QUOTE_MINT = "11111111111111111111111111111111"


@dataclass(frozen=True)
class BondingCurveAccount:
    """Raw (unconverted) fields decoded straight off the account bytes."""

    virtual_token_reserves: int
    virtual_sol_reserves: int
    real_token_reserves: int
    real_sol_reserves: int
    token_total_supply: int
    complete: bool
    creator: str
    is_mayhem_mode: bool
    is_cashback_coin: bool
    quote_mint: str


def _b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_B58_ALPHABET[rem])
    out.reverse()
    pad = 0
    for byte in raw:
        if byte != 0:
            break
        pad += 1
    return (_B58_ALPHABET[0:1] * pad + out).decode("ascii")


def decode_bonding_curve_account(data_base64: str, *, owner: str) -> BondingCurveAccount:
    """Decode a ``getAccountInfo`` base64 payload into raw on-chain fields.

    Raises :class:`MalformedMessage` for anything that isn't a plausible
    ``BondingCurve`` account — wrong owner, too short, bad base64 — instead
    of guessing at a partially-decoded struct (D1: never invent a number the
    input doesn't have).
    """
    if owner != PUMP_PROGRAM_ID:
        raise MalformedMessage(
            f"account owner {owner!r} is not the pump.fun bonding curve program", exchange="pumpfun"
        )
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"bonding curve account data is not base64: {exc}", exchange="pumpfun"
        ) from exc
    if len(raw) < _MIN_LEN:
        raise MalformedMessage(
            f"bonding curve account too short: {len(raw)} bytes, need >= {_MIN_LEN}",
            exchange="pumpfun",
        )
    if raw[:8] != bytes.fromhex("17b7f83760d8ac60"):
        raise MalformedMessage("wrong BondingCurve discriminator", exchange="pumpfun")
    if any(raw[offset] not in (0, 1) for offset in (48, 81, 82)):
        raise MalformedMessage("invalid BondingCurve boolean", exchange="pumpfun")
    off = _DISCRIMINATOR_LEN
    fields: list[int] = []
    for _ in range(_U64_FIELD_COUNT):
        fields.append(struct.unpack_from("<Q", raw, off)[0])
        off += 8
    virtual_token_reserves, virtual_sol_reserves, real_token_reserves, real_sol_reserves, supply = (
        fields
    )
    complete = bool(raw[off])
    off += 1
    creator = _b58encode(raw[off : off + 32])
    off += 32
    is_mayhem_mode = bool(raw[off])
    off += 1
    is_cashback_coin = bool(raw[off])
    off += 1
    quote_mint = _b58encode(raw[off : off + 32])
    return BondingCurveAccount(
        virtual_token_reserves=virtual_token_reserves,
        virtual_sol_reserves=virtual_sol_reserves,
        real_token_reserves=real_token_reserves,
        real_sol_reserves=real_sol_reserves,
        token_total_supply=supply,
        complete=complete,
        creator=creator,
        is_mayhem_mode=is_mayhem_mode,
        is_cashback_coin=is_cashback_coin,
        quote_mint=quote_mint,
    )


__all__ = [
    "NATIVE_SOL_QUOTE_MINT",
    "PUMP_PROGRAM_ID",
    "BondingCurveAccount",
    "decode_bonding_curve_account",
]
