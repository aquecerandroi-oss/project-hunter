"""Wave 1a of H-030: helpers over the REAL ``getTransaction`` fixtures of ``tests/fixtures/t1a_*``.

Provenance of every fixture (signature, slot, block time, why it was picked) is
``tests/fixtures/t1a_provenance.json``; ``test_t1a_provenance.py`` keeps the two honest. Nothing
here decodes an event: the helpers read the *chain's own* evidence (instruction accounts, token
balance deltas, inner-instruction payload bytes) so that a test can check a decoder against
something it did not produce.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from hunter_exchanges.pumpfun.solana_codec import b58decode

FIXTURES = Path(__file__).parents[1] / "fixtures"
EVENT_CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")
# Anchor instruction discriminators of the PumpSwap swap instructions (first 8 bytes of ix data).
AMM_BUY_IX = bytes.fromhex("66063d1201daebea")
AMM_BUY_EXACT_QUOTE_IN_IX = bytes.fromhex("c62e1552b4d9e870")


def load(relative: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / relative).read_text()))


def tx_fixture(directory: str, name: str) -> dict[str, Any]:
    return load(f"{directory}/{name}")


def account_keys(tx: dict[str, Any]) -> list[str]:
    """Static keys, then the loaded (lookup-table) ones, in the order the balances index."""
    meta = cast(dict[str, Any], tx["meta"])
    loaded = cast(dict[str, list[str]], meta.get("loadedAddresses") or {})
    keys = list(cast(list[str], tx["transaction"]["message"]["accountKeys"]))
    return keys + loaded.get("writable", []) + loaded.get("readonly", [])


def all_instructions(tx: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """``("top"|"inner", instruction)`` for every instruction of the transaction."""
    out: list[tuple[str, dict[str, Any]]] = [
        ("top", ix)
        for ix in cast(list[dict[str, Any]], tx["transaction"]["message"]["instructions"])
    ]
    for group in cast(list[dict[str, Any]], tx["meta"]["innerInstructions"]):
        out += [("inner", ix) for ix in cast(list[dict[str, Any]], group["instructions"])]
    return out


def inner_event_payloads(tx: dict[str, Any], program: str, discriminator: bytes) -> list[bytes]:
    """The event bodies (after the event-CPI tag) the program emitted as self-CPI inner
    instructions, in order — the structured twin of the ``Program data:`` log lines."""
    keys = account_keys(tx)
    out: list[bytes] = []
    for kind, ix in all_instructions(tx):
        if kind != "inner" or keys[ix["programIdIndex"]] != program:
            continue
        data = b58decode(str(ix["data"]))
        if data[:8] == EVENT_CPI_TAG and data[8:16] == discriminator:
            out.append(data[8:])
    return out


def swap_instruction_accounts(
    tx: dict[str, Any], program: str, instruction_discriminators: tuple[bytes, ...]
) -> list[str]:
    """The account list (as pubkeys) of the program's first instruction whose data starts with one
    of ``instruction_discriminators`` — top-level or reached through a router."""
    keys = account_keys(tx)
    for _, ix in all_instructions(tx):
        if keys[ix["programIdIndex"]] != program:
            continue
        if b58decode(str(ix["data"]))[:8] in instruction_discriminators:
            return [keys[i] for i in cast(list[int], ix["accounts"])]
    raise AssertionError("no such swap instruction")


def token_delta(tx: dict[str, Any], address: str) -> int:
    """post - pre of an SPL token account's balance, 0 when it has no entry (raw atoms)."""
    index = account_keys(tx).index(address)
    meta = cast(dict[str, Any], tx["meta"])

    def amount(rows: list[dict[str, Any]]) -> int:
        match = [row for row in rows if row["accountIndex"] == index]
        return int(match[0]["uiTokenAmount"]["amount"]) if match else 0

    return amount(meta["postTokenBalances"]) - amount(meta["preTokenBalances"])


def log_event_payloads(tx: dict[str, Any], program: str) -> list[bytes]:
    """Every ``Program data:`` payload the program emitted, from ``meta.logMessages``, by a plain
    invoke-stack walk (a witness written apart from ``program_logs``). All events, swap or not."""
    import base64
    import re

    stack: list[str] = []
    out: list[bytes] = []
    for line in cast(list[str], tx["meta"]["logMessages"]):
        if line.startswith("Program data: "):
            if stack and stack[-1] == program:
                out.append(base64.b64decode(line[len("Program data: ") :]))
        elif m := re.match(r"^Program (\w+) invoke \[(\d+)\]$", line):
            del stack[int(m.group(2)) - 1 :]
            stack.append(m.group(1))
        elif re.match(r"^Program (\w+) (?:success|failed)", line) and stack:
            stack.pop()
    return out


def inner_event_bodies(tx: dict[str, Any], program: str) -> list[bytes]:
    """Every event body the program emitted as a self-CPI inner instruction (event-CPI tag removed),
    whatever its discriminator, in execution order."""
    keys = account_keys(tx)
    out: list[bytes] = []
    for kind, ix in all_instructions(tx):
        if kind == "inner" and keys[ix["programIdIndex"]] == program:
            data = b58decode(str(ix["data"]))
            if data[:8] == EVENT_CPI_TAG:
                out.append(data[8:])
    return out
