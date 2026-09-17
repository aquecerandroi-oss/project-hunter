"""Rent accounting for a pump.fun transaction (T4.46, R43).

A buy's wallet funds two ``system::createAccount``s it never sees named: the
mint's own ATA (Token-2022 or classic, per coin) and — once per wallet — the
``user_volume_accumulator`` PDA. A full sell's ``CloseAccount`` (T4.46's own
builder addition, ``tx.build_close_ata_instruction``) earns the ATA rent back.
Every function here reads either ``getTransaction`` encoding this repo's RPC
clients use: the raw ``encoding: json`` instruction ``data`` (the System
Program's own bytes: ``u32 index=0, u64 lamports, u64 space, pubkey owner``,
confirmed byte-for-byte against R43's real fixture) or ``jsonParsed``'s
``info`` convenience — never assumed, never guessed by PDA.

Kept out of ``wallet_fills.py`` only to fit the repo's file-size budget: every
function here takes the caller's own ``keys`` (``wallet_fills._account_keys``)
instead of recomputing them, so there is exactly one reader of account keys
in the package.
"""

from __future__ import annotations

from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import (
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    b58decode,
)
from hunter_exchanges.pumpfun.tx import user_volume_accumulator_address

__all__ = ["ata_close_refund", "rent_funded_by", "rent_labels"]

_CLOSE_ACCOUNT_DATA = bytes([9])
_TOKEN_PROGRAMS = frozenset({TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID})


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _create_account_rent(ix: Any, keys: list[str], wallet: str) -> tuple[str, int] | None:
    """One ``system::createAccount`` the wallet funded, from either encoding:
    ``jsonParsed``'s own ``info`` when present, else the raw ``encoding: json``
    instruction data."""
    ix = _obj(ix)
    parsed_raw = ix.get("parsed")
    if isinstance(parsed_raw, dict):
        parsed = cast(dict[str, Any], parsed_raw)
        if parsed.get("type") != "createAccount":
            return None
        info = _obj(parsed.get("info"))
        if info.get("source") != wallet:
            return None
        new_account = str(info.get("newAccount", ""))
        try:
            lamports = int(info["lamports"])
        except (KeyError, TypeError, ValueError):
            return None
        return (new_account, lamports) if new_account else None
    program_index, accounts, data = (
        ix.get("programIdIndex"),
        _seq(ix.get("accounts")),
        ix.get("data"),
    )
    if (
        not isinstance(program_index, int)
        or not (0 <= program_index < len(keys))
        or keys[program_index] != SYSTEM_PROGRAM_ID
        or len(accounts) < 2
        or not isinstance(data, str)
    ):
        return None
    source_index, new_index = accounts[0], accounts[1]
    if not (isinstance(source_index, int) and isinstance(new_index, int)):
        return None
    if not (0 <= source_index < len(keys)) or not (0 <= new_index < len(keys)):
        return None
    if keys[source_index] != wallet:
        return None
    try:
        raw = b58decode(data)
    except (ValueError, KeyError):
        return None
    if len(raw) < 12 or int.from_bytes(raw[:4], "little") != 0:
        return None
    return keys[new_index], int.from_bytes(raw[4:12], "little")


def rent_funded_by(tx: dict[str, Any], keys: list[str], wallet: str) -> dict[str, int]:
    """``new account -> lamports`` for every ``system::createAccount`` the wallet
    paid for (R43): the payer's own words, ``jsonParsed`` or raw ``encoding:
    json`` alike — no program list, no PDA guessing."""
    meta = _obj(tx.get("meta"))
    rent: dict[str, int] = {}
    for group in _seq(meta.get("innerInstructions")):
        for ix in _seq(_obj(group).get("instructions")):
            entry = _create_account_rent(ix, keys, wallet)
            if entry is None:
                continue
            new_account, lamports = entry
            rent[new_account] = rent.get(new_account, 0) + lamports
    return rent


def rent_labels(tx: dict[str, Any], keys: list[str], wallet: str) -> tuple[int | None, int | None]:
    """``(ata_rent_lamports, account_rent_lamports)`` — the one-time
    ``user_volume_accumulator`` PDA named by address, everything else the wallet
    funded (the mint's ATA, on a buy) summed as the ATA rent."""
    rent = dict(rent_funded_by(tx, keys, wallet))
    if not rent:
        return None, None
    account_rent = rent.pop(user_volume_accumulator_address(wallet), None)
    ata_rent = sum(rent.values()) if rent else None
    return ata_rent, account_rent


def _closed_account_index(ix: Any, keys: list[str], wallet: str) -> int | None:
    """The key-list index of a wallet-owned SPL Token account an SPL Token
    ``CloseAccount`` drained to that same wallet — ``jsonParsed`` or raw."""
    ix = _obj(ix)
    parsed_raw = ix.get("parsed")
    if isinstance(parsed_raw, dict):
        parsed = cast(dict[str, Any], parsed_raw)
        if parsed.get("type") != "closeAccount":
            return None
        info = _obj(parsed.get("info"))
        if info.get("owner") != wallet or info.get("destination") != wallet:
            return None
        try:
            return keys.index(str(info.get("account", "")))
        except ValueError:
            return None
    program_index, accounts, data = (
        ix.get("programIdIndex"),
        _seq(ix.get("accounts")),
        ix.get("data"),
    )
    if (
        not isinstance(program_index, int)
        or not (0 <= program_index < len(keys))
        or keys[program_index] not in _TOKEN_PROGRAMS
        or len(accounts) < 3
        or not isinstance(data, str)
    ):
        return None
    account_index, dest_index, owner_index = accounts[0], accounts[1], accounts[2]
    if not all(isinstance(i, int) for i in (account_index, dest_index, owner_index)):
        return None
    if not all(0 <= i < len(keys) for i in (account_index, dest_index, owner_index)):
        return None
    if keys[dest_index] != wallet or keys[owner_index] != wallet:
        return None
    try:
        raw = b58decode(data)
    except (ValueError, KeyError):
        return None
    return account_index if raw == _CLOSE_ACCOUNT_DATA else None


def ata_close_refund(tx: dict[str, Any], keys: list[str], wallet: str) -> int | None:
    """The lamports an SPL Token ``CloseAccount`` returned to ``wallet`` — the
    ATA rent coming back on a full sell (T4.46). Read from the closed account's
    own ``preBalances`` entry (it is rent-only the instant before the close, and
    ``0`` after): no assumption about which account is a memecoin ATA beyond
    ``owner == destination == wallet``, which is all the executor ever builds."""
    meta = _obj(tx.get("meta"))
    pre = _seq(meta.get("preBalances"))
    message = _obj(_obj(tx.get("transaction")).get("message"))
    lists = [_seq(message.get("instructions"))]
    lists += [
        _seq(_obj(group).get("instructions")) for group in _seq(meta.get("innerInstructions"))
    ]
    for ix_list in lists:
        for ix in ix_list:
            index = _closed_account_index(ix, keys, wallet)
            if index is None:
                continue
            try:
                return int(pre[index])
            except (IndexError, TypeError, ValueError):
                continue
    return None
