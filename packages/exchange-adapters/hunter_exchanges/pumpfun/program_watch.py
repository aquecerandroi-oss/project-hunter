"""The other programs the pump desk depends on, watched like the pump program itself (T4.8f).

``program_identity.py`` pins the **pump** program (IDL hash + deploy slot). Our builders also
execute **PumpSwap** (the ``sell`` of a migrated position) and the pump **fee** program (both
``buy``/``sell`` builders pass ``pfeeUx…`` and read its ``FeeConfig``). All three were redeployed
on 2026-10-02 within 32 s (15:47:07Z PumpSwap, 15:47:21Z pump, 15:47:39Z fees), and PumpSwap's
``sell`` began to demand three remaining accounts nothing announced (``6062 InvalidPoolV2``,
found only by simulating our own bytes). ``FeeConfig`` unchanged proves nothing about bytecode,
so the deploy slot of each is watched by the runtime detector: one more upgrade of any of them
is a ``program_upgraded`` refusal of entries until the builders are re-proven.

Only the deploy slot is pinned for these two (no IDL hash): PumpSwap's on-chain IDL was not
republished by the 2026-10-02 upgrade and the fee program's IDL is not read by anything here.
One ``getMultipleAccounts`` reads every ``ProgramData`` header (45 bytes each).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.program_identity import (
    BPF_UPGRADEABLE_LOADER_ID,
    UPGRADE_MESSAGE,
    decode_programdata_header,
)
from hunter_exchanges.pumpfun.solana_codec import find_program_address, pubkey_bytes
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.pdas import PUMP_FEE_PROGRAM_ID

__all__ = [
    "WATCHED_PROGRAMS",
    "WatchedProgram",
    "programdata_address",
    "read_deploy_slots",
    "watched_divergence",
]

_PROGRAMDATA_HEADER_LEN = 45


@dataclass(frozen=True, slots=True)
class WatchedProgram:
    program_id: str
    label: str
    last_deploy_slot: int
    captured_at: str
    task: str


WATCHED_PROGRAMS: tuple[WatchedProgram, ...] = (
    WatchedProgram(
        program_id=PUMPSWAP_PROGRAM_ID,
        label="pumpswap",
        last_deploy_slot=452654882,  # 2026-10-02 15:47:07Z
        captured_at="2026-10-05 (context slot 453627199)",
        task="T4.8f",
    ),
    WatchedProgram(
        program_id=PUMP_FEE_PROGRAM_ID,
        label="pump_fees",
        last_deploy_slot=452655002,  # 2026-10-02 15:47:39Z
        captured_at="2026-10-05 (context slot 453627199)",
        task="T4.8f",
    ),
)
"""Proven against: ``t48f_rpc_programdata_{pumpswap,pump_fees}_raw.json`` (read 2026-10-05), a
mainnet simulation of our PumpSwap ``sell`` at slot 453626256 and the real post-upgrade sells
of ``t48e_rpc_amm_tx_*``. Bump only by re-running that proof."""


@lru_cache(maxsize=8)
def programdata_address(program_id: str) -> str:
    """The BPF-upgradeable ``ProgramData`` PDA of ``program_id``."""
    return find_program_address([pubkey_bytes(program_id)], BPF_UPGRADEABLE_LOADER_ID)[0]


def read_deploy_slots(rpc: SolanaTxRpcClient, program_ids: Sequence[str]) -> dict[str, int]:
    """Last deploy slot of every program in **one** ``getMultipleAccounts`` (45-byte slices).
    A program the node does not return is an error, never a slot of zero."""
    addresses = [programdata_address(p) for p in program_ids]
    config = {
        "encoding": "base64",
        "commitment": "confirmed",
        "dataSlice": {"offset": 0, "length": _PROGRAMDATA_HEADER_LEN},
    }
    result = cast(dict[str, Any], rpc.call("getMultipleAccounts", [addresses, config]))
    values = cast(list[dict[str, Any] | None], result.get("value") or [])
    if len(values) != len(addresses):
        raise MalformedMessage("getMultipleAccounts answered a short list", exchange="pumpfun")
    slots: dict[str, int] = {}
    for program_id, address, value in zip(program_ids, addresses, values, strict=True):
        if value is None:
            raise MalformedMessage(
                f"ProgramData {address} of {program_id} not found on this cluster",
                exchange="pumpfun",
            )
        slots[program_id] = decode_programdata_header(
            str(value["data"][0]), owner=str(value["owner"])
        )
    return slots


def watched_divergence(watch: WatchedProgram, slot: int) -> str | None:
    """``None`` when the chain still runs the proven deploy; otherwise the difference, named."""
    if slot == watch.last_deploy_slot:
        return None
    return (
        f"{watch.label} last_deploy_slot {slot} != {watch.last_deploy_slot} "
        f"({UPGRADE_MESSAGE}; fixtures {watch.task} {watch.captured_at})"
    )
