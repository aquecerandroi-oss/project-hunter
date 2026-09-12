"""Identity of the pump program as the chain reports it — an upgrade becomes a
*named* refusal (``program_upgraded``) instead of a surprise mid-trade (T4.8b).

Two ``getAccountInfo`` reads, both pure to decode:

- the Anchor **IDL account** — ``create_with_seed(find_program_address([],
  program)[0], "anchor:idl", program)``: 8-byte discriminator, 32-byte authority,
  ``u32`` length, zlib-compressed IDL JSON. Hashed *canonically* (sorted keys, no
  whitespace) so a pretty-printed copy hashes the same;
- the BPF-upgradeable **``ProgramData``** account — PDA ``[program]`` under the
  loader: ``u32`` tag (3), ``u64`` slot of the last deploy, ``Option<Pubkey>``
  authority. Only its 45-byte header is read (``dataSlice``): the program binary
  behind it is 10 MB.

Lesson of 2026-09-12 (``docs/PUMPFUN-ONCHAIN.md`` §6c): the program was upgraded
at slot 446462760 (15:24:04 UTC) — ``buy``/``sell`` began to demand a new remaining
account and ``TradeEvent`` grew 16 bytes — and the IDL account was **not**
touched: its hash that evening equals the morning's. So the deploy slot is the
detector that moves on every upgrade, and the IDL hash the one that names *what*
changed when it is updated. Both are compared with the values captured next to
the fixtures this code was proven against; either differing is a divergence.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.mayhem_state import create_with_seed
from hunter_exchanges.pumpfun.solana_codec import b58encode, find_program_address, pubkey_bytes
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient

__all__ = [
    "BPF_UPGRADEABLE_LOADER_ID",
    "EXPECTED_PUMP_PROGRAM",
    "DecodedIdlAccount",
    "ProgramExpectation",
    "ProgramIdentity",
    "canonical_idl_sha256",
    "decode_idl_account",
    "decode_programdata_header",
    "program_divergence",
    "pump_idl_account_address",
    "pump_programdata_address",
    "read_last_deploy_slot",
    "read_program_identity",
]

BPF_UPGRADEABLE_LOADER_ID = "BPFLoaderUpgradeab1e11111111111111111111111"
_IDL_ACCOUNT_DISCRIMINATOR = bytes.fromhex("184662bf3a907b9e")
"""Anchor hard-codes ``IdlAccount``'s discriminator (``anchor-lang`` ``idl/mod.rs``:
``[24, 70, 98, 191, 58, 144, 123, 158]``) — not ``sha256("account:IdlAccount")``;
the same 8 bytes head the pump program's IDL account on chain (``t48b_rpc_idl_account_raw``)."""
_PROGRAMDATA_TAG = 3
_PROGRAMDATA_HEADER_LEN = 45
UPGRADE_MESSAGE = "programa mudou: regravar T4.8b"


@dataclass(frozen=True, slots=True)
class ProgramExpectation:
    """What the fixtures were captured against — bump only by re-running T4.8b."""

    idl_sha256: str
    last_deploy_slot: int
    captured_at: str
    task: str


EXPECTED_PUMP_PROGRAM = ProgramExpectation(
    idl_sha256="fd48d9891733c30d167691b08ca5e5996e3723db58801db889b5a253f8d3e969",
    last_deploy_slot=446462760,
    captured_at="2026-09-12T17:52:36Z",
    task="T4.8b",
)
"""``t48b_idl_pump_onchain_raw.json`` (40 instructions, ``TradeEvent`` 32 fields —
the IDL account still predates the upgrade) and ``t48b_rpc_programdata_raw.json``
(deploy slot 446462760 = 2026-09-12 15:24:04 UTC, ``t48b_rpc_deploy_block_time_raw``)."""


@dataclass(frozen=True, slots=True)
class DecodedIdlAccount:
    authority: str
    idl_bytes: bytes


@dataclass(frozen=True, slots=True)
class ProgramIdentity:
    idl_sha256: str
    idl_authority: str
    idl_slot: int
    last_deploy_slot: int
    programdata_slot: int


@lru_cache(maxsize=1)
def pump_idl_account_address() -> str:
    base, _ = find_program_address([], PUMP_PROGRAM_ID)
    return create_with_seed(base, "anchor:idl", PUMP_PROGRAM_ID)


@lru_cache(maxsize=1)
def pump_programdata_address() -> str:
    return find_program_address([pubkey_bytes(PUMP_PROGRAM_ID)], BPF_UPGRADEABLE_LOADER_ID)[0]


def _b64(data_base64: str, what: str) -> bytes:
    try:
        return base64.b64decode(data_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise MalformedMessage(f"{what} data is not base64: {exc}", exchange="pumpfun") from exc


def decode_idl_account(data_base64: str, *, owner: str) -> DecodedIdlAccount:
    """The IDL JSON bytes exactly as stored (after zlib), and the authority."""
    if owner != PUMP_PROGRAM_ID:
        raise MalformedMessage(
            f"IDL account owner {owner!r} is not the pump program", exchange="pumpfun"
        )
    raw = _b64(data_base64, "IDL account")
    if raw[:8] != _IDL_ACCOUNT_DISCRIMINATOR:
        raise MalformedMessage("wrong IdlAccount discriminator", exchange="pumpfun")
    if len(raw) < 44:
        raise MalformedMessage("IDL account truncated", exchange="pumpfun")
    (length,) = struct.unpack_from("<I", raw, 40)
    try:
        idl_bytes = zlib.decompress(raw[44 : 44 + length])
    except zlib.error as exc:
        raise MalformedMessage(f"IDL account not zlib: {exc}", exchange="pumpfun") from exc
    return DecodedIdlAccount(authority=b58encode(raw[8:40]), idl_bytes=idl_bytes)


def canonical_idl_sha256(idl_bytes: bytes) -> str:
    """sha256 of the IDL with sorted keys and no whitespace — formatting-independent."""
    try:
        obj: Any = json.loads(idl_bytes)
    except ValueError as exc:
        raise MalformedMessage(f"IDL is not JSON: {exc}", exchange="pumpfun") from exc
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def decode_programdata_header(data_base64: str, *, owner: str) -> int:
    """The slot of the last deploy/upgrade, from the 45-byte ``ProgramData`` header."""
    if owner != BPF_UPGRADEABLE_LOADER_ID:
        raise MalformedMessage(
            f"ProgramData owner {owner!r} is not the upgradeable loader", exchange="pumpfun"
        )
    raw = _b64(data_base64, "ProgramData")
    if len(raw) < 12:
        raise MalformedMessage("ProgramData header truncated", exchange="pumpfun")
    tag, slot = struct.unpack_from("<IQ", raw, 0)
    if tag != _PROGRAMDATA_TAG:
        raise MalformedMessage(f"ProgramData tag {tag} != {_PROGRAMDATA_TAG}", exchange="pumpfun")
    return int(slot)


def _account(
    rpc: SolanaTxRpcClient, address: str, *, data_slice: int | None
) -> tuple[dict[str, Any], int]:
    config: dict[str, Any] = {"encoding": "base64", "commitment": "confirmed"}
    if data_slice is not None:
        config["dataSlice"] = {"offset": 0, "length": data_slice}
    result = cast(dict[str, Any], rpc.call("getAccountInfo", [address, config]))
    value = result.get("value")
    if value is None:
        raise MalformedMessage(f"account {address} not found on this cluster", exchange="pumpfun")
    return cast(dict[str, Any], value), int(cast(dict[str, Any], result["context"])["slot"])


def read_last_deploy_slot(rpc: SolanaTxRpcClient) -> int:
    """One cheap read (45 bytes) — the runtime detector."""
    value, _ = _account(rpc, pump_programdata_address(), data_slice=_PROGRAMDATA_HEADER_LEN)
    return decode_programdata_header(str(value["data"][0]), owner=str(value["owner"]))


def read_program_identity(rpc: SolanaTxRpcClient) -> ProgramIdentity:
    """Both reads — the boot check. Two ``getAccountInfo`` calls, nothing else."""
    idl_value, idl_slot = _account(rpc, pump_idl_account_address(), data_slice=None)
    decoded = decode_idl_account(str(idl_value["data"][0]), owner=str(idl_value["owner"]))
    pd_value, pd_slot = _account(
        rpc, pump_programdata_address(), data_slice=_PROGRAMDATA_HEADER_LEN
    )
    return ProgramIdentity(
        idl_sha256=canonical_idl_sha256(decoded.idl_bytes),
        idl_authority=decoded.authority,
        idl_slot=idl_slot,
        last_deploy_slot=decode_programdata_header(
            str(pd_value["data"][0]), owner=str(pd_value["owner"])
        ),
        programdata_slot=pd_slot,
    )


def program_divergence(
    identity: ProgramIdentity, expected: ProgramExpectation = EXPECTED_PUMP_PROGRAM
) -> str | None:
    """``None`` when the chain matches what the fixtures were proven against;
    otherwise the difference, named, with the instruction of what to do."""
    reasons: list[str] = []
    if identity.last_deploy_slot != expected.last_deploy_slot:
        reasons.append(
            f"last_deploy_slot {identity.last_deploy_slot} != {expected.last_deploy_slot}"
        )
    if identity.idl_sha256 != expected.idl_sha256:
        reasons.append(f"idl_sha256 {identity.idl_sha256[:16]}… != {expected.idl_sha256[:16]}…")
    if not reasons:
        return None
    return (
        f"{'; '.join(reasons)} ({UPGRADE_MESSAGE}; fixtures {expected.task} {expected.captured_at})"
    )
