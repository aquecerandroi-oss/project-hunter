"""The transaction verifier of ``docs/RISK_ENGINE_MEME.md`` §9.1 — refuse, don't warn.

Before a message is signed it is deserialized, its instructions are classified,
and then the **whole message is rebuilt** from the approved intent with the same
builder (``tx.build_trade_message``) and compared byte for byte. Anything else is
an :class:`UnverifiedTransaction` with a named reason:

1. every program invoked is on the allowlist (§1 — pump, ComputeBudget, the
   associated-token program for the buyer's own ATA, System only for a Jito tip);
2. the only signer is our wallet, at index 0, and nothing else signs;
3. no SOL leaves the wallet except through the pump instruction (curve, fee
   recipients from ``Global``) and, when the intent allows one, a tip to the
   named Jito account within the cap;
4. ``amount`` and ``max_sol_cost``/``min_sol_output`` are exactly the intent's —
   the rebuilt instruction is compared whole (accounts, flags, data);
5. compute-unit limit and price are within the decision's ceilings;
6. a blockhash is present and, when the caller knows which one it fetched, it is
   that one.

The verifier is pure: bytes and dataclasses in, a :class:`VerifiedTrade` out.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount
from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    Instruction,
    Message,
    decompile_message,
    deserialize_message,
    serialize_message,
)
from hunter_exchanges.pumpfun.tx import (
    TradeIntent,
    build_buy_instruction,
    build_sell_instruction,
    build_trade_message,
    create_ata_idempotent,
    jito_tip_transfer,
)

__all__ = ["ExecutionCaps", "UnverifiedTransaction", "VerifiedTrade", "verify_trade_message"]

_ZERO_BLOCKHASH = "11111111111111111111111111111111"


class UnverifiedTransaction(Exception):
    """Named refusal; the message never carries key material or the full transaction."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__(f"unverified_transaction:{reason}" + (f" ({detail})" if detail else ""))


@dataclass(frozen=True, slots=True)
class ExecutionCaps:
    """Ceilings the approved decision carries (§3.1: ``max_priority_fee_*``, ``max_jito_tip_sol``)."""

    max_compute_unit_limit: int
    max_compute_unit_price_micro_lamports: int
    max_jito_tip_lamports: int = 0
    jito_tip_account: str | None = None


@dataclass(frozen=True, slots=True)
class VerifiedTrade:
    message: Message
    trade: Instruction
    compute_unit_limit: int
    compute_unit_price_micro_lamports: int
    jito_tip_lamports: int
    creates_user_ata: bool


def _compute_budget(ix: Instruction) -> tuple[str, int]:
    if ix.accounts:
        raise UnverifiedTransaction("compute_budget_with_accounts")
    if len(ix.data) == 5 and ix.data[0] == 2:
        return "limit", struct.unpack("<I", ix.data[1:5])[0]
    if len(ix.data) == 9 and ix.data[0] == 3:
        return "price", struct.unpack("<Q", ix.data[1:9])[0]
    raise UnverifiedTransaction("compute_budget_unknown_instruction")


def _system_transfer(ix: Instruction, intent: TradeIntent, caps: ExecutionCaps) -> int:
    if len(ix.data) != 12 or ix.data[:4] != b"\x02\x00\x00\x00" or len(ix.accounts) != 2:
        raise UnverifiedTransaction("system_instruction_not_a_transfer")
    lamports = struct.unpack("<Q", ix.data[4:12])[0]
    source, destination = ix.accounts
    if source.pubkey != intent.user or not source.is_signer:
        raise UnverifiedTransaction("transfer_source_not_wallet")
    if caps.jito_tip_account is None or destination.pubkey != caps.jito_tip_account:
        raise UnverifiedTransaction("transfer_destination_not_tip_account", destination.pubkey)
    if lamports <= 0 or lamports > caps.max_jito_tip_lamports:
        raise UnverifiedTransaction(
            "jito_tip_above_cap", f"{lamports} > {caps.max_jito_tip_lamports}"
        )
    return lamports


@dataclass(slots=True)
class _Seen:
    trade: Instruction | None = None
    limit: int | None = None
    price: int | None = None
    tip: int = 0
    creates_ata: bool = False


def _classify(
    instructions: tuple[Instruction, ...], intent: TradeIntent, caps: ExecutionCaps
) -> _Seen:
    seen = _Seen()
    for ix in instructions:
        if ix.program_id == COMPUTE_BUDGET_PROGRAM_ID:
            kind, value = _compute_budget(ix)
            if kind == "limit":
                if seen.limit is not None:
                    raise UnverifiedTransaction("duplicate_compute_unit_limit")
                seen.limit = value
            else:
                if seen.price is not None:
                    raise UnverifiedTransaction("duplicate_compute_unit_price")
                seen.price = value
        elif ix.program_id == PUMP_PROGRAM_ID:
            if seen.trade is not None:
                raise UnverifiedTransaction("more_than_one_trade_instruction")
            seen.trade = ix
        elif ix.program_id == ASSOCIATED_TOKEN_PROGRAM_ID:
            if seen.creates_ata:
                raise UnverifiedTransaction("more_than_one_ata_instruction")
            seen.creates_ata = True
        elif ix.program_id == SYSTEM_PROGRAM_ID:
            if seen.tip:
                raise UnverifiedTransaction("more_than_one_transfer")
            seen.tip = _system_transfer(ix, intent, caps)
        else:
            raise UnverifiedTransaction("program_not_allowed", ix.program_id)
    return seen


def verify_trade_message(
    message_bytes: bytes,
    intent: TradeIntent,
    global_account: GlobalAccount,
    caps: ExecutionCaps,
    *,
    expected_blockhash: str | None = None,
) -> VerifiedTrade:
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

    actual = decompile_message(message)
    seen = _classify(actual, intent, caps)
    if seen.trade is None:
        raise UnverifiedTransaction("trade_instruction_missing")
    if seen.limit is None or seen.price is None:
        raise UnverifiedTransaction("compute_budget_missing")
    if seen.limit > caps.max_compute_unit_limit:
        raise UnverifiedTransaction(
            "compute_unit_limit_above_cap", f"{seen.limit} > {caps.max_compute_unit_limit}"
        )
    if seen.price > caps.max_compute_unit_price_micro_lamports:
        raise UnverifiedTransaction(
            "compute_unit_price_above_cap",
            f"{seen.price} > {caps.max_compute_unit_price_micro_lamports}",
        )

    # Rebuild the whole message from the intent and compare bytes.
    expected_trade = (
        build_buy_instruction(intent, global_account)
        if intent.side == "buy"
        else build_sell_instruction(intent, global_account)
    )
    expected = build_trade_message(
        expected_trade,
        payer=intent.user,
        recent_blockhash=message.recent_blockhash,
        compute_unit_limit=seen.limit,
        compute_unit_price_micro_lamports=seen.price,
        create_user_ata=(
            create_ata_idempotent(
                payer=intent.user,
                owner=intent.user,
                mint=intent.mint,
                token_program=intent.token_program,
            )
            if seen.creates_ata
            else None
        ),
        jito_tip=(
            jito_tip_transfer(
                payer=intent.user, tip_account=str(caps.jito_tip_account), lamports=seen.tip
            )
            if seen.tip
            else None
        ),
    )
    if serialize_message(expected) != message_bytes:
        raise UnverifiedTransaction(*_name_the_difference(actual, decompile_message(expected)))
    return VerifiedTrade(
        message=message,
        trade=seen.trade,
        compute_unit_limit=seen.limit,
        compute_unit_price_micro_lamports=seen.price,
        jito_tip_lamports=seen.tip,
        creates_user_ata=seen.creates_ata,
    )


def _name_the_difference(
    actual: tuple[Instruction, ...], expected: tuple[Instruction, ...]
) -> tuple[str, str]:
    if len(actual) != len(expected):
        return "instruction_count_differs", f"{len(actual)} != {len(expected)}"
    for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
        if a == e:
            continue
        if a.program_id != e.program_id:
            return "instruction_order_differs", f"instruction[{index}]"
        if a.program_id == PUMP_PROGRAM_ID:
            return "trade_instruction_differs_from_intent", _diff(a, e)
        if a.program_id == ASSOCIATED_TOKEN_PROGRAM_ID:
            return "ata_instruction_not_ours", _diff(a, e)
        return "instruction_differs", f"instruction[{index}] {_diff(a, e)}"
    return "message_bytes_differ", "same instructions, different header or keys"


def _diff(actual: Instruction, expected: Instruction) -> str:
    if actual.data != expected.data:
        return "data"
    if len(actual.accounts) != len(expected.accounts):
        return f"account_count {len(actual.accounts)} != {len(expected.accounts)}"
    for index, (a, e) in enumerate(zip(actual.accounts, expected.accounts, strict=True)):
        if a != e:
            return f"account[{index}]"
    return "unknown"
