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

Lesson of 2026-09-15 (T4.8c, ``docs/PUMPFUN-ONCHAIN.md`` §6d): a **second**
deploy that same week (slot 447228373, 07:34:32 BRT) — and this time the IDL
account *was* republished (47 instructions vs. 40, ``TradeEvent`` 34 fields vs.
32 named — the on-chain copy simply caught up to what the GitHub "main" IDL had
already shown T4.14). ``buy``/``sell`` and ``TradeEvent`` themselves were, once
again, unchanged byte for byte (``test_pumpfun_tx_parity.py``); what changed is
one more instruction (``sell_v2``) our builder does not construct. Both fields
of :data:`EXPECTED_PUMP_PROGRAM` moved this time; :data:`PREVIOUS_PUMP_PROGRAM`
keeps T4.8b's values so the history is not lost.

Lesson of 2026-09-23 (T4.8d, ``.claude/state/notes-T4.8d.md``): a **third** deploy
(slot 449734335, 11:45:19 BRT) that left the IDL account byte-for-byte untouched —
T4.8b's pattern again, and the reason both fields stay in the detector: a check
that watched only the hash would have called this program "unchanged" while its
bytecode was being replaced under a desk holding real positions. ``buy``/``sell``
and ``TradeEvent`` were, for the third time, proven unchanged (18 / 16 accounts,
24-byte data, 375-byte event) against third-party trades that landed on the new
program and against a mainnet simulation of our own bytes. Only
:attr:`ProgramExpectation.last_deploy_slot` moves this time: the hash of T4.8c and
of T4.8d are the same string on purpose.

Lesson of 2026-10-02 (T4.8e/T4.8f, ``obsidian/06-DECISIONS/Revisoes-Astra/T4.8e-decoders.md``): a
**fourth** deploy — PumpSwap (15:47:07Z), the pump program (slot 452654932, 15:47:21Z) and the
fee program (15:47:39Z) within 32 s — and the IDL account was untouched **a third time** (same
base64 as T4.8c's, read at slot 453633942). ``buy``/``sell`` of the pump program were again
byte-identical to real post-upgrade trades, but the *events* grew (``TradeEvent`` +8 bytes,
PumpSwap ``SellEvent`` +49) and PumpSwap's ``sell`` began to demand three remaining accounts
(``pool_v2``, a buyback recipient and its WSOL ATA; ``6062`` without them) — found only by
simulating our own bytes. Only :attr:`ProgramExpectation.last_deploy_slot` moves; PumpSwap and
the fee program are watched by ``program_watch.WATCHED_PROGRAMS``.

Lesson of 2026-10-08 (T4.8g, ``obsidian/06-DECISIONS/Revisoes-Astra/T4.8g-upgrade-08-10.md``): a
**fifth** deploy of the same three programs within 27 s (PumpSwap 454596406, pump 454596459, fees
454596501) and the IDL account untouched **a fourth time**. Nothing our builders or decoders read
moved (real trades and events, simulation of our own bytes); what changed is *data* (``BondingCurve``
151 -> 166 bytes, ``Global`` +1 byte). Only :attr:`ProgramExpectation.last_deploy_slot` moves.
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
    "PREVIOUS_PUMP_PROGRAM",
    "PUMP_PROGRAM_HISTORY",
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
UPGRADE_MESSAGE = "programa mudou: regravar T4.8h"


@dataclass(frozen=True, slots=True)
class ProgramExpectation:
    """What the fixtures were captured against — bump only by re-running the task
    :data:`UPGRADE_MESSAGE` names."""

    idl_sha256: str
    last_deploy_slot: int
    captured_at: str
    task: str


_T48B_PUMP_PROGRAM = ProgramExpectation(
    idl_sha256="fd48d9891733c30d167691b08ca5e5996e3723db58801db889b5a253f8d3e969",
    last_deploy_slot=446462760,
    captured_at="2026-09-12T17:52:36Z",
    task="T4.8b",
)
"""``t48b_idl_pump_onchain_raw.json`` (40 instructions, ``TradeEvent`` 32 fields —
the IDL account still predated *that* upgrade) and ``t48b_rpc_programdata_raw.json``
(deploy slot 446462760 = 2026-09-12 15:24:04 UTC, ``t48b_rpc_deploy_block_time_raw``).
Reachable through :data:`PUMP_PROGRAM_HISTORY`."""

_T48C_PUMP_PROGRAM = ProgramExpectation(
    idl_sha256="c7ca9566370b9351df9472adb7667dcc77695c49d0b1cc21b953f77567e2dc12",
    last_deploy_slot=447228373,
    captured_at="2026-09-15T19:53:52Z",
    task="T4.8c",
)
"""``t48c_idl_pump_onchain_raw.json`` (47 instructions, ``TradeEvent`` 34 fields —
the IDL account *was* republished that time, matching the count T4.14 read from
GitHub's "main") and ``t48c_rpc_programdata_raw.json`` (deploy slot 447228373 =
2026-09-15 10:34:32 UTC / 07:34:32 BRT, ``t48c_rpc_deploy_block_time_raw`` — also
the value the plantão's run 19 read independently, KB-0096). Reachable through
:data:`PUMP_PROGRAM_HISTORY`."""

_T48D_PUMP_PROGRAM = ProgramExpectation(
    idl_sha256="c7ca9566370b9351df9472adb7667dcc77695c49d0b1cc21b953f77567e2dc12",
    last_deploy_slot=449734335,
    captured_at="2026-09-23T17:37:58Z",
    task="T4.8d",
)
"""``t48d_rpc_programdata_raw.json`` (deploy slot 449734335 = 2026-09-23 14:45:19 UTC
/ 11:45:19 BRT, ``t48d_rpc_deploy_block_time_raw``) and ``t48d_rpc_idl_account_raw.json``
— whose bytes are, to the byte, :data:`PREVIOUS_PUMP_PROGRAM`'s: **this deploy did not
republish the IDL**, so the hash below is deliberately the same string as T4.8c's and
the slot is the only field that moved. The IDL fixture is not duplicated; the identity
test asserts the T4.8d account decodes to ``t48c_idl_pump_onchain_raw.json`` exactly.
The upgrade authority (``6348fb82…``) did not change. What *was* re-proven, since an
unchanged IDL proves nothing about the bytecode: byte-for-byte parity of ``buy`` /
``sell`` / ``TradeEvent`` with third-party trades that landed on this program
(``test_pumpfun_tx_parity_t48d.py``) and a mainnet simulation of our own bytes
(``t48d_simulation_proof_mainnet_raw.json``). Reachable through
:data:`PUMP_PROGRAM_HISTORY`."""

PREVIOUS_PUMP_PROGRAM = ProgramExpectation(
    idl_sha256="c7ca9566370b9351df9472adb7667dcc77695c49d0b1cc21b953f77567e2dc12",
    last_deploy_slot=452654932,
    captured_at="2026-10-05T16:33:02Z",
    task="T4.8f",
)
"""``t48f_rpc_programdata_pump_raw.json`` (deploy slot 452654932 = 2026-10-02 15:47:21 UTC,
``t48f_rpc_deploy_block_times.json``) and the IDL account — whose bytes are, to the byte, T4.8c's
for the **third** time (read at slot 453633942): the hash is the same string as T4.8c's and
T4.8d's on purpose and the slot is the only field that moved. The upgrade authority
(``6348fb82…``) did not change. Re-proven because an unchanged IDL proves nothing about the
bytecode: byte parity of the pump ``buy``/``sell`` with real post-upgrade trades
(``t48e_*``, executed by ``test_pumpfun_tx_parity_t48f.py``) and a mainnet simulation of our own bytes (never sent): curve buys and sells
(classic, holder-reward and cashback coins) and our PumpSwap ``sell``, all ``err: null`` with
events decoded. ``unexplained_lamports == 0`` on every one except the cashback **buy**, whose
residual is exactly the 1 513 840-lamport ATA rent of a wallet that had none (a simulation has no
inner instructions to name it). A PumpSwap **cashback** ``sell`` (``pool_v2`` plus the accumulator
pair) is proven both ways: two real post-upgrade sells reproduced account for account
(``test_pumpswap_tx_t48f.py``) and our own bytes simulated on a migrated cashback pool, ``err: null``;
a wallet that never traded on PumpSwap pays the accumulator's 1 346 200-lamport rent on its first
such sell, named ``cashback_init_lamports`` (``unexplained`` stays 0). Kept for history —
:func:`program_divergence` only compares against the current :data:`EXPECTED_PUMP_PROGRAM`."""

EXPECTED_PUMP_PROGRAM = ProgramExpectation(
    idl_sha256="c7ca9566370b9351df9472adb7667dcc77695c49d0b1cc21b953f77567e2dc12",
    last_deploy_slot=454596459,
    captured_at="2026-10-08T18:47:22Z",
    task="T4.8g",
)
"""``t48g_rpc_programdata_pump_raw.json`` (deploy slot 454596459 = 2026-10-08 16:20:17 UTC,
``t48g_rpc_deploy_block_times.json``) and the IDL account (``t48g_rpc_idl_account_raw.json``, slot
454629141) — T4.8c's bytes for the **fourth** time: same hash on purpose, only the slot moved; the
upgrade authority (``6348fb82…``) did not change. Re-proven because an unchanged IDL proves nothing
about the bytecode: parity of ``buy``/``sell`` and of PumpSwap's 24-account ``sell`` with real
post-upgrade trades (``test_pumpfun_tx_parity_t48g.py``, ``test_pumpswap_tx_t48g.py``), the event
decoders on real events (``test_events_t48g.py``) and a mainnet simulation of our own bytes, never
sent (``t48g_simulation_proof_mainnet.json``). Simulated: curve cashback buy and PumpSwap cashback
sell; NOT covered: the curve cashback sell and the classic SPL-token curve sell."""

PUMP_PROGRAM_HISTORY: tuple[ProgramExpectation, ...] = (
    _T48B_PUMP_PROGRAM,
    _T48C_PUMP_PROGRAM,
    _T48D_PUMP_PROGRAM,
    PREVIOUS_PUMP_PROGRAM,
    EXPECTED_PUMP_PROGRAM,
)
"""Every deploy this package has been proven against, oldest first — for docs
and tests that want to show the program has moved more than once. Five deploys
in four weeks; four of them left the IDL account untouched."""


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
