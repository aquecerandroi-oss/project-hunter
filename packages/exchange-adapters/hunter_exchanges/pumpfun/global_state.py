"""The pump program's ``Global`` account — fee recipients read from the chain, never typed.

``docs/PUMPFUN-ONCHAIN.md`` §1.1 lists the 25 fields in IDL order; T4.0d read the
account live and T4.8 captured it again
(``tests/fixtures/pumpfun/rpc_global_account_raw.json``). The transaction builder
(``tx.py``) takes a decoded :class:`GlobalAccount` as an *argument*: which
``fee_recipient`` a buy pays, and whether a Mayhem coin pays one of the
*reserved* recipients, is whatever this account says at build time
(``docs/RISK_ENGINE_MEME.md`` §9.1 item 3 — the verifier's allowlist is the
same account, so a recipient that is not in it is an ``unverified_transaction``).
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.solana_codec import b58encode

__all__ = ["GLOBAL_ACCOUNT_ADDRESS", "GlobalAccount", "decode_global_account"]

GLOBAL_ACCOUNT_ADDRESS = "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf"
_DISCRIMINATOR = bytes([167, 232, 232, 177, 200, 108, 114, 127])


@dataclass(frozen=True, slots=True)
class GlobalAccount:
    initialized: bool
    authority: str
    fee_recipient: str
    initial_virtual_token_reserves: int
    initial_virtual_sol_reserves: int
    initial_real_token_reserves: int
    token_total_supply: int
    fee_basis_points: int
    withdraw_authority: str
    enable_migrate: bool
    pool_migration_fee: int
    creator_fee_basis_points: int
    fee_recipients: tuple[str, ...]
    set_creator_authority: str
    admin_set_creator_authority: str
    create_v2_enabled: bool
    whitelist_pda: str
    reserved_fee_recipient: str
    mayhem_mode_enabled: bool
    reserved_fee_recipients: tuple[str, ...]
    is_cashback_enabled: bool
    buyback_fee_recipients: tuple[str, ...]
    buyback_basis_points: int
    initial_virtual_quote_reserves: int
    whitelisted_quote_mints: tuple[str, ...]

    @property
    def normal_fee_recipients(self) -> tuple[str, ...]:
        """The 8 recipients a non-Mayhem coin may pay (``fee_recipient`` is item 0)."""
        return (self.fee_recipient, *self.fee_recipients)

    @property
    def mayhem_fee_recipients(self) -> tuple[str, ...]:
        """The 8 *reserved* recipients a Mayhem coin pays (``reserved_fee_recipient`` is item 0)."""
        return (self.reserved_fee_recipient, *self.reserved_fee_recipients)

    def fee_recipients_for(self, *, is_mayhem_mode: bool) -> tuple[str, ...]:
        return self.mayhem_fee_recipients if is_mayhem_mode else self.normal_fee_recipients


class _Cursor:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.off = len(_DISCRIMINATOR)

    def boolean(self) -> bool:
        byte = self.raw[self.off]
        self.off += 1
        if byte not in (0, 1):
            raise ValueError("bool")
        return bool(byte)

    def u64(self) -> int:
        value = struct.unpack_from("<Q", self.raw, self.off)[0]
        self.off += 8
        return value

    def pubkey(self) -> str:
        value = b58encode(self.raw[self.off : self.off + 32])
        self.off += 32
        return value

    def pubkeys(self, n: int) -> tuple[str, ...]:
        return tuple(self.pubkey() for _ in range(n))


def decode_global_account(data_base64: str, *, owner: str) -> GlobalAccount:
    """Decode a ``getAccountInfo`` (base64) payload of ``Global``; refuses a wrong owner,
    a wrong discriminator or a truncated body instead of guessing."""
    if owner != PUMP_PROGRAM_ID:
        raise MalformedMessage(
            f"Global owner {owner!r} is not the pump program", exchange="pumpfun"
        )
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedMessage(f"Global data is not base64: {exc}", exchange="pumpfun") from exc
    if raw[:8] != _DISCRIMINATOR:
        raise MalformedMessage("wrong Global discriminator", exchange="pumpfun")
    c = _Cursor(raw)
    try:
        return GlobalAccount(
            initialized=c.boolean(),
            authority=c.pubkey(),
            fee_recipient=c.pubkey(),
            initial_virtual_token_reserves=c.u64(),
            initial_virtual_sol_reserves=c.u64(),
            initial_real_token_reserves=c.u64(),
            token_total_supply=c.u64(),
            fee_basis_points=c.u64(),
            withdraw_authority=c.pubkey(),
            enable_migrate=c.boolean(),
            pool_migration_fee=c.u64(),
            creator_fee_basis_points=c.u64(),
            fee_recipients=c.pubkeys(7),
            set_creator_authority=c.pubkey(),
            admin_set_creator_authority=c.pubkey(),
            create_v2_enabled=c.boolean(),
            whitelist_pda=c.pubkey(),
            reserved_fee_recipient=c.pubkey(),
            mayhem_mode_enabled=c.boolean(),
            reserved_fee_recipients=c.pubkeys(7),
            is_cashback_enabled=c.boolean(),
            buyback_fee_recipients=c.pubkeys(8),
            buyback_basis_points=c.u64(),
            initial_virtual_quote_reserves=c.u64(),
            whitelisted_quote_mints=c.pubkeys(1),
        )
    except (struct.error, IndexError, ValueError) as exc:
        raise MalformedMessage(
            f"Global account truncated or malformed: {exc}", exchange="pumpfun"
        ) from exc
