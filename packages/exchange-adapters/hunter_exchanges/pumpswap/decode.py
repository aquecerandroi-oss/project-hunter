"""``GlobalConfig`` and ``Pool`` account layouts — read from the program's own
on-chain IDL account, not from memory (T4.29a).

**Source of truth, in order of freshness:** (1) the PumpSwap program's own
on-chain Anchor IDL account, read live 2026-09-16 via ``getAccountInfo`` on
``5fLnXNNoZcZt9Qku6HARM3un3Ttm2cGsR7gN9Zp1R7h3`` (the ``createWithSeed(
find_program_address([], pAMMBay...), "anchor:idl", pAMMBay...)`` address —
same derivation T4.2e used for the Mayhem program), decompressed (8-byte
discriminator + 32-byte authority + u32 length + zlib body, standard Anchor
IDL account format) into
``tests/fixtures/pumpswap/t429a_idl_pump_amm_onchain.json`` (sha256
``e16ac8008908911575241a25cad33bed8d2da2153f0d726790065fd467b90ff4``,
slot 447585704). (2) ``pump-fun/pump-public-docs`` GitHub ``idl/pump_amm.json``
at ``main`` (commit ``81091419e4457566469d4e2a27f64ed84d42419c``, read
2026-09-16, sha256
``2091433899b07d003d98118ae6cd3c628960fd393b40710b6e15bce6d0e7f2d1``) —
**ahead** of the on-chain account (adds ``boost_authority``/``boost_enabled``
to ``GlobalConfig``, ``creator_fee_configurable``/``max_configurable_creator_fee_bps``
and, on ``Pool``, ``virtual_quote_reserves``/``creator_fee_bps``/
``can_edit_creator_fee``/``is_holder_reward`` — the same "IDL got ahead of the
account" pattern T4.8/T4.8c already found for the Pump program). The on-chain
account is the one that governs what today's real transactions actually check,
so this module decodes against **it**, exactly mirroring
``hunter_exchanges.pumpfun.decode``'s legacy/extended fallback for
``BondingCurve``.

**Confirmed byte-for-byte against 3 real migrated pools, live, same session**
(``tests/fixtures/pumpswap/t429a_rpc_pools_raw.json``, slot 447585957):
every one of them is **301 bytes** — the on-chain IDL's 12 declared ``Pool``
fields (245 bytes with the 8-byte discriminator) plus room for the GitHub
``main`` IDL's ``virtual_quote_reserves`` (i128, 16 bytes) +
``creator_fee_bps`` (u64) + ``can_edit_creator_fee`` (bool) +
``is_holder_reward`` (bool) = 271 bytes, plus 30 reserved/unparsed tail bytes
(``extend_account``-style headroom, same as ``BondingCurve``'s tail).
**Correction to ``docs/PUMPFUN-ONCHAIN.md`` §2.2**, which read a static example
and said "hoje ``virtual_quote_reserves=0`` em todo pool": two of the three
pools read live today carry a **non-zero** ``virtual_quote_reserves``
(17 584 505 289 and 17 584 505 291 lamports; the Mayhem pool of the three reads
0) — the field is not dormant, ``quote.py`` never assumes it is zero.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.solana_codec import b58encode

__all__ = [
    "GLOBAL_CONFIG_ADDRESS",
    "LAYOUT_BASE",
    "LAYOUT_WITH_VIRTUAL_QUOTE_RESERVES",
    "PUMPSWAP_PROGRAM_ID",
    "WSOL_MINT",
    "GlobalConfig",
    "Pool",
    "decode_global_config",
    "decode_pool_account",
]

#: Confirmed live (T4.29a): owner of every Pool/GlobalConfig account this
#: package trusts a decode from.
PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"

#: PumpSwap pools hold real SPL token accounts, never native SOL — the quote
#: side of every canonical pool is wrapped SOL (confirmed on all 3 pools read).
WSOL_MINT = "So11111111111111111111111111111111111111112"

#: PDA ``["global_config"]`` — confirmed live 2026-09-16, matches
#: ``docs/PUMPFUN-ONCHAIN.md`` §2.1.
GLOBAL_CONFIG_ADDRESS = "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"

_GLOBAL_CONFIG_DISCRIMINATOR = bytes([149, 8, 156, 202, 160, 252, 176, 217])
_POOL_DISCRIMINATOR = bytes([241, 154, 109, 4, 17, 177, 109, 188])

_POOL_BASE_LEN = 8 + 1 + 2 + 32 * 7 + 8 + 1 + 1  # 245: through is_cashback_coin
_POOL_EXTENDED_FIELDS_LEN = 16 + 8 + 1 + 1  # 26: vqr(i128) + creator_fee_bps + 2 bools

LAYOUT_BASE = "base-245b"
"""What the on-chain IDL account itself declares — no room for the extra 4
GitHub-``main`` fields."""
LAYOUT_WITH_VIRTUAL_QUOTE_RESERVES = "with-vqr-271b"
"""Confirmed present on all 3 pools read live in this task."""


@dataclass(frozen=True, slots=True)
class Pool:
    """Raw (unconverted) ``Pool`` fields — reserves are token/lamport subunits."""

    pool_bump: int
    index: int
    creator: str
    base_mint: str
    quote_mint: str
    lp_mint: str
    pool_base_token_account: str
    pool_quote_token_account: str
    lp_supply: int
    coin_creator: str
    is_mayhem_mode: bool
    is_cashback_coin: bool
    virtual_quote_reserves: int = 0
    creator_fee_bps: int = 0
    can_edit_creator_fee: bool = False
    is_holder_reward: bool = False
    layout: str = LAYOUT_BASE


@dataclass(frozen=True, slots=True)
class GlobalConfig:
    """Only the fields this package needs (fees + the account order up to
    ``coin_creator_fee_basis_points``); the tail (admin authorities, Mayhem/
    cashback/buyback recipients, ``boost_*``) is not decoded — nothing here
    reads them."""

    admin: str
    lp_fee_basis_points: int
    protocol_fee_basis_points: int
    disable_flags: int
    protocol_fee_recipients: tuple[str, ...]
    coin_creator_fee_basis_points: int

    @property
    def total_fee_basis_points(self) -> int:
        return (
            self.lp_fee_basis_points
            + self.protocol_fee_basis_points
            + (self.coin_creator_fee_basis_points)
        )


def decode_global_config(data_base64: str, *, owner: str) -> GlobalConfig:
    if owner != PUMPSWAP_PROGRAM_ID:
        raise MalformedMessage(
            f"GlobalConfig owner {owner!r} is not the PumpSwap program", exchange="pumpswap"
        )
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"GlobalConfig data is not base64: {exc}", exchange="pumpswap"
        ) from exc
    if raw[:8] != _GLOBAL_CONFIG_DISCRIMINATOR:
        raise MalformedMessage("wrong GlobalConfig discriminator", exchange="pumpswap")
    off = 8
    try:
        admin = b58encode(raw[off : off + 32])
        off += 32
        lp_fee_basis_points = struct.unpack_from("<Q", raw, off)[0]
        off += 8
        protocol_fee_basis_points = struct.unpack_from("<Q", raw, off)[0]
        off += 8
        disable_flags = raw[off]
        off += 1
        protocol_fee_recipients = tuple(
            b58encode(raw[off + i * 32 : off + i * 32 + 32]) for i in range(8)
        )
        off += 32 * 8
        coin_creator_fee_basis_points = struct.unpack_from("<Q", raw, off)[0]
    except (struct.error, IndexError) as exc:
        raise MalformedMessage(f"GlobalConfig truncated: {exc}", exchange="pumpswap") from exc
    return GlobalConfig(
        admin=admin,
        lp_fee_basis_points=lp_fee_basis_points,
        protocol_fee_basis_points=protocol_fee_basis_points,
        disable_flags=disable_flags,
        protocol_fee_recipients=protocol_fee_recipients,
        coin_creator_fee_basis_points=coin_creator_fee_basis_points,
    )


def decode_pool_account(data_base64: str, *, owner: str) -> Pool:
    """Decode a ``getAccountInfo`` base64 payload into raw ``Pool`` fields.

    Refuses a wrong owner, wrong discriminator, invalid boolean or a body
    shorter than the base 245 bytes instead of guessing at a partial struct —
    the same discipline ``hunter_exchanges.pumpfun.decode`` uses.
    """
    if owner != PUMPSWAP_PROGRAM_ID:
        raise MalformedMessage(
            f"account owner {owner!r} is not the PumpSwap program", exchange="pumpswap"
        )
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedMessage(
            f"Pool account data is not base64: {exc}", exchange="pumpswap"
        ) from exc
    if len(raw) < _POOL_BASE_LEN:
        raise MalformedMessage(
            f"Pool account too short: {len(raw)} bytes, need >= {_POOL_BASE_LEN}",
            exchange="pumpswap",
        )
    if raw[:8] != _POOL_DISCRIMINATOR:
        raise MalformedMessage("wrong Pool discriminator", exchange="pumpswap")
    off = 8
    pool_bump = raw[off]
    off += 1
    index = struct.unpack_from("<H", raw, off)[0]
    off += 2
    pubkeys: list[str] = []
    for _ in range(6):
        pubkeys.append(b58encode(raw[off : off + 32]))
        off += 32
    creator, base_mint, quote_mint, lp_mint, pool_base_ta, pool_quote_ta = pubkeys
    lp_supply = struct.unpack_from("<Q", raw, off)[0]
    off += 8
    coin_creator = b58encode(raw[off : off + 32])
    off += 32
    if raw[off] not in (0, 1) or raw[off + 1] not in (0, 1):
        raise MalformedMessage("invalid Pool boolean", exchange="pumpswap")
    is_mayhem_mode = bool(raw[off])
    off += 1
    is_cashback_coin = bool(raw[off])
    off += 1
    trailing = len(raw) - off
    if trailing < _POOL_EXTENDED_FIELDS_LEN:
        virtual_quote_reserves, creator_fee_bps, can_edit_creator_fee, is_holder_reward, layout = (
            0,
            0,
            False,
            False,
            LAYOUT_BASE,
        )
    else:
        if raw[off + 16 + 8] not in (0, 1) or raw[off + 16 + 8 + 1] not in (0, 1):
            raise MalformedMessage("invalid Pool boolean", exchange="pumpswap")
        virtual_quote_reserves = int.from_bytes(raw[off : off + 16], "little", signed=True)
        creator_fee_bps = struct.unpack_from("<Q", raw, off + 16)[0]
        can_edit_creator_fee = bool(raw[off + 16 + 8])
        is_holder_reward = bool(raw[off + 16 + 8 + 1])
        layout = LAYOUT_WITH_VIRTUAL_QUOTE_RESERVES
    return Pool(
        pool_bump=pool_bump,
        index=index,
        creator=creator,
        base_mint=base_mint,
        quote_mint=quote_mint,
        lp_mint=lp_mint,
        pool_base_token_account=pool_base_ta,
        pool_quote_token_account=pool_quote_ta,
        lp_supply=lp_supply,
        coin_creator=coin_creator,
        is_mayhem_mode=is_mayhem_mode,
        is_cashback_coin=is_cashback_coin,
        virtual_quote_reserves=virtual_quote_reserves,
        creator_fee_bps=creator_fee_bps,
        can_edit_creator_fee=can_edit_creator_fee,
        is_holder_reward=is_holder_reward,
        layout=layout,
    )
