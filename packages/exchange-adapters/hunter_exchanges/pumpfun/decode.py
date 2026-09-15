"""Bonding curve account layout — the on-chain truth for reserves.

Field order and types come from the official pump.fun IDL
(``pump-fun/pump-public-docs``, ``BondingCurve`` account type), vendored and
read with an Anchor-style IDL parser by
``chainstacklabs/pumpfun-bonkfun-bot`` commit ``a0540fdc9e6bb108d52f0f512f2e396d2396bdef``
(``idl/pump_fun_idl.json``, 2026-08-24 — cited per T4.0's research, not
copied: this module hand-decodes the fixed layout below with ``struct``
instead of vendoring an IDL parser, since only one account type is ever
read here).

Layout (little-endian), 115 bytes, followed by either a short reserved pad
too small to hold the extra fields — 0 or 9 bytes observed, ``LAYOUT_LEGACY``,
defaults below — or three more fields (``LAYOUT_WITH_HOLDER_REWARD``, 125
bytes) plus a further reserved, unparsed tail (26 zero bytes observed):

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
------------------------ present only when the account was allocated with room
creator_fee_bps            8  u64, a per-coin override of the creator's basis
                               points; ``0`` on every coin this package has
                               read so far except one (T4.2f's 12/09 capture,
                               ``creator_fee_bps=10``) — whether ``0`` means
                               "unset, use the tier" or "explicitly zero" is
                               not established (mirrors ``can_edit_creator_fee``)
can_edit_creator_fee       1  bool, opaque
is_holder_reward           1  bool — **the on-chain byte behind M-P34/KB-0096**:
                               confirmed ``true`` (T4.8c, 2026-09-15) on a mint
                               ``frontend-api-v3.pump.fun`` also reports
                               ``is_holder_reward: true`` for, and ``false`` on
                               a control mint from the same listing
======================  ====  ================================================

**This is not new on-chain state from either 2026-09 upgrade.** T4.2f's
capture of 100 fresh mints on 2026-09-12 already had 45/100 accounts at the
151-byte length (one with a non-zero ``creator_fee_bps``); re-reading the
T4.8/T4.8b reference mints on 2026-09-15 (idle since 09-12) found them at 151
bytes too. ``decode_bonding_curve_account`` simply never looked past byte 115
before T4.8c — the REST/indexer surface exposing ``is_holder_reward`` (KB-0096)
is what changed recently, not this account's shape. Whatever decides an
account's length (creation-time allocation vs. a later realloc) was not
determined within this task's RPC budget; both lengths are read here as
current, coexisting realities, not "before/after" an upgrade.

The inherited RPC fixture and the separately timestamped A4.1 capture exercise
the legacy layout; ``t48c_rpc_bonding_curve_hr_raw.json`` /
``t48c_rpc_bonding_curve_control_raw.json`` (``docs/PUMPFUN-ONCHAIN.md`` §6d)
exercise the extended one. REST and RPC reads are not atomic and their
reserves can differ; Mayhem enabled on-chain does not imply the REST agent
state is active.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass

from hunter_exchanges.base import MalformedMessage

_DISCRIMINATOR_LEN = 8
_U64_FIELD_COUNT = 5
_MIN_LEN = _DISCRIMINATOR_LEN + _U64_FIELD_COUNT * 8 + 1 + 32 + 1 + 1 + 32  # 115
_HOLDER_REWARD_FIELDS_LEN = 8 + 1 + 1  # creator_fee_bps, can_edit_creator_fee, is_holder_reward
LAYOUT_LEGACY = "legacy-115b"
"""The account's allocated space leaves no room (0 or up to 9 reserved bytes)
for the three extra fields — decoded as ``0``/``False``/``False``."""
LAYOUT_WITH_HOLDER_REWARD = "with-holder-reward-125b"
"""The account has room for ``creator_fee_bps``/``can_edit_creator_fee``/
``is_holder_reward`` — present since at least 2026-09-12 on ~45 % of a sampled
population (T4.2f), confirmed readable in this package since T4.8c."""
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
    creator_fee_bps: int = 0
    can_edit_creator_fee: bool = False
    is_holder_reward: bool = False
    layout: str = LAYOUT_LEGACY


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
    off += 32
    trailing = len(raw) - off
    if trailing < _HOLDER_REWARD_FIELDS_LEN:
        # No room for the three extra fields — 0 bytes (space ends at
        # quote_mint) or a short reserved pad (9 bytes, T4.0's original
        # finding). Either way: defaults, not a malformed account.
        creator_fee_bps, can_edit_creator_fee, is_holder_reward, layout = (
            0,
            False,
            False,
            LAYOUT_LEGACY,
        )
    else:
        if raw[off + 8] not in (0, 1) or raw[off + 9] not in (0, 1):
            raise MalformedMessage("invalid BondingCurve boolean", exchange="pumpfun")
        creator_fee_bps = struct.unpack_from("<Q", raw, off)[0]
        can_edit_creator_fee = bool(raw[off + 8])
        is_holder_reward = bool(raw[off + 9])
        layout = LAYOUT_WITH_HOLDER_REWARD
        # Bytes beyond the three fields are reserved and unparsed (T4.8c: 26
        # zero bytes on every account read so far) — not validated further.
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
        creator_fee_bps=creator_fee_bps,
        can_edit_creator_fee=can_edit_creator_fee,
        is_holder_reward=is_holder_reward,
        layout=layout,
    )


__all__ = [
    "LAYOUT_LEGACY",
    "LAYOUT_WITH_HOLDER_REWARD",
    "NATIVE_SOL_QUOTE_MINT",
    "PUMP_PROGRAM_ID",
    "BondingCurveAccount",
    "decode_bonding_curve_account",
]
