"""The two tokens of a PumpSwap pool, per event (wave 1b of H-030).

A PumpSwap ``BuyEvent``/``SellEvent`` names the pool and the user, not the pool's mints. The swap
instruction that emitted it does: its accounts are, in the program's own IDL (``buy``,
``buy_exact_quote_in``, ``sell``), ``0 pool, 1 user, 2 global_config, 3 base_mint, 4 quote_mint,
5 user_base_token_account, 6 user_quote_token_account, 7 pool_base_token_account, 8
pool_quote_token_account``. The instruction may be top level or reached by CPI through a router; both
are visible in a ``getTransaction`` result, so this module works from one (the logs alone, as
delivered by ``logsSubscribe``, carry no accounts: those records keep their legs unknown).

**Attribution** is by the event's own fields, not by order: an instruction belongs to an event when
its accounts 0, 1, 5 and 6 are the event's ``pool``, ``user``, ``user_base_token_account`` and
``user_quote_token_account``. A pool has one pair of mints, so two instructions of the same pool
agree; if they do not, the legs are a **conflict**.

**Cross-check against the chain's own labels.** The token-balance rows of the transaction carry the
``mint`` of every token account they list. Where a row exists for the user's two accounts or the
pool's two vaults, its mint must equal the one the instruction names; a disagreement is a conflict.
(The user's WSOL account is often absent from the rows, a wrapped-SOL account opened and closed in the
same transaction; the pool's vaults never are.)

Unknown is a value, never a guess: no matching instruction (a swap instruction this reader does not
know, a pruned transaction) is **unresolved**; both outcomes are counted by the caller. Pure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Final, Literal, cast

from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.swap_record import SwapRecord
from hunter_exchanges.pumpfun.trade_event_codec import EVENT_CPI_TAG
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID, WSOL_MINT

__all__ = ["attach_pool_legs"]

# Anchor discriminators of the swap instructions (first 8 bytes of the instruction data), IDL.
_SWAP_DISCRIMINATORS: Final = frozenset(
    {
        bytes([102, 6, 61, 18, 1, 218, 235, 234]),  # buy
        bytes([198, 46, 21, 82, 180, 217, 232, 112]),  # buy_exact_quote_in
        bytes([51, 230, 133, 164, 1, 127, 131, 173]),  # sell
    }
)
_POOL, _USER, _BASE_MINT, _QUOTE_MINT = 0, 1, 3, 4
_USER_BASE, _USER_QUOTE, _VAULT_BASE, _VAULT_QUOTE = 5, 6, 7, 8
_MIN_ACCOUNTS: Final = _VAULT_QUOTE + 1


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _keys(transaction: dict[str, Any]) -> list[str]:
    meta = _obj(transaction.get("meta"))
    message = _obj(_obj(transaction.get("transaction")).get("message"))
    loaded = _obj(meta.get("loadedAddresses"))
    keys = [
        *_seq(message.get("accountKeys")),
        *_seq(loaded.get("writable")),
        *_seq(loaded.get("readonly")),
    ]
    return [str(k) for k in keys]


def _swap_instructions(
    transaction: dict[str, Any], keys: list[str]
) -> tuple[list[list[str]], list[list[str]]]:
    """``(known swap instructions, other PumpSwap instructions)`` as account pubkeys, top level and
    inner. The second list (event self-CPIs excluded) holds what this reader does not understand: an
    unknown swap variant such as ``SellV2`` lands there."""
    meta = _obj(transaction.get("meta"))
    message = _obj(_obj(transaction.get("transaction")).get("message"))
    instructions = [*_seq(message.get("instructions"))]
    for group in _seq(meta.get("innerInstructions")):
        instructions += _seq(_obj(group).get("instructions"))
    out: list[list[str]] = []
    other: list[list[str]] = []
    for ix_any in instructions:
        ix = _obj(ix_any)
        program: Any = ix.get("programIdIndex")
        accounts = _seq(ix.get("accounts"))
        if (
            not isinstance(program, int)
            or program >= len(keys)
            or keys[program] != PUMPSWAP_PROGRAM_ID
        ):
            continue
        if not all(isinstance(i, int) and 0 <= i < len(keys) for i in accounts):
            continue
        try:
            data = b58decode(str(ix.get("data", "")))
        except ValueError:
            continue
        if data[:8] in _SWAP_DISCRIMINATORS and len(accounts) >= _MIN_ACCOUNTS:
            out.append([keys[i] for i in accounts])
        elif data[:8] != EVENT_CPI_TAG:
            other.append([keys[i] for i in accounts])
    return out, other


def _mints_by_account(transaction: dict[str, Any], keys: list[str]) -> dict[str, set[str]]:
    """Every mint the transaction's own token-balance rows attach to an account (pre and post)."""
    meta = _obj(transaction.get("meta"))
    out: dict[str, set[str]] = {}
    for side in ("preTokenBalances", "postTokenBalances"):
        for row_any in _seq(meta.get(side)):
            row = _obj(row_any)
            index: Any = row.get("accountIndex")
            mint = row.get("mint")
            if isinstance(index, int) and 0 <= index < len(keys) and isinstance(mint, str):
                out.setdefault(keys[index], set()).add(mint)
    return out


def _legs(
    swap: SwapRecord, instructions: list[list[str]], labels: dict[str, set[str]]
) -> tuple[str, str] | Literal["unresolved", "conflict"]:
    matches = [
        a
        for a in instructions
        if (a[_POOL], a[_USER], a[_USER_BASE], a[_USER_QUOTE])
        == (swap.pool, swap.wallet, swap.user_base_token_account, swap.user_quote_token_account)
    ]
    if not matches:
        return "unresolved"
    pairs = {(a[_BASE_MINT], a[_QUOTE_MINT]) for a in matches}
    if len(pairs) != 1:
        return "conflict"
    base, quote = next(iter(pairs))
    for match in matches:
        for account, expected in (
            (match[_USER_BASE], base),
            (match[_USER_QUOTE], quote),
            (match[_VAULT_BASE], base),
            (match[_VAULT_QUOTE], quote),
        ):
            seen = labels.get(account)
            if seen is not None and seen != {expected}:
                return "conflict"
    return base, quote


def attach_pool_legs(
    transaction: dict[str, Any], swaps: Sequence[SwapRecord]
) -> tuple[tuple[SwapRecord, ...], int, int, int]:
    """``(swaps with their pool legs, unresolved, conflicts, via sibling)`` for one ``getTransaction``
    result.

    ``via sibling`` counts the resolved events that share their pool and user with an instruction this
    reader does not understand (an unknown swap variant such as ``SellV2``): the mints are right by
    construction (one pair per pool) but the unknown invocation only borrows the known one's evidence,
    and which event it emitted is not established. Also counted when the other instruction is merely
    some PumpSwap call on the same pool and user (a deposit, say): conservative.

    A pool record gets ``base_mint``, ``quote_mint`` and ``quote_is_sol`` (decided by the quote mint:
    WSOL or not); a record whose legs are unresolved or in conflict is returned unchanged and counted.
    Curve records pass through. The transaction is not modified."""
    keys = _keys(transaction)
    instructions, others = _swap_instructions(transaction, keys)
    labels = _mints_by_account(transaction, keys)
    out: list[SwapRecord] = []
    unresolved = conflicts = via_sibling = 0
    for swap in swaps:
        if swap.venue != "pool":
            out.append(swap)
            continue
        legs = _legs(swap, instructions, labels)
        if isinstance(legs, str):
            unresolved += legs == "unresolved"
            conflicts += legs == "conflict"
            out.append(swap)
        else:
            base, quote = legs
            via_sibling += any(swap.pool in o and swap.wallet in o for o in others)
            out.append(
                replace(swap, base_mint=base, quote_mint=quote, quote_is_sol=quote == WSOL_MINT)
            )
    return tuple(out), unresolved, conflicts, via_sibling
