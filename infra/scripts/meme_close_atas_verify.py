"""Pure verifier of a "close empty token accounts" message (T4.77) — runs on
the compiled legacy ``Message`` **before** ``meme_close_atas_send`` signs it,
the way ``hunter_meme_executor.spot_verify`` guards the Jupiter path and
``hunter_exchanges.pumpfun.verify._close_ata`` guards the executor's own
full-sell ``CloseAccount`` (T4.46).

What is allowed, and nothing else:

- exactly one required signature, and it is the wallet (the payer);
- ComputeBudget ``SetComputeUnitLimit`` (index 2) and ``SetComputeUnitPrice``
  (index 3), at most one of each, no accounts, and ``limit × price`` at or
  under ``MAX_PRIORITY_FEE_LAMPORTS``;
- SPL **Token program** (classic) ``CloseAccount`` — ``data == b"\\x09"``
  exactly (a ``Transfer`` is 3, ``Approve`` 4, ``SetAuthority`` 6, ``Burn``
  8; a padded ``\\x09\\x00`` is not a ``CloseAccount``), three accounts:
  ``[account (writable, in the plan), destination == wallet (writable),
  authority == wallet (signer)]``, no account closed twice, at most
  ``MAX_CLOSES_PER_BATCH`` and at least one.

Token-2022 is refused by name here on purpose: the script lists Token-2022
accounts as ``skipped:token_2022`` and never builds a close for them, so a
Token-2022 ``CloseAccount`` in the message can only mean the builder was
changed under the verifier. Anything else — System ``Transfer``, an
Associated Token ``Create``, any DEX — is ``program_not_allowed:<id>``.

No I/O, no clock, no network: ``(message, wallet, allowed_accounts) ->
tuple[closed accounts]`` or :class:`CloseAtasRefused`.
"""

from __future__ import annotations

import struct

from hunter_exchanges.pumpfun.solana_codec import (
    COMPUTE_BUDGET_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    CompiledInstruction,
    Message,
)

__all__ = [
    "CLOSE_ACCOUNT_DATA",
    "MAX_CLOSES_PER_BATCH",
    "MAX_PRIORITY_FEE_LAMPORTS",
    "CloseAtasRefused",
    "priority_fee_lamports",
    "verify_close_atas_message",
]

CLOSE_ACCOUNT_DATA = bytes([9])
MAX_CLOSES_PER_BATCH = 8
MAX_PRIORITY_FEE_LAMPORTS = 100_000
_CU_LIMIT_INDEX = 2
_CU_PRICE_INDEX = 3


class CloseAtasRefused(Exception):
    """Named refusal; the caller never signs whatever failed verification."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"close_atas_refused:{reason}")


def priority_fee_lamports(*, compute_unit_limit: int, micro_lamports_per_cu: int) -> int:
    """The priority fee a validator charges: ``ceil(limit × price / 1e6)``."""
    return -(-compute_unit_limit * micro_lamports_per_cu // 1_000_000)


def verify_close_atas_message(
    message: Message, *, wallet: str, allowed_accounts: frozenset[str]
) -> tuple[str, ...]:
    """Return the accounts the message closes, in order, or raise."""
    if message.num_required_signatures != 1 or message.account_keys[0] != wallet:
        raise CloseAtasRefused("signers_not_exactly_wallet")
    keys = message.account_keys
    closed: list[str] = []
    cu_limit: int | None = None
    cu_price: int | None = None
    for ix in message.instructions:
        program = keys[ix.program_id_index]
        if program == COMPUTE_BUDGET_PROGRAM_ID:
            kind, value = _compute_budget(ix)
            if kind == _CU_LIMIT_INDEX:
                if cu_limit is not None:
                    raise CloseAtasRefused("compute_budget_instruction_duplicated")
                cu_limit = value
            else:
                if cu_price is not None:
                    raise CloseAtasRefused("compute_budget_instruction_duplicated")
                cu_price = value
            continue
        if program == TOKEN_PROGRAM_ID:
            account = _close_account(message, ix, wallet=wallet, allowed=allowed_accounts)
            if account in closed:
                raise CloseAtasRefused("close_account_duplicated")
            closed.append(account)
            continue
        raise CloseAtasRefused(f"program_not_allowed:{program}")
    if not closed:
        raise CloseAtasRefused("no_close_account_instruction")
    if len(closed) > MAX_CLOSES_PER_BATCH:
        raise CloseAtasRefused(f"too_many_close_instructions:{len(closed)}>{MAX_CLOSES_PER_BATCH}")
    if cu_limit is not None and cu_price is not None:
        fee = priority_fee_lamports(compute_unit_limit=cu_limit, micro_lamports_per_cu=cu_price)
        if fee > MAX_PRIORITY_FEE_LAMPORTS:
            raise CloseAtasRefused(f"priority_fee_above_cap:{fee}>{MAX_PRIORITY_FEE_LAMPORTS}")
    elif cu_price is not None:
        # A price with no explicit limit is charged on the runtime default
        # (200k CU per instruction) — refuse rather than guess the fee.
        raise CloseAtasRefused("compute_unit_price_without_limit")
    return tuple(closed)


def _compute_budget(ix: CompiledInstruction) -> tuple[int, int]:
    if ix.account_indexes:
        raise CloseAtasRefused("compute_budget_instruction_has_accounts")
    if len(ix.data) == 5 and ix.data[0] == _CU_LIMIT_INDEX:
        return _CU_LIMIT_INDEX, struct.unpack("<I", ix.data[1:])[0]
    if len(ix.data) == 9 and ix.data[0] == _CU_PRICE_INDEX:
        return _CU_PRICE_INDEX, struct.unpack("<Q", ix.data[1:])[0]
    raise CloseAtasRefused("compute_budget_instruction_unknown")


def _close_account(
    message: Message, ix: CompiledInstruction, *, wallet: str, allowed: frozenset[str]
) -> str:
    if ix.data != CLOSE_ACCOUNT_DATA:
        raise CloseAtasRefused("token_instruction_not_close_account")
    if len(ix.account_indexes) != 3:
        raise CloseAtasRefused("close_account_accounts_not_three")
    account_ix, destination_ix, authority_ix = ix.account_indexes
    keys = message.account_keys
    if keys[destination_ix] != wallet:
        raise CloseAtasRefused("close_destination_not_wallet")
    if keys[authority_ix] != wallet or not message.is_signer(authority_ix):
        raise CloseAtasRefused("close_authority_not_wallet")
    account = keys[account_ix]
    if account == wallet:
        raise CloseAtasRefused("close_account_is_wallet")
    if account not in allowed:
        raise CloseAtasRefused(f"close_account_not_in_plan:{account[:8]}")
    if not message.is_writable(account_ix):
        raise CloseAtasRefused("close_account_not_writable")
    return account
