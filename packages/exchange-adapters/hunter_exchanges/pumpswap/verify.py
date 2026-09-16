"""Verifier for a PumpSwap sell message — the §9.1 discipline, PumpSwap edition
(T4.29a). Mirrors ``hunter_exchanges.pumpfun.verify`` exactly: deserialize,
classify every instruction against an allowlist, rebuild the whole message
from the approved intent with this package's own builder, compare byte for
byte. Anything else is an :class:`UnverifiedTransaction` with a named reason.

Allowlist: ``ComputeBudget``, the associated-token program (only for the
wallet's own WSOL ATA), the PumpSwap program (exactly one ``sell``), the SPL
Token program (only a ``CloseAccount`` on the wallet's own WSOL ATA — never a
transfer, never anyone else's account). No Jito tip is modelled: PumpSwap
exits are never bundled in this task's scope.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    Instruction,
    Message,
    associated_token_address,
    decompile_message,
    deserialize_message,
    serialize_message,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID, WSOL_MINT
from hunter_exchanges.pumpswap.tx import PumpSwapSellIntent, build_sell_message

__all__ = [
    "ExecutionCaps",
    "UnverifiedTransaction",
    "VerifiedPumpSwapSell",
    "verify_pumpswap_sell_message",
]

_ZERO_BLOCKHASH = "11111111111111111111111111111111"


class UnverifiedTransaction(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__(f"unverified_transaction:{reason}" + (f" ({detail})" if detail else ""))


@dataclass(frozen=True, slots=True)
class ExecutionCaps:
    """Ceilings the approved decision carries — same shape as
    ``hunter_exchanges.pumpfun.verify.ExecutionCaps``, no Jito tip modelled
    (PumpSwap exits are never bundled in this task's scope)."""

    max_compute_unit_limit: int
    max_compute_unit_price_micro_lamports: int


@dataclass(frozen=True, slots=True)
class VerifiedPumpSwapSell:
    message: Message
    trade: Instruction
    compute_unit_limit: int
    compute_unit_price_micro_lamports: int
    creates_wsol_ata: bool


def _compute_budget(ix: Instruction) -> tuple[str, int]:
    if ix.accounts:
        raise UnverifiedTransaction("compute_budget_with_accounts")
    if len(ix.data) == 5 and ix.data[0] == 2:
        return "limit", struct.unpack("<I", ix.data[1:5])[0]
    if len(ix.data) == 9 and ix.data[0] == 3:
        return "price", struct.unpack("<Q", ix.data[1:9])[0]
    raise UnverifiedTransaction("compute_budget_unknown_instruction")


def verify_pumpswap_sell_message(
    message_bytes: bytes,
    intent: PumpSwapSellIntent,
    *,
    compute_unit_limit_cap: int,
    compute_unit_price_cap_micro_lamports: int,
    expected_blockhash: str | None = None,
) -> VerifiedPumpSwapSell:
    try:
        message = deserialize_message(message_bytes)
    except (ValueError, IndexError) as exc:
        raise UnverifiedTransaction("undecodable_message", str(exc)) from exc
    if message.num_required_signatures != 1 or message.account_keys[0] != intent.user:
        raise UnverifiedTransaction("signer_is_not_our_wallet")
    if message.recent_blockhash == _ZERO_BLOCKHASH:
        raise UnverifiedTransaction("blockhash_missing")
    if expected_blockhash is not None and message.recent_blockhash != expected_blockhash:
        raise UnverifiedTransaction("blockhash_mismatch")

    wsol_ata = associated_token_address(intent.user, WSOL_MINT, token_program=TOKEN_PROGRAM_ID)
    actual = decompile_message(message)
    limit: int | None = None
    price: int | None = None
    trade: Instruction | None = None
    creates_wsol_ata = False
    for ix in actual:
        if ix.program_id == COMPUTE_BUDGET_PROGRAM_ID:
            kind, value = _compute_budget(ix)
            if kind == "limit":
                if limit is not None:
                    raise UnverifiedTransaction("duplicate_compute_unit_limit")
                limit = value
            else:
                if price is not None:
                    raise UnverifiedTransaction("duplicate_compute_unit_price")
                price = value
        elif ix.program_id == PUMPSWAP_PROGRAM_ID:
            if trade is not None:
                raise UnverifiedTransaction("more_than_one_trade_instruction")
            trade = ix
        elif ix.program_id == ASSOCIATED_TOKEN_PROGRAM_ID:
            if creates_wsol_ata:
                raise UnverifiedTransaction("more_than_one_ata_instruction")
            if len(ix.accounts) < 2 or ix.accounts[1].pubkey != wsol_ata:
                raise UnverifiedTransaction("ata_instruction_not_wsol")
            creates_wsol_ata = True
        elif ix.program_id == TOKEN_PROGRAM_ID:
            if len(ix.data) != 1 or ix.data[0] != 9:
                raise UnverifiedTransaction("token_instruction_not_close_account")
            if not ix.accounts or ix.accounts[0].pubkey != wsol_ata:
                raise UnverifiedTransaction("close_account_not_wsol")
            if ix.accounts[1].pubkey != intent.user:
                raise UnverifiedTransaction("close_account_destination_not_wallet")
        else:
            raise UnverifiedTransaction("program_not_allowed", ix.program_id)
    if trade is None:
        raise UnverifiedTransaction("trade_instruction_missing")
    if limit is None or price is None:
        raise UnverifiedTransaction("compute_budget_missing")
    if limit > compute_unit_limit_cap:
        raise UnverifiedTransaction(
            "compute_unit_limit_above_cap", f"{limit} > {compute_unit_limit_cap}"
        )
    if price > compute_unit_price_cap_micro_lamports:
        raise UnverifiedTransaction(
            "compute_unit_price_above_cap", f"{price} > {compute_unit_price_cap_micro_lamports}"
        )

    expected = build_sell_message(
        intent,
        payer=intent.user,
        recent_blockhash=message.recent_blockhash,
        compute_unit_limit=limit,
        compute_unit_price_micro_lamports=price,
        create_wsol_ata=creates_wsol_ata,
    )
    if serialize_message(expected) != message_bytes:
        raise UnverifiedTransaction("message_bytes_differ", "rebuilt message does not match")
    return VerifiedPumpSwapSell(
        message=message,
        trade=trade,
        compute_unit_limit=limit,
        compute_unit_price_micro_lamports=price,
        creates_wsol_ata=creates_wsol_ata,
    )
